"""Typed adapter for System-1 probabilistic evaluation; zero direct credential handling.

One invocation makes at most one request. Errors, partial answers, and missing
confidence are explicit; they are never silently coerced into safe decisions.
"""
import importlib.util
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

DEFAULT_MODEL = "~typesafe/jev-latest"


def _resolve_bridge_dir() -> Path:
    env_dir = os.environ.get("JEV_BRIDGE_DIR")
    if env_dir:
        return Path(env_dir)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "JevBridge" / "runtime"
    return Path.home() / ".local" / "share" / "JevBridge" / "runtime"


def _resolve_bridge_python() -> Path:
    env_py = os.environ.get("JEV_PYTHON")
    if env_py:
        return Path(env_py)
    return Path(sys.executable)


class JevIntegrationError(RuntimeError):
    def __init__(self, code: str, *, billing_uncertain: bool = False):
        self.code = code
        self.billing_uncertain = billing_uncertain
        super().__init__(f"JEV {code}; billing_uncertain={billing_uncertain}; no automatic retry")


class ConfidenceLevel(str, Enum):
    """Descriptive confidence buckets, not calibrated accuracy or execution authority."""
    HIGH = "high"
    MID = "mid"
    LOW = "low"
    UNKNOWN = "unknown"


def get_confidence_level(confidence: Optional[float]) -> ConfidenceLevel:
    if confidence is None:
        return ConfidenceLevel.UNKNOWN
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise JevIntegrationError("RESPONSE_INVALID")
    if confidence >= 0.85:
        return ConfidenceLevel.HIGH
    if confidence >= 0.55:
        return ConfidenceLevel.MID
    return ConfidenceLevel.LOW


@dataclass
class NoulDecision:
    probability: float
    is_true: bool
    confidence: Optional[float] = None
    level: ConfidenceLevel = ConfidenceLevel.UNKNOWN


@dataclass
class ChoiceDecision:
    selected: str
    probabilities: Dict[str, float]
    confidence: Optional[float]
    level: ConfidenceLevel


@dataclass
class ScoreDecision:
    score: float  # zero-based index over the ordered criteria
    probabilities: Dict[str, float]
    confidence: Optional[float]
    level: ConfidenceLevel


@dataclass
class JevUsage:
    input_tokens: int
    output_tokens: int
    cost: Optional[float]


@dataclass
class JevResponse:
    id: Optional[str]
    model: str
    provider: Optional[str]
    usage: JevUsage
    raw: Dict[str, Any]
    answers: Dict[str, Union[NoulDecision, ChoiceDecision, ScoreDecision]]


