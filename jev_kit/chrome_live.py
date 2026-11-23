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
    r"id_(?:rsa|ed25519|ecdsa|dsa)(?:_sk)?(?:\.pub)?|"
    r"credentials(?:\.json|\.db|\.xml)?|"
    r"\.git-credentials|"
    r"\.npmrc|\.pypirc|\.netrc|\.vault-token|\.yarnrc\.yml|\.envrc|\.terraformrc|"
    r"\.cargo[/\\]credentials(?:\.toml)?|\.gem[/\\]credentials|\.fly[/\\]config\.yml|\.composer[/\\]auth\.json|"
    r"secrets\.(?:ya?ml|json|toml)|master\.key|"
    r"cookies\.sqlite|Login\s*Data|Local\s*State|Web\s*Data|"
    r"terraform\.tfstate(?:\.backup)?|\.kube[/\\]config|kubeconfig|"
    r"\.aws[/\\](?:credentials|config)|\.docker[/\\]config\.json|gh[/\\]hosts\.yml|"
    r"\.codex[/\\]auth\.json|\.claude[/\\]\.credentials\.json|"
    r"\.config[/\\]gcloud[/\\](?:application_default_credentials\.json|credentials\.db)|\.azure[/\\]accessTokens\.json|"
    r"\.pgpass|\.my\.cnf|\.boto|\.databrickscfg|key4\.db|logins\.json|age[/\\]keys\.txt|"
    r"\.pulumi[/\\]credentials\.json|\.wrangler[/\\]config[/\\]default\.toml|glab-cli[/\\]config\.yml|"
    r"\.huggingface[/\\]token|\.railway[/\\]config\.json|\.config[/\\]doctl[/\\]config\.yaml|"
    r"\.modal\.toml|\.s3cfg|\.vercel[/\\]auth\.json|"
    r"[^/\\]+\.(?:pem|key|pfx|p12|kdbx)"
    r")$",
    re.IGNORECASE,
)

_FORBIDDEN_BROWSER_TARGET_PATTERN = re.compile(
    r"(?:"
    r"^javascript:|"
    r"^data:text/html|"
    r"^devtools://|"
    r"^view-source:file://|"
    r"^about:config|"
    r"^chrome://(?:settings/passwords|password-manager|omnibox|extensions|net-export|inspect|signin-internals|sync-internals|gcm-internals|local-state|indexeddb-internals|histograms|ukm|flags|webrtc-internals|usb-internals|bluetooth-internals|translate-internals|net-internals|quota-internals|process-internals|policy|device-log|media-internals|serviceworker-internals|app-service-internals|predictors|safe-browsing|attribution-internals)|"
    r"^(?:edge|brave)://(?:wallet|passwords|settings/passwords)|"
    r"^file://+(?:etc/(?:passwd|shadow)|windows/system32/config)|"
    r"^file://+.*?(?:User\s*Data|google-chrome|chromium).*?(?:Login\s*Data|Cookies|Local\s*State|Web\s*Data)|"
    r"^https?://169\.254\.169\.254(?:/|$)|"
    r"^https?://(?:169\.254\.170\.2|169\.254\.0\.23|168\.63\.129\.16|192\.0\.0\.192)(?:/|$)|"
    r"^https?://(?:2852039166|0xa9fea9fe|0xa9\.0xfe\.0xa9\.0xfe|0251\.0376\.0251\.0376|0251\.254\.169\.254)(?:/|$)|"
    r"^https?://(?:\[fd00:ec2::254\]|\[(?:0:0:0:0:0:ffff|::ffff):(?:169\.254\.169\.254|a9fe:a9fe)\]|100\.100\.100\.200)(?:/|$)|"
    r"^https?://kubernetes\.default(?:\.svc(?:\.cluster\.local)?)?(?:/|$)|"
    r"^https?://metadata(?:\.(?:google\.internal|goog))?(?:/|$)"
    r")",
    re.IGNORECASE,
)

