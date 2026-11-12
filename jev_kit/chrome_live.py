"""
Chrome M144+ Live Session Discovery & Layer-0 CDP Action Guard (`jev_kit.chrome_live`)
--------------------------------------------------------------------------------------
Provides two deterministic, zero-popup capabilities for browser-enabled coding agents:
1. `discover_devtools_active_port`: Reads Chrome M144+ `DevToolsActivePort` across
   Windows/macOS/Linux without initiating a transient WebSocket handshake (avoiding
   repeated Chrome 'Allow remote debugging?' modal popups).
2. `screen_cdp_action`: Layer-0 deterministic security & DLP pre-screening for
   Chrome DevTools Protocol (CDP) commands (`Runtime.evaluate`, `DOM.setFileInputFiles`,
   `Page.navigate`, `Network.setExtraHTTPHeaders`) before forwarding to a persistent
   local CDP bridge (`http://127.0.0.1:19876`).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

from .core import JevIntegrationError, contains_sensitive_credential
from .guard import GuardAction

_SENSITIVE_UPLOAD_FILE_PATTERN = re.compile(
    r"(?:^|[/\\])(?:"
    r"\.env(?:\.[a-zA-Z0-9._-]+)?|"
    r"id_(?:rsa|ed25519|ecdsa|dsa)(?:\.pub)?|"
    r"credentials(?:\.json|\.db|\.xml)?|"
    r"\.git-credentials|"
    r"\.npmrc|\.pypirc|\.netrc|"
    r"cookies\.sqlite|Login\s*Data|Local\s*State|Web\s*Data|"
    r"terraform\.tfstate(?:\.backup)?|\.kube[/\\]config|kubeconfig|"
    r"[^/\\]+\.(?:pem|key|pfx|p12|kdbx)"
    r")$",
    re.IGNORECASE,
)

_FORBIDDEN_BROWSER_TARGET_PATTERN = re.compile(
    r"(?:"
    r"^chrome://(?:settings/passwords|password-manager|omnibox|extensions)|"
    r"^(?:edge|brave)://(?:wallet|passwords|settings/passwords)|"
    r"^file://+(?:etc/(?:passwd|shadow)|windows/system32/config)|"
    r"^file://+.*?(?:User\s*Data|google-chrome|chromium).*?(?:Login\s*Data|Cookies|Local\s*State|Web\s*Data)|"
    r"^https?://169\.254\.169\.254(?:/|$)|"
    r"^https?://(?:\[fd00:ec2::254\]|100\.100\.100\.200)(?:/|$)|"
    r"^https?://metadata\.google\.internal(?:/|$)"
    r")",
    re.IGNORECASE,
)

_BULK_COOKIE_DUMP_METHODS = frozenset({
    "Network.getAllCookies",
    "Storage.getCookies",
})

_COOKIE_EXFIL_EXPR_PATTERN = re.compile(
    r"(?is)document\.cookie.*?(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket)\s*\()"
    r"|(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket)\s*\().*?document\.cookie"
)

_WEB_STORAGE_EXFIL_EXPR_PATTERN = re.compile(
    r"(?is)(?:\blocalStorage\b|\bsessionStorage\b).*?(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket)\s*\()"
    r"|(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket)\s*\().*?(?:\blocalStorage\b|\bsessionStorage\b)"
)


@dataclass
class ChromeLiveEndpoint:
    found: bool
    port: Optional[int]
    ws_path: Optional[str]
    ws_url: Optional[str]
    active_port_file: str
    bridge_http_url: str = "http://127.0.0.1:19876"


@dataclass
class CdpGuardVerdict:
    action: GuardAction
    method: str
    safe: bool
    layer0_triggered: bool
    reasons: List[str] = field(default_factory=list)
    recommended_params: Dict[str, Any] = field(default_factory=dict)


def default_devtools_port_paths() -> List[Path]:
    """Return platform-ordered candidate paths for Chrome's DevToolsActivePort file."""
    candidates: List[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Google" / "Chrome" / "User Data" / "DevToolsActivePort")
    home = Path.home()
    if sys.platform == "darwin":
        candidates.append(home / "Library" / "Application Support" / "Google" / "Chrome" / "DevToolsActivePort")
    candidates.append(home / ".config" / "google-chrome" / "DevToolsActivePort")
    candidates.append(home / ".config" / "chromium" / "DevToolsActivePort")
    return candidates


def discover_devtools_active_port(custom_path: Optional[str] = None) -> ChromeLiveEndpoint:
    """
    Parse Chrome M144+ `DevToolsActivePort` without opening a WebSocket connection.
    Line 1: TCP port (e.g., 9222)
    Line 2: Browser WebSocket path (e.g., /devtools/browser/<uuid>)
    """
    paths = [Path(os.path.expandvars(custom_path))] if custom_path else default_devtools_port_paths()
    for p in paths:
        if p.is_file():
            lines = [ln.strip() for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            if len(lines) >= 2 and lines[0].isdigit():
                port = int(lines[0])
                ws_path = lines[1] if lines[1].startswith("/") else f"/{lines[1]}"
                return ChromeLiveEndpoint(
                    found=True,
                    port=port,
                    ws_path=ws_path,
                    ws_url=f"ws://127.0.0.1:{port}{ws_path}",
                    active_port_file=str(p),
                )
    fallback = str(paths[0]) if paths else "DevToolsActivePort"
    return ChromeLiveEndpoint(
        found=False,
        port=None,
        ws_path=None,
        ws_url=None,
        active_port_file=fallback,
    )


def screen_cdp_action(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    target_url: Optional[str] = None,
) -> CdpGuardVerdict:
    """
    Deterministic Layer-0 security & DLP guard for Chrome DevTools Protocol (CDP) actions.
    - Rejects raw secrets/tokens in CDP parameters (`SENSITIVE_INPUT_REJECTED`).
    - Blocks `DOM.setFileInputFiles` when sensitive dotfiles/private keys are included.
    - Blocks `Page.navigate` to cloud metadata SSRF or browser password manager URLs.
    - Injects `userGesture=True` recommendation on `Runtime.evaluate` popup/navigation calls.
    """
    clean_params = dict(params or {})
    serialized = json.dumps({"method": method, "params": clean_params, "target_url": target_url or ""}, ensure_ascii=False)
    if contains_sensitive_credential(serialized):
        raise JevIntegrationError("SENSITIVE_INPUT_REJECTED", billing_uncertain=False)

    reasons: List[str] = []
    if method in _BULK_COOKIE_DUMP_METHODS:
        reasons.append(f"CDP method '{method}' blocked: bulk cross-domain cookie harvesting is prohibited.")

    if target_url and _FORBIDDEN_BROWSER_TARGET_PATTERN.search(target_url.strip()):
        reasons.append(f"Target URL '{target_url}' matches restricted browser/metadata endpoint.")

    if method == "Page.navigate":
        nav_url = str(clean_params.get("url", "")).strip()
        if _FORBIDDEN_BROWSER_TARGET_PATTERN.search(nav_url):
            reasons.append(f"Navigation URL '{nav_url}' blocked by Layer-0 SSRF/password-store policy.")

    if method == "Runtime.evaluate":
        expr = str(clean_params.get("expression", ""))
        if _COOKIE_EXFIL_EXPR_PATTERN.search(expr):
            reasons.append("Runtime.evaluate expression blocked: detected document.cookie network exfiltration pattern.")
        if _WEB_STORAGE_EXFIL_EXPR_PATTERN.search(expr):
            reasons.append("Runtime.evaluate expression blocked: detected localStorage/sessionStorage network exfiltration pattern.")

    if method == "DOM.setFileInputFiles":
        files = clean_params.get("files") or []
        for fpath in files:
            if _SENSITIVE_UPLOAD_FILE_PATTERN.search(str(fpath)):
                reasons.append(f"File upload blocked: '{fpath}' matches sensitive credential/key filename pattern.")

    if reasons:
        return CdpGuardVerdict(
            action=GuardAction.BLOCK,
            method=method,
            safe=False,
            layer0_triggered=True,
            reasons=reasons,
            recommended_params=clean_params,
        )

    if method == "Runtime.evaluate" and "userGesture" not in clean_params:
        clean_params["userGesture"] = True

    return CdpGuardVerdict(
        action=GuardAction.ALLOW,
        method=method,
        safe=True,
        layer0_triggered=False,
        reasons=["Passed Layer-0 CDP pre-screen."],
        recommended_params=clean_params,
    )
