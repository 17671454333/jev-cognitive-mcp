"""
CLI Interface for JevKit (jev-cognitive-mcp)

Usage:
  python -m jev_kit guard "<command>" [--context "<ctx>"] [--reflex-only]
  python -m jev_kit route "<task_description>" [--context "<ctx>"]
  python -m jev_kit verify --spec "<spec>" --changes "<changes>" [--tests "<tests>"]
  python -m jev_kit rerank --query "<query>" "<item1>" "<item2>" ...
  python -m jev_kit arbitrate --confidence 0.9 --risk 0.1 --reversible
  python -m jev_kit mcp
"""

import argparse
import json
import sys
from .core import JevIntegrationError
from .guard import check_command_safety, local_reflex_screen
from .router import route_task
from .verifier import verify_completion
from .reranker import rerank
from .controller import arbitrate_escalation, ControllerSignals
from .mcp_server import run_stdio_server


def fmt(value, digits=2):
    return "unknown" if value is None else f"{value:.{digits}f}"


def main():
    parser = argparse.ArgumentParser(description="JevKit - 3+1 Cognitive Hierarchy & MCP CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # guard
    guard_parser = subparsers.add_parser("guard", help="Screen command safety before execution")
    guard_parser.add_argument("cmd", help="Command string to inspect")
    guard_parser.add_argument("--context", default=None, help="Optional context or intent")
    guard_parser.add_argument("--reflex-only", action="store_true", help="Run Layer-0 deterministic screen only")

    # route
    route_parser = subparsers.add_parser("route", help="Route task complexity and model tier")
    route_parser.add_argument("task", help="Task prompt or description")
    route_parser.add_argument("--context", default=None, help="Optional repository context")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify task acceptance and completion")
    verify_parser.add_argument("--spec", required=True, help="Original user task specification")
    verify_parser.add_argument("--changes", required=True, help="Implemented changes or diff")
    verify_parser.add_argument("--tests", default=None, help="Test output or verification logs")

    # rerank
    rerank_parser = subparsers.add_parser("rerank", help="Rerank candidate items against query")
    rerank_parser.add_argument("--query", required=True, help="Target search query")
    rerank_parser.add_argument("items", nargs="+", help="Candidate items to rank")

    # arbitrate
    arb_parser = subparsers.add_parser("arbitrate", help="Run 5-factor Meta-Controller arbitration")
    arb_parser.add_argument("--confidence", type=float, required=True, help="System-1 confidence (0..1)")
    arb_parser.add_argument("--risk", type=float, required=True, help="Risk score (0..1)")
    arb_parser.add_argument("--reversible", action="store_true", help="Action is a reversible two-way door")
    arb_parser.add_argument("--irreversible", action="store_true", help="Action is an irreversible one-way door")
    arb_parser.add_argument("--value", type=float, default=0.5, help="Expected deep reasoning value (0..1)")
    arb_parser.add_argument("--cost", type=float, default=0.2, help="Cost budget pressure (0..1)")
    arb_parser.add_argument("--deterministic", action="store_true", help="Layer-0 deterministic rule matched")
    arb_parser.add_argument("--causal", action="store_true", help="Requires strict causal proof")

    # mcp
    subparsers.add_parser("mcp", help="Start JSON-RPC 2.0 MCP stdio server")

    args = parser.parse_args()

    if args.command == "mcp":
        run_stdio_server()
        return

    if args.command == "guard":
        if args.reflex_only:
            res = local_reflex_screen(args.cmd, args.context)
            if res is None:
                print(json.dumps({"ok": True, "action": "pass_reflex", "layer0_triggered": False}))
                return
        else:
            res = check_command_safety(args.cmd, args.context)
        print("\n=== Jev Security Guard Verdict ===")
        print(f"Action:             {res.action.value.upper()}")
        print(f"Layer-0 Reflex:     {res.layer0_triggered}")
        print(f"Confidence Level:   {res.confidence_level.value} (conf={fmt(res.overall_confidence)})")
        print(f"Destructive Prob:   {res.destructive_prob:.2f}")
        print(f"RCE / Exfil Prob:   {res.rce_prob:.2f}")
        print(f"Secret Leak Prob:   {res.secret_prob:.2f}")
        print(f"Summary:            {res.summary}")
        if res.response is not None:
            print(f"Model ID:           {res.response.model}")
            print(f"Reported Cost:       ${fmt(res.response.usage.cost, 6)}\n")

    elif args.command == "route":
        res = route_task(args.task, args.context)
        print("\n=== Jev Model & Task Route ===")
        print(f"Model Tier:         {res.tier.value.upper()}")
        print(f"Difficulty Score:   {res.complexity_score:.2f} / 4.0")
        print(f"Requires Arch:      {res.requires_architecture}")
        print(f"Confidence:         {fmt(res.confidence)} ({res.confidence_level.value})")
        print(f"Recommended Models: {', '.join(res.recommended_models)}")
        print(f"Rationale:          {res.rationale}")
        print(f"Reported Cost:       ${fmt(res.response.usage.cost, 6)}\n")

    elif args.command == "verify":
        res = verify_completion(args.spec, args.changes, args.tests)
        print("\n=== Jev Acceptance & Completion Gate ===")
        print(f"Status:             {res.status.value.upper()}")
        print(f"Quality Score:      {res.quality_score:.2f} / 4.0")
        print(f"Satisfaction Prob:  {res.satisfaction_prob:.2f}")
        print(f"Untested Edges:     {res.has_untested_edges} (prob={res.untested_edges_prob:.2f})")
        print(f"Confidence:         {fmt(res.confidence)} ({res.confidence_level.value})")
        print(f"Feedback:           {res.feedback}")
        print(f"Reported Cost:       ${fmt(res.response.usage.cost, 6)}\n")

    elif args.command == "rerank":
        res = rerank(args.query, args.items)
        print("\n=== Jev Semantic Rerank Results ===")
        for r in res:
            rel_mark = "PASS" if r.is_relevant else "SKIP"
            print(f"[{rel_mark}] Score: {r.relevance_score:.2f}/4.0 (conf={fmt(r.confidence)}) -> {r.content}")
        print()

    elif args.command == "arbitrate":
        reversible = True if args.reversible else (False if args.irreversible else True)
        decision = arbitrate_escalation(
            ControllerSignals(
                confidence=args.confidence,
                risk=args.risk,
                reversible=reversible,
                expected_value=args.value,
                cost_pressure=args.cost,
                deterministic_match=args.deterministic,
                requires_causal_proof=args.causal,
            )
        )
        print(
            json.dumps(
                {
                    "target_layer": decision.target_layer.value,
                    "escalate_to_system2": decision.escalate_to_system2,
                    "require_human_approval": decision.require_human_approval,
                    "utility_score": decision.utility_score,
                    "triggers": decision.triggers,
                    "rationale": decision.rationale,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except JevIntegrationError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "billing_uncertain": exc.billing_uncertain}))
        raise SystemExit(2)
