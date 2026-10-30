"""
Dynamic Model & Task Router.

Classifies task complexity in milliseconds to route coding requests across Fast,
Standard, and Deep Reasoning tiers while estimating architectural blast radius.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from .core import (
    call_jev,
    ConfidenceLevel,
    JevResponse,
    JevIntegrationError,
    validate_typed_answers,
    get_confidence_level,
)


class ModelTier(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP_REASONING = "deep_reasoning"


@dataclass
class RouteVerdict:
    tier: ModelTier
    complexity_score: float
    requires_architecture: bool
    recommended_models: List[str]
    confidence: Optional[float]
    confidence_level: ConfidenceLevel
    rationale: str
    response: JevResponse


TIER_MODELS = {
    ModelTier.FAST: ["gpt-4o-mini", "codex-mini-latest", "gemini-2.5-flash", "claude-3-5-haiku"],
    ModelTier.STANDARD: ["gpt-4.1", "gpt-4o", "claude-3-7-sonnet", "gemini-2.5-pro"],
    ModelTier.DEEP_REASONING: ["o3", "o4-mini", "codex-1", "claude-3-7-sonnet-thinking"],
}


def route_task(task_description: str, context: Optional[str] = None) -> RouteVerdict:
    """Sub-second evaluation of incoming coding task complexity and model tier routing."""
    if (
        not isinstance(task_description, str)
        or not task_description.strip()
        or (context is not None and not isinstance(context, str))
    ):
        raise JevIntegrationError("INPUT_INVALID")
    state_parts = [f"Task Request:\n```\n{task_description.strip()}\n```"]
    if context:
        state_parts.append(f"Repository / Context Info:\n{context.strip()}")
    state = "\n\n".join(state_parts)

    questions = {
        "tier": {
            "type": "choice",
            "instructions": "Select the required model capability tier for this task",
            "criteria": {
                "fast": "Simple formatting, single-line edits, direct translations, routine queries, or basic syntax fixes",
                "standard": "Typical software feature development, unit testing, component refactoring, or clear API integration",
                "deep_reasoning": "High-complexity algorithms, distributed consensus, tricky concurrency bugs, system architecture redesign, or heavy mathematical proofs",
                "insufficient": "Insufficient information to recommend a model change",
            },
        },
        "is_architectural": {
            "type": "noul",
            "instructions": "Does this task require multi-file architectural planning or structural system changes?",
            "criteria": {
                "true": "Affects multi-module architecture, protocols, or core data structures across the repository",
                "false": "Localized to a single file, isolated function, or straightforward documentation/formatting",
            },
        },
        "difficulty_score": {
            "type": "score",
            "instructions": "Score overall technical difficulty from 1 (trivial) to 5 (extreme complexity)",
            "criteria": [
                "1 - Trivial / straightforward boilerplate",
                "2 - Standard feature work with known patterns",
                "3 - Moderate complexity requiring careful logic",
                "4 - High complexity with edge cases and race conditions",
                "5 - Research-level, novel architecture, or extreme algorithmic challenge",
            ],
        },
    }

    resp = call_jev(state, questions)
    validate_typed_answers(resp, questions)
    tier_ans = resp.answers["tier"]
    arch_ans = resp.answers["is_architectural"]
    diff_ans = resp.answers["difficulty_score"]

    tier_selected = tier_ans.selected
    conf = tier_ans.confidence
    level = get_confidence_level(conf)
    arch_prob = arch_ans.probability
    score = diff_ans.score

    if tier_selected == "deep_reasoning" or score >= 2.8:
        tier = ModelTier.DEEP_REASONING
        rationale = f"Deep reasoning tier selected (difficulty: {score:.1f}/4.0, architectural: {arch_prob >= 0.5})."
    elif tier_selected == "fast" and level == ConfidenceLevel.HIGH and score <= 0.8 and arch_prob < 0.3:
        tier = ModelTier.FAST
        rationale = f"Fast execution tier selected (difficulty: {score:.1f}/4.0, localized task)."
    else:
        tier = ModelTier.STANDARD
        rationale = f"Standard tier selected (difficulty: {score:.1f}/4.0)."

    return RouteVerdict(
        tier=tier,
        complexity_score=score,
        requires_architecture=arch_prob >= 0.5,
        recommended_models=(
            TIER_MODELS.get(tier, [])
            if tier_selected != "insufficient" and level == ConfidenceLevel.HIGH
            else []
        ),
        confidence=conf,
        confidence_level=level,
        rationale=rationale,
        response=resp,
    )


@dataclass
class AutopilotPlan:
    tier: ModelTier
    reasoning_effort: str
    context_tier: str
    selected_model: str
    fallback_models: List[str]
    rationale: str


def autopilot_select(task_description: str, context_chars: int = 0) -> AutopilotPlan:
    """Zero-config offline autopilot selector for model tier, reasoning_effort, and context fit."""
    if not isinstance(task_description, str) or not task_description.strip() or context_chars < 0:
        raise JevIntegrationError("INPUT_INVALID")

    text = task_description.lower()
    total_chars = len(task_description) + int(context_chars)

    if total_chars >= 120_000:
        context_tier = "long_context"
    elif total_chars >= 16_000:
        context_tier = "medium"
    else:
        context_tier = "short"

    deep_keywords = (
        "architecture", "consensus", "raft", "deadlock", "concurrency", "race condition",
        "security audit", "cryptograph", "zero-downtime", "distributed", "theorem", "proof",
    )
    fast_keywords = (
        "typo", "format", "rename", "docstring", "comment", "translate", "lint", "readme",
    )

    if any(k in text for k in deep_keywords) or context_tier == "long_context":
        tier = ModelTier.DEEP_REASONING
        effort = "high"
    elif any(k in text for k in fast_keywords) and context_tier == "short" and len(task_description) < 240:
        tier = ModelTier.FAST
        effort = "low"
    else:
        tier = ModelTier.STANDARD
        effort = "medium"

    candidates = TIER_MODELS[tier]
    return AutopilotPlan(
        tier=tier,
        reasoning_effort=effort,
        context_tier=context_tier,
        selected_model=candidates[0],
        fallback_models=candidates[1:],
        rationale=f"Autopilot selected {tier.value} (reasoning_effort={effort}, context_tier={context_tier}).",
    )
