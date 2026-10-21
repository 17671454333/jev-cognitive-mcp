"""
Completion & Acceptance Gate.

Acts as an unbiased, non-generative judge before an agent marks a task complete
or merges a pull request. Prevents premature stops, superficial finishes, and
unverified diffs.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .core import (
    call_jev,
    ConfidenceLevel,
    JevResponse,
    JevIntegrationError,
    validate_typed_answers,
    get_confidence_level,
)


class VerificationStatus(str, Enum):
    PASS = "pass"
    ADVISORY = "advisory"
    NEEDS_REVISION = "needs_revision"


@dataclass
class VerificationVerdict:
    status: VerificationStatus
    is_satisfied: bool
    satisfaction_prob: float
    has_untested_edges: bool
    untested_edges_prob: float
    quality_score: float
    confidence: Optional[float]
    confidence_level: ConfidenceLevel
    feedback: str
    response: JevResponse


def verify_completion(
    task_spec: str,
    implemented_changes: str,
    test_results: Optional[str] = None,
) -> VerificationVerdict:
    """Judge whether an implementation genuinely fulfills specification and test criteria."""
    if (
        not isinstance(task_spec, str)
        or not task_spec.strip()
        or not isinstance(implemented_changes, str)
        or not implemented_changes.strip()
        or (test_results is not None and not isinstance(test_results, str))
    ):
        raise JevIntegrationError("INPUT_INVALID")
    state_blocks = [
        f"### 1. Target Specification / User Requirements:\n{task_spec.strip()}",
        f"### 2. Implemented Code Changes / Artifacts:\n{implemented_changes.strip()}",
    ]
    if test_results and test_results.strip():
        state_blocks.append(f"### 3. Verification & Test Run Output:\n{test_results.strip()}")
    else:
        state_blocks.append("### 3. Verification & Test Run Output:\n(No test execution output provided)")

    state = "\n\n".join(state_blocks)

    questions = {
        "is_satisfied": {
            "type": "noul",
            "instructions": "Does the implemented code completely fulfill all explicit core requirements stated in the specification?",
            "criteria": {
                "true": "All key requirements, functions, and requested behavior are fully implemented",
                "false": "Critical features are missing, stubbed out, or deviate from requested goals",
            },
        },
        "has_untested_edges": {
            "type": "noul",
            "instructions": "Are there glaring unhandled edge cases, unverified error paths, or missing test validation?",
            "criteria": {
                "true": "Obvious gaps, unhandled exceptions, or missing validation against edge cases",
                "false": "Robust implementation with verified logic and test evidence",
            },
        },
        "quality_score": {
            "type": "score",
            "instructions": "Rate overall implementation completeness and rigor from 1 (poor/incomplete) to 5 (production ready)",
            "criteria": [
                "1 - Severely incomplete, non-functional, or broken",
                "2 - Partial implementation with noticeable defects",
                "3 - Working prototype meeting baseline needs but lacks polish/tests",
                "4 - Solid, complete implementation with sound error handling",
                "5 - Production-grade, thoroughly verified with full coverage",
            ],
        },
        "verdict": {
            "type": "choice",
            "instructions": "Select final acceptance gate status",
            "criteria": {
                "pass": "Deliver directly to user; implementation is complete and verified",
                "advisory": "Deliver with notes; baseline is met but minor tests or edge cases remain unverified",
                "reject": "Do not deliver; agent must continue working to address missing items",
                "insufficient": "Evidence is insufficient to establish completion",
            },
        },
    }

    resp = call_jev(state, questions)
    validate_typed_answers(resp, questions)
    sat_ans = resp.answers["is_satisfied"]
    edge_ans = resp.answers["has_untested_edges"]
    qual_ans = resp.answers["quality_score"]
    dec_ans = resp.answers["verdict"]

    sat_prob = sat_ans.probability
    edge_prob = edge_ans.probability
    score = qual_ans.score
    choice_val = dec_ans.selected
    conf = dec_ans.confidence
    level = get_confidence_level(conf)

    if (
        choice_val == "pass"
        and level == ConfidenceLevel.HIGH
        and test_results
        and test_results.strip()
        and sat_prob >= 0.80
        and edge_prob <= 0.40
        and score >= 2.5
    ):
        status = VerificationStatus.PASS
        feedback = (
            f"Verification Passed: Quality index {score:.1f}/4.0. "
            "Supplied evidence supports acceptance; this does not replace deterministic test execution."
        )
    elif choice_val in ("reject", "insufficient") or sat_prob < 0.60 or score < 1.0:
        status = VerificationStatus.NEEDS_REVISION
        feedback = (
            f"Verification Failed (Quality {score:.1f}/4.0, Satisfaction prob: {sat_prob:.2f}). "
            "Requirements unmet or critical defects remain."
        )
    else:
        status = VerificationStatus.ADVISORY
        feedback = (
            f"Advisory Acceptance (Quality {score:.1f}/4.0, Satisfaction prob: {sat_prob:.2f}). "
            f"Completion is not fully established: edge-case validation needs review ({edge_prob:.2f})."
        )

    return VerificationVerdict(
        status=status,
        is_satisfied=sat_prob >= 0.5,
        satisfaction_prob=sat_prob,
        has_untested_edges=edge_prob >= 0.5,
        untested_edges_prob=edge_prob,
        quality_score=score,
        confidence=conf,
        confidence_level=level,
        feedback=feedback,
        response=resp,
    )
