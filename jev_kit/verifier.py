"""
Advisory Evidence Review Gate.

Reviews caller-supplied task specifications, change descriptions, and test output
logs to identify potential gaps or unhandled edge cases. This module does NOT
inspect git diffs or execute test runners directly; deterministic test execution
and host/human review remain required.
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
    """Review caller-supplied specification, change summary, and test logs for evidence gaps."""
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
        f"### 2. Supplied Change Summary / Artifacts:\n{implemented_changes.strip()}",
    ]
    if test_results and test_results.strip():
        state_blocks.append(f"### 3. Supplied Test Output:\n{test_results.strip()}")
    else:
        state_blocks.append("### 3. Supplied Test Output:\n(No test execution output provided)")

    state = "\n\n".join(state_blocks)

    questions = {
        "is_satisfied": {
            "type": "noul",
            "instructions": "Does the supplied change description address all explicit core requirements stated in the specification?",
            "criteria": {
                "true": "All stated requirements and requested behavior are accounted for in the supplied description",
                "false": "Critical features are missing, stubbed out, or deviate from requested goals",
            },
        },
        "has_untested_edges": {
            "type": "noul",
            "instructions": "Are there obvious unhandled edge cases, unverified error paths, or missing test evidence in the supplied text?",
            "criteria": {
                "true": "Obvious gaps, unhandled exceptions, or missing validation against edge cases",
                "false": "Supplied text includes clear error-handling and test evidence",
            },
        },
        "quality_score": {
            "type": "score",
            "instructions": "Rate completeness of the supplied evidence from 1 (incomplete) to 5 (thoroughly documented)",
            "criteria": [
                "1 - Severely incomplete, non-functional, or broken",
                "2 - Partial implementation with noticeable defects",
                "3 - Working prototype meeting baseline needs but lacks polish/tests",
                "4 - Solid implementation summary with sound error handling",
                "5 - Thoroughly documented implementation with test evidence",
            ],
        },
        "verdict": {
            "type": "choice",
            "instructions": "Select advisory evidence review status",
            "criteria": {
                "pass": "Supplied evidence is complete and includes test logs",
                "advisory": "Baseline is met in supplied text but minor tests or edge cases remain unverified",
                "reject": "Supplied description is incomplete; missing items must be addressed",
                "insufficient": "Supplied text is insufficient to evaluate completion",
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
            f"Advisory Evidence Review Passed (Index {score:.1f}/4.0): "
            "Supplied description and test logs show no obvious gaps. Does not replace deterministic test execution."
        )
    elif choice_val in ("reject", "insufficient") or sat_prob < 0.60 or score < 1.0:
        status = VerificationStatus.NEEDS_REVISION
        feedback = (
            f"Advisory Evidence Review Flagged Gaps (Index {score:.1f}/4.0, Satisfaction prob: {sat_prob:.2f}): "
            "Supplied description or test evidence is incomplete."
        )
    else:
        status = VerificationStatus.ADVISORY
        feedback = (
            f"Advisory Caution (Index {score:.1f}/4.0, Satisfaction prob: {sat_prob:.2f}): "
            f"Supplied evidence is partial; edge-case or test verification needs review ({edge_prob:.2f})."
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
