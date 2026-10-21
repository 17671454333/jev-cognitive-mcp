# Contributing to jev-cognitive-mcp

Thank you for your interest in contributing to `jev-cognitive-mcp`!

## Development Setup

```bash
git clone https://github.com/17671454333/jev-cognitive-mcp.git
cd jev-cognitive-mcp
pip install -e ".[dev]"
pytest -v
```

## Pull Request Checklist

1. **Deterministic Layer-0 First**: Any rule that can be expressed deterministically (regex, AST check, allowlist, schema validation) belongs in Layer 0 (`local_reflex_screen` or `_validate_*`), not in a prompt.
2. **No Silent Fallbacks**: Never convert network timeouts, missing confidence, or malformed responses into `ALLOW` or `PASS`. Always raise `JevIntegrationError` with accurate `billing_uncertain` metadata.
3. **Zero Credential Egress**: Add unit tests verifying that sensitive patterns are rejected before transport invocation.
4. **Tests Required**: All new MCP tools, arbitration rules, or CLI subcommands must include unit tests in `tests/`.