_BULK_COOKIE_DUMP_METHODS = frozenset({
    "Network.getAllCookies",
    "Storage.getCookies",
    "Storage.getSharedStorageEntries",
    "Storage.getTrustTokens",
    "Storage.clearTrustTokens",
    "Storage.runBounceTrackingMitigations",
    "DOMStorage.getDOMStorageItems",
    "IndexedDB.requestData",
    "CacheStorage.requestEntries",
    "CacheStorage.requestCachedResponse",
    "FileSystem.getDirectory",
    "Network.getResponseBody",
    "Network.getRequestPostData",
    "Network.loadNetworkResource",
    "Network.enableReportingApi",
    "Fetch.takeResponseBodyAsStream",
    "Fetch.enable",
    "Audits.getEncodedResponse",
    "Network.setRequestInterception",
    "Network.setCookie",
    "Network.setCookies",
    "Storage.setCookies",
    "Storage.clearDataForOrigin",
    "Storage.clearCookies",
    "Network.clearBrowserCookies",
    "Debugger.setScriptSource",
    "Debugger.evaluateOnCallFrame",
    "HeapProfiler.takeHeapSnapshot",
    "HeapProfiler.getObjectByHeapObjectId",
    "Runtime.queryObjects",
    "DOMSnapshot.captureSnapshot",
    "Page.captureSnapshot",
    "Page.setSPCTransactionMode",
    "Cast.enable",
    "Cast.startTabMirroring",
    "FedCm.enable",
    "FedCm.selectAccount",
    "DeviceAccess.enable",
    "DeviceAccess.selectPrompt",
    "BluetoothEmulation.enable",
    "BackgroundService.startObserving",
    "BackgroundService.setRecording",
    "Autofill.trigger",
    "Autofill.setAddresses",
    "PWA.install",
    "PWA.launch",
    "Tracing.start",
    "Page.startScreencast",
    "SystemInfo.getProcessInfo",
    "Target.exposeDevToolsProtocol",
    "Target.setAutoAttach",
    "Extensions.loadUnpacked",
    "Extensions.getStorageItems",
    "Extensions.setStorageItems",
    "WebAuthn.enable",
    "WebAuthn.addVirtualAuthenticator",
    "WebAuthn.getCredentials",
    "Page.addScriptToEvaluateOnNewDocument",
    "Page.addScriptToEvaluateOnLoad",
    "Page.setBypassCSP",
    "Runtime.addBinding",
    "Browser.grantPermissions",
    "Browser.setPermission",
    "ServiceWorker.deliverPushMessage",
    "ServiceWorker.dispatchSyncEvent",
    "Security.setIgnoreCertificateErrors",
    "Security.setOverrideCertificateErrors",
    "Security.handleCertificateError",
    "Network.replayXHR",
    "Browser.executeBrowserCommand",
    "Browser.addPrivacySandboxEnrollmentOverride",
    "SmartCardEmulation.enable",
    "Storage.trackIndexedDBForOrigin",
    "Storage.trackCacheStorageForOrigin",
})

_COOKIE_EXFIL_EXPR_PATTERN = re.compile(
    r"(?is)(?:document\.cookie|\bcookieStore\.(?:get|getAll)\s*\().*?(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket|WebTransport|EventSource|BroadcastChannel)\s*\()"
    r"|(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket|WebTransport|EventSource|BroadcastChannel)\s*\().*?(?:document\.cookie|\bcookieStore\.(?:get|getAll)\s*\()"
)

_WEB_STORAGE_EXFIL_EXPR_PATTERN = re.compile(
    r"(?is)(?:\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|\bcaches\.(?:open|match|keys)\s*\().*?(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket|WebTransport|EventSource|BroadcastChannel)\s*\()"
    r"|(?:\bfetch\s*\(|\bXMLHttpRequest\b|navigator\.sendBeacon\s*\(|new\s+(?:Image|WebSocket|WebTransport|EventSource|BroadcastChannel)\s*\().*?(?:\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|\bcaches\.(?:open|match|keys)\s*\()"
)

_REDIRECT_EXFIL_EXPR_PATTERN = re.compile(
    r"(?is)(?:(?:window\.)?location\.(?:assign|replace)\s*\(|(?:window\.)?location(?:\.href)?\s*=).*?(?:document\.cookie|\bcookieStore\b|\blocalStorage\b|\bsessionStorage\b)"
)

_CLIPBOARD_HARVEST_EXPR_PATTERN = re.compile(
    r"(?is)\bnavigator\.clipboard\.read(?:Text)?\s*\("
)

_CREDENTIAL_CONTAINER_EXPR_PATTERN = re.compile(
    r"(?is)\bnavigator\.credentials\.(?:get|create|store)\s*\(|\bquerySelector(?:All)?\s*\(\s*['\"][^'\"]*type\s*=\s*['\"]?password\b|\bdocument\.domain\s*="
)

_SERVICE_WORKER_PERSIST_EXPR_PATTERN = re.compile(
    r"(?is)\bnavigator\.serviceWorker\.register\s*\("
)

_FILESYSTEM_PICKER_EXPR_PATTERN = re.compile(
    r"(?is)\b(?:window\.)?show(?:OpenFile|SaveFile|Directory)Picker\s*\(|\bnavigator\.storage\.getDirectory\s*\("
)

_HARDWARE_PAYMENT_EXPR_PATTERN = re.compile(
    r"(?is)\bnavigator\.(?:usb|hid|bluetooth)\.requestDevice\s*\(|\bnavigator\.serial\.requestPort\s*\(|\bnavigator\.smartCard\.establishContext\s*\(|\bnew\s+PaymentRequest\s*\("
)

