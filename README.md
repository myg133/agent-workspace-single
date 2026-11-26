# agent-workspace-single

> **合并状态（2026-11-26）**：single 模式已并入 `agent-workspace` 2.0.0；
> 本仓库保留兼容与历史，新安装优先使用主 skill 的 single 模式（`scripts/aw_single.py`）。

单机版的轻量 Agent 协作层：**传统代码仓库 + 独立文档仓库 + 本地 `.aw/`**。

它不要求把现有项目改造成 workspace 布局，也不创建 `demand` / `deploy` 分支；消息用本地 inbox，可选 bus 审计 / MQTT。

- 代码仓库保持原样（通常 `main` / `develop` / `feature/*`）；
- 需求、验收、状态继续放在现有文档仓库；
- feature worktree 放在独立的 `worktrees/` 目录；
- 认领、WIP、session 放在本地 `.aw/`，不提交到任何仓库。

## 状态

MVP 已实现：`scripts/aw_single.py`。

MQTT 依赖已 vendor 到 `vendor/paho/`（paho-mqtt 2.2.0），不需要 `pip install`。

## 测试预算

默认按风险测，不按覆盖率测：

- 每个任务新增测试 ≤3；Bug 修复 1 条回归；重构 0 条；
- Dev 只跑 fast / related；full 交给 QA / CI；
- 不测未改动代码、第三方库、私有实现、日志/文案/格式；
- 目标测试 + related 通过即停止，不补覆盖率。

完整规则见 [references/testing.md](references/testing.md)。

## MQTT 配置

MQTT 默认关闭。需要连接时，在 `.aw/config.json` 写：

```json
{
  "mqtt": {
    "enabled": true,
    "host": "broker.example.com",
    "port": 8883,
    "tls": true,
    "ca_file": "",
    "username": "",
    "password_env": "AW_MQTT_PASSWORD",
    "client_id": "",
    "keepalive": 30,
    "topic_prefix": "aw/v1"
  }
}
```

或用 `init` 参数：

```bash
aw_single.py init --root . \
  --code-root D:/proj/app --docs-root D:/proj/docs \
  --base-branch develop \
  --mqtt-host broker.example.com --mqtt-port 8883 \
  --mqtt-username aw --mqtt-ca D:/certs/ca.pem
```

密码通过 `AW_MQTT_PASSWORD` 提供，不写进配置。watcher 已接入 MQTT 订阅/发布与 presence；没有 broker 时退化本地 inbox + bus。

```bash
python scripts/aw_single.py init --root . \
  --code-root D:/proj/app --docs-root D:/proj/docs --base-branch develop

python scripts/aw_single.py whoami
python scripts/aw_single.py handoff --note "换班" --next-step "先处理未读"
python scripts/aw_single.py resume
python scripts/aw_single.py queue add REQ-001 --title "登录"
python scripts/aw_single.py claim next
python scripts/aw_single.py claim list
python scripts/aw_single.py claim release REQ-001
# 已有分支/worktree 被孤儿认领占用：保留现场，转给当前 BA
python scripts/aw_single.py claim adopt REQ-001 --branch feature/REQ-001
python scripts/aw_single.py claim doctor
python scripts/aw_single.py project check
python scripts/aw_single.py bus log

python scripts/aw_single.py msg send --to ba-1 --type question --body "ping"
python scripts/aw_single.py msg report --subject "用户新任务" --body "REQ-001：目标 / 优先级 / 预期"
python scripts/aw_single.py msg inbox
python scripts/aw_single.py msg wait --timeout 120
python scripts/aw_single.py watch --ensure --exec "bash start-agent.sh"
```

当前覆盖：本地 claim、WIP=1、feature worktree、queue、doctor、本地消息、wake。
不解析 docs 状态、不接 CI、不做跨机通信。

## 目录

```text
<local-root>/
├── app/                 # 现有代码仓库
├── docs/                # 现有文档仓库
├── worktrees/           # feature worktree
└── .aw/                 # 本地协调层（不提交）
    ├── config.json
    ├── claims/
    ├── sessions/
    └── queue.json
```

## 角色

| 角色 | 文档 | 说明 |
|------|------|------|
| Planner（可选） | [planner.md](references/roles/planner.md) | 优先级、跨 BA 边界、ADR |
| BA | [ba.md](references/roles/ba.md) | 需求、验收、状态、claim、派单 |
| Dev | [dev.md](references/roles/dev.md) | 无状态执行者，worktree 内实现 |
| QA | [qa.md](references/roles/qa.md) | 只读验证，报告交 BA |

暂不设 Deploy / Explore 常驻角色。

## 只做什么

- 单机多 agent；
- WIP=1；
- feature worktree 隔离；
- 认领、队列、session；
- 读 docs 仓库的需求/验收，写回状态由 BA 负责。

## 不做什么

- 不改代码仓库的分支模型；
- 不建 `demand` / `deploy` 分支；bus 是可选审计分支；
- 不做跨机 claim；
- 不做完整 audit / verify / upgrade；
- 不替代现有 CI/CD 和消息系统；
- 不复制 workspace 版的 `aw.py`。

## 文档

- [单机 profile](references/single-profile.md)
- [工作流](references/workflow.md)
- [测试克制](references/testing.md)
- [会话与子 Agent 预算](references/session-budget.md)
- [换班协议 handoff / resume](references/handoff.md)
- [探索权唯一与 evidence](references/exploration.md)
- [任务预检与开工自检](references/task-sizing.md)
- [目录布局](references/layout.md)
- [Setup / 环境变量](references/setup.md)
- [omp 唤醒插件](references/omp.md)
- [DSH 唤醒插件](references/dsh.md)
- [MQTT + bus 协议](references/mqtt-bus-protocol.md)