def _unique_object(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError(f"Duplicate JSON key: {k}")
        obj[k] = v
    return obj


def _reject_constant(val):
    raise ValueError(f"Invalid JSON constant: {val}")


def _is_finite_number(val: Any) -> bool:
    return type(val) in (int, float) and math.isfinite(val)


def _validate_questions_builtin(questions: Dict[str, Any]) -> None:
    if type(questions) is not dict or not questions:
        raise JevIntegrationError("INPUT_INVALID")
    for key, spec in questions.items():
        if not isinstance(key, str) or not key.strip() or type(spec) is not dict:
            raise JevIntegrationError("INPUT_INVALID")
        qtype = spec.get("type")
        instructions = spec.get("instructions")
        criteria = spec.get("criteria")
        if not isinstance(instructions, str) or not instructions.strip():
            raise JevIntegrationError("INPUT_INVALID")
        if qtype == "noul":
            if type(criteria) is not dict or set(criteria.keys()) != {"true", "false"}:
                raise JevIntegrationError("INPUT_INVALID")
            if not all(isinstance(v, str) and v.strip() for v in criteria.values()):
                raise JevIntegrationError("INPUT_INVALID")
        elif qtype == "choice":
            if type(criteria) is not dict or len(criteria) < 2:
                raise JevIntegrationError("INPUT_INVALID")
            if not all(isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
                       for k, v in criteria.items()):
                raise JevIntegrationError("INPUT_INVALID")
        elif qtype == "score":
            if type(criteria) is not list or len(criteria) < 2:
                raise JevIntegrationError("INPUT_INVALID")
            if not all(isinstance(v, str) and v.strip() for v in criteria):
                raise JevIntegrationError("INPUT_INVALID")
        else:
            raise JevIntegrationError("INPUT_INVALID")


def _validate_response_builtin(raw: Dict[str, Any], questions: Dict[str, Any]) -> None:
    if type(raw) is not dict:
        raise JevIntegrationError("RESPONSE_INVALID")
    model = raw.get("model")
    if not isinstance(model, str) or not model.strip():
        raise JevIntegrationError("RESPONSE_INVALID")
    usage = raw.get("usage")
    if type(usage) is not dict:
        raise JevIntegrationError("RESPONSE_INVALID")
    in_tok = usage.get("input_tokens")
    out_tok = usage.get("output_tokens")
    cost = usage.get("cost")
    if type(in_tok) is not int or in_tok < 0 or type(out_tok) is not int or out_tok < 0:
        raise JevIntegrationError("RESPONSE_INVALID")
    if cost is not None and (not _is_finite_number(cost) or cost < 0):
        raise JevIntegrationError("RESPONSE_INVALID")
    answers = raw.get("answers")
    if type(answers) is not dict or set(answers.keys()) != set(questions.keys()):
        raise JevIntegrationError("RESPONSE_INVALID")

    for key, spec in questions.items():
        item = answers.get(key)
        if type(item) is not dict or item.get("type") != spec["type"]:
            raise JevIntegrationError("RESPONSE_INVALID")
        qtype = spec["type"]
        conf = item.get("confidence")
        if conf is not None and (not _is_finite_number(conf) or not 0 <= conf <= 1):
            raise JevIntegrationError("RESPONSE_INVALID")
        if qtype == "noul":
            prob = item.get("noul")
            if not _is_finite_number(prob) or not 0 <= prob <= 1:
                raise JevIntegrationError("RESPONSE_INVALID")
        elif qtype == "choice":
            choice = item.get("choice")
            if choice not in spec["criteria"]:
                raise JevIntegrationError("RESPONSE_INVALID")
            probs = item.get("probabilities", {})
            if type(probs) is not dict:
                raise JevIntegrationError("RESPONSE_INVALID")
            for k, p in probs.items():
                if k not in spec["criteria"] or not _is_finite_number(p) or not 0 <= p <= 1:
                    raise JevIntegrationError("RESPONSE_INVALID")
        elif qtype == "score":
            score = item.get("score")
            max_idx = len(spec["criteria"]) - 1
            if not _is_finite_number(score) or not 0 <= score <= max_idx:
                raise JevIntegrationError("RESPONSE_INVALID")
            probs = item.get("probabilities", {})
            if type(probs) is not dict:
                raise JevIntegrationError("RESPONSE_INVALID")
            for _, p in probs.items():
                if not _is_finite_number(p) or not 0 <= p <= 1:
                    raise JevIntegrationError("RESPONSE_INVALID")


def validate_typed_answers(resp: JevResponse, questions: Dict[str, Any]) -> None:
    """Defend policy consumers against malformed injected/custom responses."""
    if not isinstance(resp, JevResponse):
        raise JevIntegrationError("RESPONSE_INVALID")
    _validate_questions_builtin(questions)
    answers = {}
    for key, value in resp.answers.items():
        if isinstance(value, NoulDecision):
            item: Dict[str, Any] = {"type": "noul", "noul": value.probability}
        elif isinstance(value, ChoiceDecision):
            item = {"type": "choice", "choice": value.selected, "probabilities": value.probabilities}
        elif isinstance(value, ScoreDecision):
            item = {"type": "score", "score": value.score, "probabilities": value.probabilities}
        else:
            raise JevIntegrationError("RESPONSE_INVALID")
        if value.confidence is not None:
            item["confidence"] = value.confidence
        answers[key] = item
    usage: Dict[str, Any] = {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }
    if resp.usage.cost is not None:
        usage["cost"] = resp.usage.cost
    _validate_response_builtin({"model": resp.model, "answers": answers, "usage": usage}, questions)


def _invoke_bridge(payload: bytes, timeout: float) -> dict:
    bridge_dir = _resolve_bridge_dir()
    bridge_python = _resolve_bridge_python()
    cli = bridge_dir / "jev_cli.py"
    if not cli.is_file() or not bridge_python.is_file():
        raise JevIntegrationError("BRIDGE_MISSING")
    try:
        result = subprocess.run(
            [str(bridge_python), "-B", "-X", "utf8", str(cli), "--request-stdin", "--live"],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise JevIntegrationError("TIMEOUT", billing_uncertain=True) from None
    except OSError:
        raise JevIntegrationError("BRIDGE_START_FAILED") from None
    try:
        if len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError("response size")
        envelope = json.loads(
            result.stdout,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeError):
        raise JevIntegrationError("BRIDGE_RESPONSE_INVALID", billing_uncertain=True) from None
    if type(envelope) is not dict:
        raise JevIntegrationError("BRIDGE_RESPONSE_INVALID", billing_uncertain=True)
    if result.returncode or envelope.get("ok") is not True:
        error = envelope.get("error")
        error = error if type(error) is dict else {}
        safe_codes = {
            "INPUT_INVALID", "REQUEST_TOO_LARGE", "RESPONSE_INVALID",
            "CREDENTIAL_MISSING", "CREDENTIAL_ACCESS_PENDING", "LOCAL_ERROR",
            "CREDENTIAL_NOT_AUTHORIZED", "TIMEOUT", "NETWORK_ERROR", "BRIDGE_FAILED",
        }
        code = error.get("code")
        raise JevIntegrationError(
            code if code in safe_codes else "BRIDGE_FAILED",
            billing_uncertain=error.get("billing_uncertain") is not False,
        )
    return envelope.get("response")


def call_jev(
    state: Union[str, Dict[str, Any], list],
    questions: Dict[str, Any],
    api_key: Any = None,
    model: str = DEFAULT_MODEL,
    timeout: float = 45.0,
    transport: Optional[Callable[[bytes, float], dict]] = None,
) -> JevResponse:
    """Send minimal authorized input through JevBridge, at most once per call.

    Explicit key injection is rejected by design: only the isolated bridge
    controls credential access.
    """
    if api_key is not None:
        raise JevIntegrationError("DIRECT_CREDENTIALS_DISABLED")
    if model != DEFAULT_MODEL or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise JevIntegrationError("INPUT_INVALID")
    _validate_questions_builtin(questions)
    if type(state) not in (str, dict, list) or (isinstance(state, str) and not state.strip()):
        raise JevIntegrationError("INPUT_INVALID")
    try:
        payload = json.dumps(
            {"state": state, "questions": questions},
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError):
        raise JevIntegrationError("INPUT_INVALID") from None
    if len(payload) > 262144:
        raise JevIntegrationError("REQUEST_TOO_LARGE")

    sent_questions = json.loads(payload)["questions"]
    invoker = transport if transport is not None else _invoke_bridge
    raw = invoker(payload, timeout)
    _validate_response_builtin(raw, sent_questions)

    answers: Dict[str, Union[NoulDecision, ChoiceDecision, ScoreDecision]] = {}
    for key, item in raw["answers"].items():
        kind = item["type"]
        confidence = item.get("confidence")
        if kind == "noul":
            answers[key] = NoulDecision(item["noul"], item["noul"] >= 0.5)
        elif kind == "choice":
            answers[key] = ChoiceDecision(
                item["choice"],
                item.get("probabilities", {}),
                confidence,
                get_confidence_level(confidence),
            )
        else:
            answers[key] = ScoreDecision(
                item["score"],
                item.get("probabilities", {}),
                confidence,
                get_confidence_level(confidence),
            )
    usage = raw["usage"]
    return JevResponse(
        raw.get("id"),
        raw["model"],
        raw.get("provider"),
        JevUsage(usage["input_tokens"], usage["output_tokens"], usage.get("cost")),
        raw,
        answers,
    )
