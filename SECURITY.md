# Security Policy

## Architectural Security Principles

`jev-cognitive-mcp` is designed as a security-first cognitive routing and pre-tool verification layer for autonomous coding agents (OpenAI Codex CLI, Claude Code, Cursor, Antigravity):

1. **Zero Direct Credential Handling**: `call_jev()` explicitly rejects raw API keys (`DIRECT_CREDENTIALS_DISABLED`). Credentials remain isolated in the host bridge runtime and are never exposed to agent tool arguments.
2. **Layer-0 Deterministic DLP & Destructive Reflex**: Before any network request is made, `local_reflex_screen()` inspects inputs for literal secrets (`sk-*`, `ghp_*`, `Bearer` tokens, password assignments) and blocks destructive shell patterns (`rm -rf /`, `mkfs`, `DROP DATABASE`, remote `curl | bash` pipes) in `<1ms` with zero token egress.
3. **Advisory Non-Escalation**: A high confidence score from System-1 intuition (`ConfidenceLevel.HIGH`) is a descriptive signal, **never** an execution grant that bypasses host sandboxing or human-in-the-loop gates for one-way-door operations.
4. **Bounded Single-Attempt Execution**: Every logical evaluation makes at most one upstream request (`billing_uncertain` is explicitly tracked on timeouts without silent retries).

## Supported Versions

| Version | Supported |
| ------- | --------- |
| `0.3.x` | Yes       |
| `< 0.3` | No        |

## Reporting a Vulnerability

Please report security vulnerabilities via **GitHub Security Advisories** on this repository rather than opening a public issue with exploit payloads. We aim to triage all reports within 48 hours.
