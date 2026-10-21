"""
Advisory Pre-Tool Security Gate & Layer-0 Deterministic Reflex Screen.

Combines deterministic regex screening (Layer 0) with System-1 probabilistic
semantic screening (JEV) to provide advisory risk signals before a host executes
shell commands. Execution blocking and permission enforcement remain the
responsibility of the host runtime.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional
from .core import (
    call_jev,
    contains_sensitive_credential,
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


_DESTRUCTIVE_REFLEX_PATTERN = re.compile(
    r"(?i)(?:"
    # POSIX rm variants including separated flags (-r -f), -- option terminator, and root/home/wildcard targets
    r"\brm\b(?:\s+-(?:[rRfFiIv]+|-recursive|-force|-no-preserve-root))+\s+(?:--\s+)?(?:/(?:\s|$|\*)|~(?:/|\s|$)|\*)"
    r"|\bmkfs(?:\.[a-z0-9]+)?\b"
    r"|\bdd\s+if=/dev/(?:zero|random|urandom)\b"
    r"|\bDROP\s+(?:DATABASE|SCHEMA|TABLE)\b"
    r"|\bTRUNCATE\s+TABLE\b"
    # Windows PowerShell & CMD recursive/volume deletion patterns
    r"|\b(?:Format-Volume|Clear-Disk)\b"
    r"|\b(?:Remove-Item|ri|rm|del|erase|rd|rmdir)\b[^\r\n;|]*(?:-Recurse|-Force|/s|/q)[^\r\n;|]*(?:-Recurse|-Force|/s|/q)"
    # Remote script pipe into shell / interpreter
    r"|\b(?:curl|wget|Invoke-WebRequest|iwr|irm)\b[^|;\r\n]*\|\s*(?:(?:ba|z|k)?sh|pwsh|powershell|iex|Invoke-Expression|python[23]?)\b"
    r")"
)


def local_reflex_screen(command: str, context: Optional[str] = None) -> Optional[GuardVerdict]:
    """Layer-0 deterministic reflex screen (0 model tokens).

    Rejects known credential patterns before any external request and flags
    known destructive or remote-pipe shell patterns without invoking a model.
    This screen is a bounded heuristic filter, not a complete shell parser or DLP engine.
    """
    if not isinstance(command, str) or not command.strip() or (context is not None and not isinstance(context, str)):
        raise JevIntegrationError("INPUT_INVALID")
    if contains_sensitive_credential(command) or (context and contains_sensitive_credential(context)):
        raise JevIntegrationError("SENSITIVE_INPUT_REJECTED")
    if _DESTRUCTIVE_REFLEX_PATTERN.search(command):
        is_pipe = bool(re.search(r"(?i)\|\s*(?:(?:ba|z|k)?sh|pwsh|powershell|iex|Invoke-Expression|python[23]?)\b", command))
        return GuardVerdict(
            action=GuardAction.BLOCK,
            is_destructive=True,
            destructive_prob=1.0,
            is_rce_or_exfil=is_pipe,
            rce_prob=1.0 if is_pipe else 0.0,
            is_secret_leak=False,
            secret_prob=0.0,
            overall_confidence=1.0,
            confidence_level=ConfidenceLevel.HIGH,
            summary="Advisory BLOCK by Layer-0 deterministic reflex: matched known destructive or remote-shell pipe pattern.",
            response=None,
            layer0_triggered=True,
        )
    return None


def check_command_safety(command: str, context: Optional[str] = None) -> GuardVerdict:
    """Provide advisory command safety verdict via Layer-0 reflex followed by System-1 evaluation."""
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
            "instructions": "Choose the recommended execution policy for this command",
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
        summary = "Advisory BLOCK: High security risk indicated (destructive, RCE, or credential exposure). Host should block execution."
    elif choice_val in ("caution", "insufficient") or max(dest_prob, rce_prob, sec_prob) >= 0.35:
        action = GuardAction.REQUIRE_CONFIRMATION
        summary = "Advisory REQUIRE_CONFIRMATION: Command modifies system state or presents moderate risk."
    else:
        if level != ConfidenceLevel.HIGH:
            action = GuardAction.REQUIRE_CONFIRMATION
            summary = "Advisory REQUIRE_CONFIRMATION: confidence is absent or below the high descriptive bucket."
        else:
            action = GuardAction.ALLOW
            summary = "Advisory ALLOW: low-risk signal; host execution permissions still apply."

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