_MEDIA_CAPTURE_EXPR_PATTERN = re.compile(
    r"(?is)\bnavigator\.mediaDevices\.get(?:Display|User)Media\s*\("
)

_WEBRTC_PUSH_EXFIL_EXPR_PATTERN = re.compile(
    r"(?is)\bnew\s+(?:webkit)?RTCPeerConnection\s*\(|\bpushManager\.subscribe\s*\("
)

_PRIVACY_SENSOR_EXPR_PATTERN = re.compile(
    r"(?is)\bnew\s+(?:EyeDropper|NDEFReader|IdleDetector|SharedWorker|PresentationRequest)\s*\(|\bnavigator\.contacts\.select\s*\(|\b(?:window\.)?getScreenDetails\s*\("
)

_FORBIDDEN_DOWNLOAD_PATH_PATTERN = re.compile(
    r"(?:^|[/\\])\.\.(?:[/\\]|$)"
    r"|(?:^|[/\\])(?:\.ssh|\.gnupg|\.aws|\.kube|\.codex|\.claude|cron\.d|systemd|Startup|System32|etc|root)(?:[/\\]|$)",
    re.IGNORECASE,
)

_FORBIDDEN_EXTRA_HEADER_NAMES = frozenset({
    "cookie",
    "proxy-authorization",
    "authorization",
    "x-api-key",
    "x-anthropic-api-key",
    "x-amz-security-token",
    "x-goog-api-key",
    "cf-access-client-secret",
    "x-supabase-key",
    "x-gitlab-token",
    "x-vercel-protection-bypass",
    "x-hub-signature-256",
    "stripe-signature",
    "x-slack-signature",
    "x-shopify-hmac-sha256",
    "x-datadog-api-key",
    "x-sentry-auth",
    "x-algolia-api-key",
    "cf-access-jwt-assertion",
})


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

    if method in ("Page.navigate", "Target.createTarget"):
        nav_url = str(clean_params.get("url", "")).strip()
        if _FORBIDDEN_BROWSER_TARGET_PATTERN.search(nav_url):
            reasons.append(f"Navigation URL '{nav_url}' blocked by Layer-0 SSRF/password-store policy.")

    if method in ("Runtime.evaluate", "Runtime.callFunctionOn"):
        expr_key = "expression" if method == "Runtime.evaluate" else "functionDeclaration"
        expr = str(clean_params.get(expr_key, ""))
        if _COOKIE_EXFIL_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: detected cookie/cookieStore network exfiltration pattern.")
        if _WEB_STORAGE_EXFIL_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: detected localStorage/sessionStorage/indexedDB network exfiltration pattern.")
        if _CLIPBOARD_HARVEST_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: clipboard read access via CDP is prohibited.")
        if _CREDENTIAL_CONTAINER_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: navigator.credentials access via CDP is prohibited.")
        if _SERVICE_WORKER_PERSIST_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: persistent ServiceWorker registration via CDP is prohibited.")
        if _FILESYSTEM_PICKER_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: File System Access API / OPFS directory access via CDP is prohibited.")
        if _HARDWARE_PAYMENT_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: WebUSB/WebHID/WebSerial/WebBluetooth/PaymentRequest access via CDP is prohibited.")
        if _REDIRECT_EXFIL_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: top-level location redirect cookie/storage exfiltration is prohibited.")
        if _MEDIA_CAPTURE_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: silent getDisplayMedia/getUserMedia screen or mic capture via CDP is prohibited.")
        if _WEBRTC_PUSH_EXFIL_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: WebRTC STUN/TURN leak or PushManager subscription persistence via CDP is prohibited.")
        if _PRIVACY_SENSOR_EXPR_PATTERN.search(expr):
            reasons.append(f"{method} payload blocked: EyeDropper pixel sampling, ContactsManager, or multi-screen topology access via CDP is prohibited.")

    if method in ("Browser.setDownloadBehavior", "Page.setDownloadBehavior"):
        dl_path = str(clean_params.get("downloadPath", "")).strip()
        if dl_path and _FORBIDDEN_DOWNLOAD_PATH_PATTERN.search(dl_path):
            reasons.append(f"{method} blocked: downloadPath '{dl_path}' targets restricted system/credential directory or path traversal.")

    if method == "Network.setExtraHTTPHeaders":
        headers = clean_params.get("headers") or {}
        if isinstance(headers, dict):
            for hname in headers:
                if str(hname).strip().lower() in _FORBIDDEN_EXTRA_HEADER_NAMES:
                    reasons.append(f"Network.setExtraHTTPHeaders blocked: overriding sensitive '{hname}' header is prohibited.")

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
