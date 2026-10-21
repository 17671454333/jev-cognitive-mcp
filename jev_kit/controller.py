"""
Meta-Controller: 3+1 Cognitive Hierarchy Arbitration Engine.

Arbitrates whether a task remains at Layer 0 (Deterministic Reflex), stays in
System 1 (Fast Intuition / JEV), or escalates to System 2 (Deep Reasoning LLM)
based on 5 quantitative parameters:
1. Confidence (0.0 .. 1.0)
2. Risk (0.0 .. 1.0)
3. Reversibility (True = two-way door, False = one-way door)
4. Expected Value of deep reasoning (0.0 .. 1.0)
5. Computational Cost budget pressure (0.0 .. 1.0)
"""

from dataclasses import dataclass
from enum import Enum
import math
from typing import List
from .core import JevIntegrationError


class CognitiveLayer(str, Enum):
    LAYER_0_REFLEX = "layer_0_reflex"
    SYSTEM_1_INTUITION = "system_1_intuition"
    SYSTEM_2_REASONING = "system_2_reasoning"
    HUMAN_GATE = "human_gate"


@dataclass
class ControllerSignals:
    confidence: float
    risk: float
    reversible: bool
    expected_value: float = 0.5
    cost_pressure: float = 0.2
    deterministic_match: bool = False
    requires_causal_proof: bool = False


@dataclass
class ArbitrationDecision:
    target_layer: CognitiveLayer
    escalate_to_system2: bool
    require_human_approval: bool
    utility_score: float
    triggers: List[str]
    rationale: str


def _validate_unit_float(val: float, name: str) -> None:
    if type(val) not in (int, float) or not math.isfinite(val) or not 0.0 <= val <= 1.0:
        raise JevIntegrationError(f"INVALID_SIGNAL_{name.upper()}")


def arbitrate_escalation(signals: ControllerSignals) -> ArbitrationDecision:
    """Deterministic 5-factor meta-controller arbitration."""
    if not isinstance(signals, ControllerSignals):
        raise JevIntegrationError("INPUT_INVALID")
    _validate_unit_float(signals.confidence, "confidence")
    _validate_unit_float(signals.risk, "risk")
    _validate_unit_float(signals.expected_value, "expected_value")
    _validate_unit_float(signals.cost_pressure, "cost_pressure")
    if not isinstance(signals.reversible, bool) or not isinstance(signals.deterministic_match, bool):
        raise JevIntegrationError("INPUT_INVALID")

    triggers: List[str] = []

    # 1. Hard safety boundary: irreversible + high risk requires explicit human gate
    if not signals.reversible and signals.risk >= 0.70:
        triggers.append("one_way_door_high_risk")
        return ArbitrationDecision(
            target_layer=CognitiveLayer.HUMAN_GATE,
            escalate_to_system2=True,
            require_human_approval=True,
            utility_score=1.0,
            triggers=triggers,
            rationale="Irreversible (one-way door) operation with high risk requires System-2 review and human authorization.",
        )

    # 2. Layer 0 direct dispatch when deterministic rule matches and risk is low
    if signals.deterministic_match and signals.risk < 0.35 and signals.reversible:
        triggers.append("deterministic_reflex_match")
        return ArbitrationDecision(
            target_layer=CognitiveLayer.LAYER_0_REFLEX,
            escalate_to_system2=False,
            require_human_approval=False,
            utility_score=0.0,
            triggers=triggers,
            rationale="Deterministic Layer-0 rule matched on reversible low-risk action; zero model invocation required.",
        )

    # 3. Rigid System-2 escalation triggers
    if signals.confidence < 0.75:
        triggers.append("low_system1_confidence")
    if not signals.reversible:
        triggers.append("irreversible_one_way_door")
    if signals.risk >= 0.60:
        triggers.append("high_error_cost")
    if signals.requires_causal_proof:
        triggers.append("requires_causal_reasoning")

    # Expected Net Gain of escalating to System 2:
    # combines uncertainty (1 - confidence), risk weight, and expected value minus cost pressure
    uncertainty = 1.0 - signals.confidence
    utility = (0.45 * uncertainty) + (0.35 * signals.risk) + (0.30 * signals.expected_value) - (0.20 * signals.cost_pressure)
    utility = max(0.0, min(1.0, round(utility, 4)))

    if triggers or utility >= 0.45:
        if not triggers:
            triggers.append("positive_escalation_utility")
        return ArbitrationDecision(
            target_layer=CognitiveLayer.SYSTEM_2_REASONING,
            escalate_to_system2=True,
            require_human_approval=not signals.reversible and signals.risk >= 0.50,
            utility_score=utility,
            triggers=triggers,
            rationale=f"Escalated to System 2 (utility={utility:.2f}, triggers={', '.join(triggers)}).",
        )

    return ArbitrationDecision(
        target_layer=CognitiveLayer.SYSTEM_1_INTUITION,
        escalate_to_system2=False,
        require_human_approval=False,
        utility_score=utility,
        triggers=["high_confidence_reversible"],
        rationale=f"Retained in System 1 fast intuition path (confidence={signals.confidence:.2f}, utility={utility:.2f}).",
    )
