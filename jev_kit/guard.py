"""
Pre-Tool Security Gate & Layer-0 Deterministic Reflex Screen.

Combines deterministic regex screening (Layer 0) with System-1 probabilistic
semantic screening (JEV) before an agent executes shell commands.
Advisory semantic screening never overrides host permission boundaries.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional
from .core import (
    call_jev,
    ConfidenceLevel,
    JevResponse,
    JevIntegrationError,
    validate_typed_answers,
    get_confidence_level,
)


class GuardAction(str, Enum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"


@dataclass
class GuardVerdict:
    action: GuardAction
    is_destructive: bool
    destructive_prob: float
    is_rce_or_exfil: bool
    rce_prob: float
    is_secret_leak: bool
    secret_prob: float
    overall_confidence: Optional[float]
    confidence_level: ConfidenceLevel
    summary: str
    response: Optional[JevResponse] = None
    layer0_triggered: bool = False


_SENSITIVE_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\bsk-(?:or-|proj-)?[A-Za-z0-9_-]{12,}"
    r"|\bgh[pousr]_[A-Za-z0-9_]{20,}"
    r"|\bBearer\s+[A-Za-z0-9._~+/-]{12,}"
    r"|(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*['\"][^'\"]+['\"]"
)

_DESTRUCTIVE_REFLEX_PATTERN = re.compile(
    r"(?i)(?:\brm\s+-[rRfF]*\s+/(?:\s|$|\*)"
    r"|\bmkfs(?:\.[a-z0-9]+)?\b"
    r"|\bdd\s+if=/dev/(?:zero|random|urandom)\b"
    r"|\bDROP\s+(?:DATABASE|SCHEMA|TABLE)\b"
    r"|\bTRUNCATE\s+TABLE\b"
    r"|\bFormat-Volume\b"
    r"|\bcurl\b[^|;]*\|\s*(?:ba)?sh\b"
    r"|\bwget\b[^|;]*\|\s*(?:ba)?sh\b)"
)


def local_reflex_screen(command: str, context: Optional[str] = None) -> Optional[GuardVerdict]:
    """Layer-0 deterministic reflex screen (<1ms, 0 tokens).

    Rejects raw credential egress immediately and blocks unambiguous destructive
    or remote-pipe patterns without invoking any model.
    """
    if not isinstance(command, str) or not command.strip() or (context is not None and not isinstance(context, str)):
        raise JevIntegrationError("INPUT_INVALID")
    if _SENSITIVE_CREDENTIAL_PATTERN.search(command) or (context and _SENSITIVE_CREDENTIAL_PATTERN.search(context)):
        raise JevIntegrationError("SENSITIVE_INPUT_REJECTED")
    if _DESTRUCTIVE_REFLEX_PATTERN.search(command):
        return GuardVerdict(
            action=GuardAction.BLOCK,
            is_destructive=True,
            destructive_prob=1.0,
            is_rce_or_exfil=bool(re.search(r"(?i)\|\s*(?:ba)?sh\b", command)),
            rce_prob=1.0 if re.search(r"(?i)\|\s*(?:ba)?sh\b", command) else 0.0,
            is_secret_leak=False,
            secret_prob=0.0,
            overall_confidence=1.0,
            confidence_level=ConfidenceLevel.HIGH,
            summary="Blocked by Layer-0 deterministic reflex: high-risk destructive or remote shell pipe pattern.",
            response=None,
            layer0_triggered=True,
        )
    return None


def check_command_safety(command: str, context: Optional[str] = None) -> GuardVerdict:
    """Screen command safety via Layer-0 reflex followed by System-1 probabilistic evaluation."""
    reflex = local_reflex_screen(command, context)
    if reflex is not None:
        return reflex

    state_parts = [f"Command to execute:\n```\n{command.strip()}\n```"]
    if context:
        state_parts.append(f"Context / Rationale:\n{context.strip()}")
    state = "\n\n".join(state_parts)

    questions = {
        "is_destructive": {
            "type": "noul",
            "instructions": "Does this command irreversibly delete files, wipe partitions, drop databases, or overwrite unrecoverable assets?",
            "criteria": {
                "true": "Destroys, removes, truncates, or overwrites persistent data irreversibly",
                "false": "Read-only, additive, or recoverable standard modifications",
            },
        },
        "is_rce_or_exfil": {
            "type": "noul",
            "instructions": "Does this command execute arbitrary remote code or exfiltrate private files/data over the network?",
            "criteria": {
                "true": "Pipes remote scripts into shell, sends private data to external endpoints, or bypasses network controls",
                "false": "Standard package installs, harmless curl/git fetch, or local operations",
            },
        },
        "is_secret_leak": {
            "type": "noul",
            "instructions": "Does this command expose or print raw secrets, tokens, private keys, or credentials in plain text?",
            "criteria": {
                "true": "Outputs, dumps, or transmits unmasked API keys, passwords, or credentials",
                "false": "No credential exposure or handles masked/environment references safely",
            },
        },
        "decision": {
            "type": "choice",
            "instructions": "Choose the required execution policy for this command",
            "criteria": {
                "safe": "Standard harmless dev command (git status, pytest, ls, harmless compiles)",
                "caution": "Modifying commands that need user awareness (file edits, migrations, installs)",
                "dangerous": "High risk destructive deletion, malicious payload, or critical resource termination",
                "insufficient": "Not enough evidence to establish safety",
            },
        },
    }

    resp = call_jev(state, questions)
    validate_typed_answers(resp, questions)
    dest_ans = resp.answers["is_destructive"]
    rce_ans = resp.answers["is_rce_or_exfil"]
    sec_ans = resp.answers["is_secret_leak"]
    dec_ans = resp.answers["decision"]

    dest_prob = dest_ans.probability
    rce_prob = rce_ans.probability
    sec_prob = sec_ans.probability
    choice_val = dec_ans.selected
    conf = dec_ans.confidence
    level = get_confidence_level(conf)

    if choice_val == "dangerous" or dest_prob >= 0.70 or rce_prob >= 0.65 or sec_prob >= 0.65:
        action = GuardAction.BLOCK
        summary = "Blocked: High security risk detected (destructive, RCE, or credential exposure)."
    elif choice_val in ("caution", "insufficient") or max(dest_prob, rce_prob, sec_prob) >= 0.35:
        action = GuardAction.REQUIRE_CONFIRMATION
        summary = "Confirmation required: Command modifies system state or presents moderate risk."
    else:
        if level != ConfidenceLevel.HIGH:
            action = GuardAction.REQUIRE_CONFIRMATION
            summary = "Review required: confidence is absent or below the high descriptive bucket."
        else:
            action = GuardAction.ALLOW
            summary = "Low-risk advisory result; existing execution permissions still apply."

    return GuardVerdict(
        action=action,
        is_destructive=dest_prob >= 0.5,
        destructive_prob=dest_prob,
        is_rce_or_exfil=rce_prob >= 0.5,
        rce_prob=rce_prob,
        is_secret_leak=sec_prob >= 0.5,
        secret_prob=sec_prob,
        overall_confidence=conf,
        confidence_level=level,
        summary=summary,
        response=resp,
        layer0_triggered=False,
    )
