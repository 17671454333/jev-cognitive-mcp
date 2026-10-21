# jev-cognitive-mcp

[English](README.md) · **简体中文**

[![CI](https://github.com/17671454333/jev-cognitive-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/17671454333/jev-cognitive-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**面向编码智能体（OpenAI Codex CLI、Claude Code、Cursor、Antigravity）的 3+1 认知分层辅助工具包与 MCP（Model Context Protocol）服务端。**

---

## 核心定位与设计边界

在自主编码与开源维护工作流中，`jev-cognitive-mcp` 提供**辅助性（Advisory）**风险初筛、模型层级路由、五维元认知仲裁与完成度复核信号。实际命令拦截、沙箱隔离与人工确认门禁（Human Gate）由宿主智能体执行。

1. **Layer 0（确定性反射层，本地离线 / 0 Token）**：
   - 在任何外部桥接调用前，对序列化输入执行本地正则 DLP 敏感凭据拦截（涵盖带引号或不带引号的 `password=`、`secret=`、`api_key=`、`token=`，以及 `sk-*`、`ghp_*`、`glpat-*`、`AKIA*`、`Bearer`、PEM 私钥与 URL 凭据），触发 `SENSITIVE_INPUT_REJECTED`，确保敏感凭据不会进入桥接负载。
   - 识别高危破坏性命令（如 `rm -rf /`、`rm -rf -- /`、PowerShell `Remove-Item -Recurse -Force`、`rd /s /q`、`mkfs`、`DROP DATABASE` 及 `curl | bash` 远程执行管道）。
2. **System 1（概率直觉层 / 需外部 `JevBridge`）**：
   - 通过本地 `JevBridge`（由环境变量 `JEV_BRIDGE_DIR` 指定目录，未安装时显式返回 `BRIDGE_MISSING`）执行单次概率评估，包含 `jev_guard`（命令风险评估）、`jev_route`（模型层级路由）、`jev_rerank`（候选片段重排序）与 `jev_verify`（基于调用方传入的任务说明、变更摘要与测试结果进行完成度评估，不直接读取 Git 仓库或执行测试）。
3. **System 2（深度推理层 / 宿主主模型）**：
   - 由宿主大模型（如 `o3`、`codex-1`）处理复杂架构重构与跨模块因果推理。
4. **Meta-Controller（五维元认知仲裁，本地离线 / 0 Token）**：
   - `jev_arbitrate` 基于 **置信度 (Confidence)**、**风险度 (Risk)**、**可逆性 (Reversibility)**、**预期价值 (Value)** 与 **成本压力 (Cost Pressure)** 五项量化指标计算升级效用，对不可逆高风险操作建议触发人工确认（`human_gate`）。

---

## 快速开始

```bash
git clone https://github.com/17671454333/jev-cognitive-mcp.git
cd jev-cognitive-mcp
pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

### 1. 接入 OpenAI Codex CLI (`~/.codex/config.toml`)

运行 `jev-kit init-codex --format toml` 生成配置并写入 `~/.codex/config.toml`：

```toml
[mcp_servers.jev_cognitive]
command = "jev-mcp"
args = []
```

### 2. 接入标准 JSON MCP 客户端

运行 `jev-kit init-codex --format json` 生成配置：

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
