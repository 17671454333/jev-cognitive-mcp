# Security Policy

## Architectural Security Principles & Boundaries

`jev-cognitive-mcp` provides an **advisory** cognitive routing and pre-tool verification layer for coding agents (OpenAI Codex CLI, Claude Code, Cursor, Antigravity). Host agents are responsible for enforcing actual command execution blocking, sandboxing, and human-in-the-loop approvals.

1. **Pre-Egress DLP Chokepoint (`SENSITIVE_INPUT_REJECTED`)**:
   - Before `_invoke_bridge()` is ever called, `call_jev()` and `local_reflex_screen()` scan the serialized payload for literal credentials, including quoted or unquoted `password=`, `passwd=`, `secret=`, `api_key=`, `token=` assignments, `Bearer`/`Basic` headers, `sk-*`, `ghp_*`, `glpat-*`, `xox*`, `AKIA*`, `npm_*` tokens, PEM private keys, and URL userinfo credentials. Matching payloads are rejected locally with zero network egress.
2. **Zero Direct Credential Arguments (`DIRECT_CREDENTIALS_DISABLED`)**:
   - `call_jev()` explicitly rejects `api_key`, `token`, or `secret` keyword arguments. Credentials remain isolated in the external host bridge runtime.
3. **Layer-0 Destructive Command Pattern Screening**:
   - `local_reflex_screen()` detects common destructive shell and PowerShell patterns (`rm -rf /`, `rm -rf -- /`, separated flags `rm -r -f /`, `Remove-Item -Recurse -Force`, `rd /s /q`, `mkfs`, `DROP DATABASE`, and remote `curl/wget/iwr/irm | sh/bash/pwsh/iex/python` pipes) locally without network calls. Because pattern matching is heuristic, host sandboxing remains mandatory.
4. **Advisory Non-Escalation**:
   - High confidence from System-1 intuition (`ConfidenceLevel.HIGH`) is a descriptive signal, **never** an execution grant that bypasses host sandboxing or human gates for irreversible operations.
5. **Bounded Single-Attempt Execution**:
   - Every System-1 evaluation makes at most one upstream bridge call (`billing_uncertain` is explicitly tracked on timeouts without silent retries).

## Supported Versions

| Version | Supported |
| ------- | --------- |
| `0.3.x` | Yes       |
| `< 0.3` | No        |

## Reporting a Vulnerability

Please report security vulnerabilities via **GitHub Security Advisories** on this repository rather than opening a public issue with live credentials or exploit payloads.
