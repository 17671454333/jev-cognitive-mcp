"""
Model Context Protocol (MCP) JSON-RPC 2.0 Stdio Server for JevKit.

Exposes 5 advisory tools to MCP-compatible coding agents (OpenAI Codex CLI,
Claude Code, Cursor):
- jev_guard: Advisory pre-tool command risk screening (Layer-0 deterministic reflex + optional System-1 JEV)
- jev_route: Advisory task complexity & model tier routing
- jev_verify: Advisory review of caller-supplied change descriptions and test evidence
- jev_rerank: Bounded semantic candidate ranking
- jev_arbitrate: Deterministic 5-factor Meta-Controller escalation recommendation

Note: All tool outputs are advisory recommendations. Actual command execution,
blocking, and human-approval gates remain enforced by the host runtime.
"""

import json
import sys
from typing import Any, Dict, Optional
from . import __version__
from .core import JevIntegrationError
from .guard import check_command_safety, local_reflex_screen, run_layer0_benchmark
from .router import route_task
from .verifier import verify_completion
from .reranker import rerank
from .controller import arbitrate_escalation, ControllerSignals

MCP_TOOLS = [
    {
        "name": "jev_guard",
        "description": "Provide advisory risk screening for a shell command using Layer-0 deterministic regex rules and (unless reflex_only=true) System-1 probabilistic evaluation. Does not intercept host execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to inspect."},
                "context": {"type": "string", "description": "Optional rationale or context."},
                "reflex_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, run only offline Layer-0 deterministic screening (requires no external JevBridge runtime).",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "jev_route",
        "description": "Provide advisory task complexity and model tier recommendation (requires configured JevBridge runtime).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_description": {"type": "string", "description": "Task description or prompt."},
                "context": {"type": "string", "description": "Optional repository or file context."},
            },
            "required": ["task_description"],
        },
    },
    {
        "name": "jev_verify",
        "description": "Review caller-supplied task specification, change summary, and test logs for potential evidence gaps (does not run tests or read git diffs directly; requires JevBridge runtime).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_spec": {"type": "string", "description": "Original task requirements."},
                "implemented_changes": {"type": "string", "description": "Caller-supplied summary of diffs or artifacts."},
                "test_results": {"type": "string", "description": "Optional caller-supplied test runner output."},
            },
            "required": ["task_spec", "implemented_changes"],
        },
    },
    {
        "name": "jev_rerank",
        "description": "Rank up to 96 candidate text items against a query in batches of 12 (requires JevBridge runtime).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search or triage query."},
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Candidate texts to rank.",
                },
                "top_k": {"type": "integer", "description": "Optional limit on returned items."},
            },
            "required": ["query", "items"],
        },
    },
    {
        "name": "jev_arbitrate",
        "description": "Run the offline deterministic 5-factor Meta-Controller to recommend Layer-0 Reflex, System-1 Intuition, System-2 Deep Reasoning, or Human Gate.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confidence": {"type": "number", "description": "System-1 confidence (0.0 to 1.0)."},
                "risk": {"type": "number", "description": "Estimated blast-radius risk (0.0 to 1.0)."},
                "reversible": {"type": "boolean", "description": "True if two-way door (reversible)."},
                "expected_value": {"type": "number", "default": 0.5, "description": "Expected value of deep reasoning (0.0 to 1.0)."},
                "cost_pressure": {"type": "number", "default": 0.2, "description": "Token/latency budget pressure (0.0 to 1.0)."},
                "deterministic_match": {"type": "boolean", "default": False},
                "requires_causal_proof": {"type": "boolean", "default": False},
            },
            "required": ["confidence", "risk", "reversible"],
        },
    },
    {
        "name": "jev_benchmark",
        "description": "Run the offline deterministic Layer-0 JSONL replay benchmark suite and return accuracy and timing metrics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {
                    "type": "string",
                    "default": "benchmarks/layer0_corpus.jsonl",
                    "description": "Path to JSONL benchmark fixture file.",
                },
            },
        },
    },
]


