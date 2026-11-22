# jev-cognitive-mcp

**English** · [简体中文](README.zh-CN.md)

[![CI](https://github.com/17671454333/jev-cognitive-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/17671454333/jev-cognitive-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-purple.svg)](jev_kit/mcp_server.py)

**Advisory 3+1 Cognitive Hierarchy Toolkit & Model Context Protocol (MCP) Server for Coding Agents (OpenAI Codex CLI, Claude Code, Cursor, Antigravity).**

`jev-cognitive-mcp` provides deterministic Layer-0 DLP/destructive command pre-screening, 5-factor Meta-Controller escalation arbitration, and optional System-1 probabilistic triage (`guard`, `route`, `verify`, `rerank`) over stdio MCP. All verdicts and routing signals are **advisory**—the host agent remains responsible for enforcing command blocking, sandboxing, and human-in-the-loop approval gates.

---

## Architecture: The 3+1 Cognitive Hierarchy

```mermaid
flowchart LR
    A["Incoming Agent Action / Task"] --> L0["Layer 0: Deterministic Reflex<br/>(0 network / 0 token cost)<br/>DLP regex & destructive pattern screen"]
    L0 -->|Blocked / Matched| OUT0["Immediate Advisory Verdict"]
    L0 -->|Needs Semantic Triage| S1["System 1: Probabilistic Intuition (JEV)<br/>(Requires external JevBridge)<br/>Guard / Route / Rerank / Verify"]
    S1 --> MC{"Meta-Controller<br/>5-Factor Arbitration"}
    MC -->|High Confidence & Two-Way Door| OUT1["Advisory Fast Path"]
    MC -->|Low Confidence / High Risk| S2["System 2: Host Frontier LLM<br/>(Codex / o3 / Sonnet Thinking)"]
    MC -->|One-Way Door & High Risk| HG["Explicit Human Gate Required"]
```

| Layer | Role | Execution Mode | Responsibility |
|---|---|---|---|
| **Layer 0 (Reflex)** | Deterministic Code | Local offline (`0 tokens`, no network call) | Pre-egress regex DLP credential screening (`sk-*`, `sk-ant-*`, `ghp_*`, `glpat-*`, `AKIA*`, `SG.*`, `pypi-*`, `hf_*`, `Bearer`, `password=`, `secret=`, `api_key=`, `token=`, PEM keys), destructive shell pattern matching (`rm -rf /`, `rm -rf -- /`, `Remove-Item -Recurse -Force`, `mkfs`, `wipefs -a`, `shred -u /`, `DROP DATABASE`, `curl \| bash`), strict schema validation |
| **System 1 (Intuition)** | Probabilistic JEV | External `JevBridge` single-attempt call | Multi-head `noul` (boolean probability), `choice` (categorical distribution), and `score` (0..4 ordinal rubric) evaluations |
| **System 2 (Reasoning)** | Host Frontier LLM | Host agent runtime | Complex causal reasoning, multi-file architecture design, subtle debugging |
| **Meta-Controller** | Control Plane | Local offline (`0 tokens`, no network call) | Arbitrates escalation using 5 quantitative signals: **Confidence**, **Risk**, **Reversibility**, **Expected Value**, and **Cost Pressure** |

---

## Core Modules & MCP Tools

1. **`jev_guard` (`jev_kit.guard`) — Advisory Pre-Tool Command Risk Screen**
   - Evaluates shell commands before execution and returns an advisory action (`ALLOW`, `INSPECT`, `ESCALATE_HUMAN`, or `BLOCK`).
   - **Layer 0 (`reflex_only=true` or pre-screen)**: Blocks literal credential egress (`SENSITIVE_INPUT_REJECTED`) and known destructive shell/PowerShell patterns locally with zero network calls.
   - **System 1 (when `reflex_only=false`)**: Evaluates `is_destructive`, `is_rce_or_exfil`, and `is_secret_leak` probabilities via `JevBridge`.
2. **`jev_arbitrate` (`jev_kit.controller`) — Offline 5-Factor Meta-Controller**
   - Purely deterministic calculation of expected escalation utility from `(confidence, risk, reversible, expected_value, cost_pressure)`. Recommends `human_gate` on irreversible high-risk actions. Works completely offline.
3. **`jev_route` (`jev_kit.router`) — Advisory Task & Model Tier Router**
   - Classifies incoming coding prompts into `FAST` (`codex-mini-latest`, `gpt-4o-mini`), `STANDARD` (`gpt-4.1`, `gpt-4o`), or `DEEP_REASONING` (`o3`, `codex-1`) tiers while estimating architectural scope.
4. **`jev_verify` (`jev_kit.verifier`) — Caller-Supplied Completion & Acceptance Review**
   - Reviews caller-supplied `task_spec`, `implemented_changes` summary, and `test_results` logs to return `PASS`, `ADVISORY`, or `NEEDS_REVISION`. Does **not** inspect git repositories or run test suites directly.
5. **`jev_rerank` (`jev_kit.reranker`) — Bounded Semantic Candidate Reranker**
   - Ranks up to 96 caller-supplied code snippets or issue candidates in deterministic batches of 12 while preserving full provenance and failing closed on partial batch errors.

---

## Offline Deterministic Mode vs. External `JevBridge` Requirement

- **Works 100% Offline (Zero External Dependencies)**:
  - `jev_arbitrate` (5-factor Meta-Controller)
  - `jev_guard` with `reflex_only=true` (`jev-kit guard "<cmd>" --reflex-only`)
  - `jev-kit init-codex` (configuration generator for OpenAI Codex CLI and MCP clients)
  - Pre-egress credential DLP screening inside `call_jev()` (blocks sensitive tokens before any bridge lookup)
- **Requires External `JevBridge` Runtime**:
  - `jev_guard` (when `reflex_only=false` and Layer 0 does not match), `jev_route`, `jev_verify`, and `jev_rerank` invoke `jev_cli.py` from the local `JevBridge` runtime directory.
  - Set `JEV_BRIDGE_DIR=/path/to/JevBridge/runtime` (defaults to `%LOCALAPPDATA%\JevBridge\runtime` on Windows or `~/.local/share/JevBridge/runtime` on Linux/macOS). If the bridge runtime is not installed, these tools fail closed with `JevIntegrationError(code="BRIDGE_MISSING")`.

---

## Quick Start

### 1. Installation

```bash
git clone https://github.com/17671454333/jev-cognitive-mcp.git
cd jev-cognitive-mcp
pip install -e ".[dev]"
```

### 2. Wire into OpenAI Codex CLI (`~/.codex/config.toml`)

Generate the exact TOML snippet with `jev-kit init-codex --format toml` and add it to `~/.codex/config.toml`:

```toml
[mcp_servers.jev_cognitive]
command = "jev-mcp"
args = []
```

### 3. Wire into JSON MCP Clients (Claude Code, Cursor, Antigravity)

Generate with `jev-kit init-codex --format json`:

```json
{
  "mcpServers": {
    "jev-cognitive": {
      "command": "jev-mcp",
      "args": []
    }
  }
}
```

### 4. CLI Usage & Verification

```bash
# Generate OpenAI Codex CLI config.toml snippet
jev-kit init-codex --format toml

# Layer-0 deterministic reflex screen (offline, 0 tokens)
jev-kit guard "rm -rf -- /" --reflex-only

# 5-factor Meta-Controller arbitration (offline, 0 tokens)
jev-kit arbitrate --confidence 0.62 --risk 0.75 --irreversible --value 0.85

# Run deterministic unit test suite
python -m unittest discover -s tests -v
```

---

## Security & Reliability Boundaries

- **Pre-Egress Credential DLP Chokepoint**: Both `local_reflex_screen()` and `call_jev()` screen serialized inputs for literal secrets (`sk-*`, `ghp_*`, `glpat-*`, `AKIA*`, `sntrys_*`, `s.*`, `PMAK-*`, `glsa_*`, `Bearer`, `password=`, `secret=`, `api_key=`, `token=`, PEM private keys, and URL userinfo credentials) and raise `SENSITIVE_INPUT_REJECTED` before `_invoke_bridge()` can be called.
- **Zero Direct Credential Arguments**: `call_jev()` rejects explicit `api_key`, `token`, or `secret` keyword arguments (`DIRECT_CREDENTIALS_DISABLED`).
- **Advisory Boundary**: Outputs from `jev-cognitive-mcp` are advisory structured signals; host agents must enforce execution blocking and human approval gates.
- **No Silent Fallbacks**: Timeouts, missing bridge runtimes (`BRIDGE_MISSING`), or malformed responses raise `JevIntegrationError` with explicit `billing_uncertain` tracking rather than defaulting to `ALLOW` or `PASS`.

## License

Released under the [MIT License](LICENSE).


## Zero-Popup Chrome M144+ Live CDP Guard (`jev_chrome_guard`)

Modern Chrome (M144+) exposes `%LOCALAPPDATA%\Google\Chrome\User Data\DevToolsActivePort` via `chrome://inspect/#remote-debugging`, triggering a native modal prompt on every transient WebSocket handshake. `jev_chrome_guard` provides:
- **Zero-Popup `DevToolsActivePort` Discovery**: Parses live port and browser WebSocket UUID across Windows, macOS, and Linux without opening transient WebSockets.
- **Layer-0 CDP DLP & SSRF Pre-Screen**: Blocks accidental `.env` / `.envrc` / `.terraformrc` / SSH key / `.kube/config` / `.aws/credentials` / `.docker/config.json` / `.codex/auth.json` / `.claude/.credentials.json` / `.vault-token` / `.cargo/credentials.toml` / `.fly/config.yml` / `.pulumi/credentials.json` / `.wrangler/config/default.toml` / `.composer/auth.json` / `master.key` / `.pgpass` / `age/keys.txt` / Firefox `key4.db` & `logins.json` / `gcloud` ADC / `terraform.tfstate` / Chrome `Local State` file uploads in `DOM.setFileInputFiles`, blocks `document.cookie` / `cookieStore.getAll()`, `localStorage`/`sessionStorage`/`indexedDB`/`caches.open()`, and top-level `location.href` redirect exfiltration (including `WebTransport`, `EventSource` & `BroadcastChannel` sinks), `navigator.clipboard.readText()`, `navigator.credentials.get()` & DOM `input[type="password"]` harvesting, `navigator.mediaDevices.getDisplayMedia()`/`getUserMedia()` screen & mic capture, `EyeDropper` / `NDEFReader` / `IdleDetector` / `SharedWorker` sensor & worker persistence, `navigator.contacts.select()` & `getScreenDetails()` fingerprinting, `RTCPeerConnection` STUN/TURN leak & `pushManager.subscribe()` persistence, File System Access API (`showDirectoryPicker` / `navigator.storage.getDirectory`), WebUSB/WebHID/WebSerial/WebBluetooth/`PaymentRequest` hardware & payment prompts, and persistent `navigator.serviceWorker.register()` injection across both `Runtime.evaluate` and `Runtime.callFunctionOn`, blocks bulk `DOMStorage`/`IndexedDB`/`CacheStorage`/`SharedStorage`/OPFS (`FileSystem.getDirectory`)/cookie dumps, V8 heap & full-DOM memory snapshots (`HeapProfiler.takeHeapSnapshot` / `Runtime.queryObjects` / `DOMSnapshot.captureSnapshot` / `Page.captureSnapshot`), federated login, SPC payment & hardware chooser bypass (`FedCm.enable` / `FedCm.selectAccount` / `Page.setSPCTransactionMode` / `DeviceAccess.selectPrompt` / `BluetoothEmulation.enable`), background observation & silent app persistence (`BackgroundService.startObserving` / `Autofill.trigger` / `PWA.install`), destructive `Network.clearBrowserCookies` / `Storage.clearDataForOrigin` session wipes, privileged `Target.exposeDevToolsProtocol` / `Extensions.loadUnpacked` / `Extensions.getStorageItems` / `Page.startScreencast` / `Audits.getEncodedResponse` escalation, live `Debugger.evaluateOnCallFrame` / `Network.getRequestPostData` / `WebAuthn.getCredentials` / `Tracing.start` inspection, silent `Browser.grantPermissions` / `Page.setBypassCSP` overrides, persistent `Page.addScriptToEvaluateOnNewDocument` / `Runtime.addBinding` backdoors, TLS downgrade (`Security.setIgnoreCertificateErrors` / `Security.handleCertificateError`), MITM `Fetch.enable` / `Network.setCookie` overrides, sensitive `Browser.setDownloadBehavior` path traversal, and `Cookie`/`Authorization`/`X-Api-Key`/`X-Anthropic-Api-Key`/`X-Amz-Security-Token`/`X-Goog-Api-Key`/`CF-Access-Client-Secret`/`X-Supabase-Key`/`X-Gitlab-Token`/`X-Vercel-Protection-Bypass`/`X-Hub-Signature-256`/`Stripe-Signature`/`Proxy-Authorization` header overrides, blocks `javascript:` / `data:text/html` / `devtools://` / `view-source:file://` / `about:config` pseudo-URLs, `chrome://signin-internals` / `chrome://local-state` / `chrome://webrtc-internals` / `chrome://net-internals` token & network pages, `file://` browser profile vault reads, and cloud metadata SSRF (`169.254.169.254`, AWS ECS `169.254.170.2`, Azure WireServer `168.63.129.16`, Oracle OCI `192.0.0.192`, decimal/hex/dotted-hex/octal `2852039166`/`0xa9fea9fe`/`0xa9.0xfe.0xa9.0xfe`/`0251.254.169.254`, `[fd00:ec2::254]`, `[::ffff:169.254.169.254]`, `[::ffff:a9fe:a9fe]`, `100.100.100.200`, `metadata.goog`) across `Page.navigate` and `Target.createTarget`, and enforces `userGesture: true` on safe evaluations to prevent popup blockers.

---

## Open-Core Pro & Commercial Ecosystem

| Capability | Community Core (`jev-cognitive-mcp` · MIT) | Studio Pro Suite (Commercial / Sponsors) |
| :--- | :--- | :--- |
| **Layer-0 Shell & CDP Guardrails** | ✅ Included (115-case JSONL benchmark, 0 tokens) | ✅ + Custom Enterprise Policy Packs |
| **5-Factor Meta-Controller & Autopilot** | ✅ Included (`jev_arbitrate`, `jev_autopilot`) | ✅ + Multi-Key Quota Balancer |
| **Chrome M144+ Zero-Popup CDP Guard** | ✅ Endpoint Discovery + Layer-0 CDP Screen | ✅ + Persistent Multi-Tab Daemon & Windows UIA Auto-Consent |
| **8-Platform Matrix Auto-Publisher** | — | 🚀 **Pro Exclusive**: One-click zero-login publishing to YouTube, TikTok, Bilibili, Xiaohongshu, Douyin, WeChat Channels & Kuaishou |
| **AI Short-Drama & WebGame Studio** | See [`open-short-drama-studio`](https://github.com/17671454333/open-short-drama-studio) | 🚀 **Pro Exclusive**: Cross-shot face-locking, Seedance 85%-credit-saver pipeline, CapCut draft exporter & 6-target WebGame packager |
