# jev-cognitive-mcp

[English](README.md) · **简体中文**

[![CI](https://github.com/17671454333/jev-cognitive-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/17671454333/jev-cognitive-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**面向自主编码智能体（OpenAI Codex CLI、Claude Code、Cursor、Antigravity）的 3+1 认知分层工具包与 MCP（Model Context Protocol）安全服务端。**

---

## 核心解决的问题

在自主编码与开源维护工作流（PR 审查、Issue 分类、自动化测试、终端命令执行）中，如果将所有判断都交给重度推理大模型（System 2），不仅延迟高、Token 消耗巨大，还容易出现“自我宣布完成”或误执行高危命令。

`jev-cognitive-mcp` 构建了严密的 **3+1 认知分层闭环**：

1. **Layer 0（确定性反射层，`<1ms` / `0 Token`）**：本地正则 DLP 凭据拦截（防止 `sk-*`、`ghp_*`、`Bearer` 外泄）、破坏性命令与远程管道熔断（`rm -rf /`、`DROP DATABASE`、`curl | bash`）、严格 Schema 校验。
2. **System 1（快速直觉层 / JEV）**：亚秒级概率分布评估，负责命令风险初筛（`jev_guard`）、任务复杂度与模型路由（`jev_route`）、候选片段重排序（`jev_rerank`）与交付验收门禁（`jev_verify`）。
3. **System 2（深度推理层 / 宿主主模型）**：专注复杂因果推理、跨模块架构设计与疑难 Bug 修复。
4. **Meta-Controller（五维元认知仲裁中枢）**：基于 **置信度 (Confidence)**、**风险度 (Risk)**、**可逆性 (Reversibility)**、**预期价值 (Value)** 与 **算力成本 (Cost)** 五项量化指标，确定性地裁决停留层级或触发人工审批门禁（Human Gate）。

---

## 快速开始

```bash
git clone https://github.com/17671454333/jev-cognitive-mcp.git
cd jev-cognitive-mcp
pip install -e ".[dev]"
pytest -v
```

### MCP 客户端接入

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

## 开源许可

本项目采用 [MIT 许可证](LICENSE) 开源。