def handle_mcp_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single JSON-RPC 2.0 MCP message and return response dict (or None for notifications)."""
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}

    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params") or {}

    if req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "jev-cognitive-mcp", "version": __version__},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            payload = _dispatch_tool(name, args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                    "isError": False,
                },
            }
        except JevIntegrationError as exc:
            err_payload = {"ok": False, "code": exc.code, "billing_uncertain": exc.billing_uncertain}
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(err_payload, ensure_ascii=False)}],
                    "isError": True,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": str(exc)},
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "jev_guard":
        cmd = args.get("command", "")
        ctx = args.get("context")
        if args.get("reflex_only"):
            verdict = local_reflex_screen(cmd, ctx)
            if verdict is None:
                return {"ok": True, "advisory": True, "action": "pass_reflex", "layer0_triggered": False}
        else:
            verdict = check_command_safety(cmd, ctx)
        return {
            "ok": True,
            "advisory": True,
            "action": verdict.action.value,
            "is_destructive": verdict.is_destructive,
            "destructive_prob": verdict.destructive_prob,
            "is_rce_or_exfil": verdict.is_rce_or_exfil,
            "rce_prob": verdict.rce_prob,
            "is_secret_leak": verdict.is_secret_leak,
            "secret_prob": verdict.secret_prob,
            "confidence": verdict.overall_confidence,
            "confidence_level": verdict.confidence_level.value,
            "layer0_triggered": verdict.layer0_triggered,
            "summary": verdict.summary,
        }

    if name == "jev_route":
        verdict = route_task(args.get("task_description", ""), args.get("context"))
        return {
            "ok": True,
            "advisory": True,
            "tier": verdict.tier.value,
            "complexity_score": verdict.complexity_score,
            "requires_architecture": verdict.requires_architecture,
            "recommended_models": verdict.recommended_models,
            "confidence": verdict.confidence,
            "confidence_level": verdict.confidence_level.value,
            "rationale": verdict.rationale,
        }

    if name == "jev_verify":
        verdict = verify_completion(
            args.get("task_spec", ""),
            args.get("implemented_changes", ""),
            args.get("test_results"),
        )
        return {
            "ok": True,
            "advisory": True,
            "status": verdict.status.value,
            "is_satisfied": verdict.is_satisfied,
            "satisfaction_prob": verdict.satisfaction_prob,
            "has_untested_edges": verdict.has_untested_edges,
            "untested_edges_prob": verdict.untested_edges_prob,
            "quality_score": verdict.quality_score,
            "confidence": verdict.confidence,
            "confidence_level": verdict.confidence_level.value,
            "feedback": verdict.feedback,
        }

    if name == "jev_rerank":
        scored = rerank(args.get("query", ""), args.get("items", []), top_k=args.get("top_k"))
        return {
            "ok": True,
            "advisory": True,
            "results": [
                {
                    "index": item.index,
                    "content": item.content,
                    "relevance_score": item.relevance_score,
                    "is_relevant": item.is_relevant,
                    "confidence": item.confidence,
                }
                for item in scored
            ],
        }

    if name == "jev_arbitrate":
        signals = ControllerSignals(
            confidence=float(args["confidence"]),
            risk=float(args["risk"]),
            reversible=bool(args["reversible"]),
            expected_value=float(args.get("expected_value", 0.5)),
            cost_pressure=float(args.get("cost_pressure", 0.2)),
            deterministic_match=bool(args.get("deterministic_match", False)),
            requires_causal_proof=bool(args.get("requires_causal_proof", False)),
        )
        decision = arbitrate_escalation(signals)
        return {
            "ok": True,
            "advisory": True,
            "target_layer": decision.target_layer.value,
            "escalate_to_system2": decision.escalate_to_system2,
            "require_human_approval": decision.require_human_approval,
            "utility_score": decision.utility_score,
            "triggers": decision.triggers,
            "rationale": decision.rationale,
        }

    if name == "jev_benchmark":
        input_path = args.get("input_path", "benchmarks/layer0_corpus.jsonl")
        summary = run_layer0_benchmark(input_path)
        return {"ok": True, "advisory": True, **summary}

    raise ValueError(f"Unknown tool: {name}")


def run_stdio_server() -> None:
    """Run MCP stdio server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue
        resp = handle_mcp_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
