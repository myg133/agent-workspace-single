---
name: agent-workspace-single
description: 单机、双仓（代码仓库 + 文档仓库）、传统分支模型下的轻量多 Agent 协作层。用于已有项目不想改造成 workspace 布局，但需要 WIP=1、feature worktree 隔离、认领和交接的场景。单机消息、本地 inbox、可选 MQTT 已支持；不适用于需要 workspace 分支模型的场景。
metadata:
  short-description: 单机双仓 Agent 协作
  version: 0.2.0
---

# agent-workspace-single

这是 `agent-workspace` 的单机精简版，只解决三件事：

1. 一个 agent 同时只持有一个需求（WIP=1）；
2. 每个需求一个独立 feature worktree；
3. 需求文档在另一个仓库时，仍能完成认领、交接和状态追踪。

它**不改造**代码仓库，也不使用 `demand` / `bus` / `deploy` 分支。

## 何时使用

- 已有传统 `main/develop/feature/*` 仓库；
- 文档在独立仓库；
- 单机多 agent（BA/Dev/QA）；
- 不想引入 workspace orphan 根和 bus 分支。

## 何时不用

- 需要跨机共享 claim；
- 需要 workspace 的 `code/BA/Deploy` 布局；
- 需要完整 audit/verify/upgrade。

## 角色

- `references/roles/planner.md`（可选）
- `references/roles/ba.md`
- `references/roles/dev.md`
- `references/roles/qa.md`

## 测试预算（默认）

- 每个任务新增测试 ≤3；Bug 修复 1 条回归；重构 0 条；
- Dev 默认只跑 fast / related，full 交给 QA / CI；
- 测试按风险测，不按覆盖率测；停止条件、失败分诊、测试审计见
  `references/testing.md`。

## 依赖

MQTT 库已 vendor 到 `vendor/paho/`（paho-mqtt 2.2.0），不需要安装依赖。

## 入口

先读：

- `references/setup.md`
- `references/single-profile.md`
- `references/workflow.md`
- `references/testing.md`
- `references/layout.md`
- `references/omp.md`
- `references/dsh.md`

命令：

```bash
python scripts/aw_single.py init --root . \
  --code-root <code-root> --docs-root <docs-root> --base-branch develop
python scripts/aw_single.py whoami
python scripts/aw_single.py queue add REQ-001
python scripts/aw_single.py claim next
python scripts/aw_single.py claim list
python scripts/aw_single.py claim release REQ-001
python scripts/aw_single.py claim doctor

python scripts/aw_single.py msg send --to ba-1 --type question --body "ping"
python scripts/aw_single.py msg inbox
python scripts/aw_single.py msg wait --timeout 120
python scripts/aw_single.py watch --ensure --exec "bash start-agent.sh"
```
