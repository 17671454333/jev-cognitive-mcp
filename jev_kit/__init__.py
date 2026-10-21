"""
JevKit (jev-cognitive-mcp) - 3+1 Cognitive Architecture & Advisory MCP Toolkit

Implements an advisory 3+1 cognitive hierarchy for coding agents (Codex, Claude Code, Cursor):
- Layer 0 (Deterministic Reflex): Regex DLP screening, destructive command pattern detection, schema validation
- System 1 (Fast Intuition / JEV): Advisory probabilistic classification, routing, and candidate ranking
- System 2 (Deep Reasoning / Host LLM): Complex causal reasoning, architecture design, and host-enforced execution
- Meta-Controller: 5-factor arbitration (Confidence, Risk, Reversibility, Value, Cost)
"""

__version__ = "0.3.1"

from .core import (
    call_jev,
    contains_sensitive_credential,
    JevIntegrationError,
    ConfidenceLevel,
    NoulDecision,
    ChoiceDecision,
    ScoreDecision,
    JevResponse,
    JevUsage,
    get_confidence_level,
    validate_typed_answers,
)
from .guard import (
    check_command_safety,
    local_reflex_screen,
    GuardVerdict,
    GuardAction,
)
from .router import (
    route_task,
    RouteVerdict,
    ModelTier,
)
from .verifier import (
    verify_completion,
    VerificationVerdict,
    VerificationStatus,
)
from .reranker import (
    rerank,
    ScoredItem,
    RerankError,
)
from .controller import (
    arbitrate_escalation,
    CognitiveLayer,
    ControllerSignals,
    ArbitrationDecision,
)

__all__ = [
    "__version__",
    "call_jev",
    "contains_sensitive_credential",
    "JevIntegrationError",
    "ConfidenceLevel",
    "NoulDecision",
    "ChoiceDecision",
    "ScoreDecision",
    "JevResponse",
    "JevUsage",
    "get_confidence_level",
    "validate_typed_answers",
    "check_command_safety",
    "local_reflex_screen",
    "GuardVerdict",
    "GuardAction",
    "route_task",
    "RouteVerdict",
    "ModelTier",
    "verify_completion",
    "VerificationVerdict",
    "VerificationStatus",
    "rerank",
    "ScoredItem",
    "RerankError",
    "arbitrate_escalation",
    "CognitiveLayer",
    "ControllerSignals",
    "ArbitrationDecision",
]
