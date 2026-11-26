---
name: agent-workspace-single
description: 单机、双仓（代码仓库 + 文档仓库）、传统分支模型下的轻量多 Agent 协作层。用于已有项目不想改造成 workspace 布局，但需要 WIP=1、feature worktree 隔离、认领和交接的场景。单机消息、本地 inbox、可选 MQTT 已支持；不适用于需要 workspace 分支模型的场景。
metadata:
  short-description: 单机双仓 Agent 协作
  version: 0.6.5
---

# agent-workspace-single

> **合并状态（2026-11-26）**：本 skill 已并入 `agent-workspace` 2.0.0 的 single 模式；
> 本仓库保留兼容入口，新安装优先使用主 skill。

这是 `agent-workspace` 的单机精简版，只解决三件事：

1. 一个 agent 同时只持有一个需求（WIP=1）；
2. 每个需求一个独立 feature worktree；
3. 需求文档在另一个仓库时，仍能完成认领、交接和状态追踪。

它**不改造**代码仓库，也不建 `demand` / `deploy` 分支；消息走本地 inbox，可选 bus 审计 / MQTT。

## 何时使用

- 已有传统 `main/develop/feature/*` 仓库；
- 文档在独立仓库；
- 单机多 agent（BA/Dev/QA）；
- 不想引入 workspace orphan 根；bus 审计可选。

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

## 会话预算（默认）

- 主会话 ≤60 轮 / 8 万上下文，硬上限 100 轮 / 10 万；到阈值 handoff 换新会话；
- 一个 REQ 最多 2–3 个子 Agent；没有 diff 预期的任务不 spawn；
- 探索 / 文档 / status 用低成本模型，复杂实现 / 关键 review 才用强模型；
- 完整规则、会话任务卡、度量与反模式见 `references/session-budget.md`。

## 探索权唯一

- BA 只做业务、验收、文档、接口探索；代码探索交给 Dev（或 BA 自己实现时由本人做）；
- 一个任务只有一个代码探索 owner；不允许 BA 深读一遍、Dev 再重读一遍；
- Fresh 子 Agent 默认零上下文，任务卡必须带 evidence（已确认/待验证/不要重读）；
- 规则与模板见 `references/exploration.md`、`templates/exploration-evidence.md.tpl`。

## 任务预检与开工自检

- BA 下派前判断任务大小：模块/文件/AC/依赖/切片/预算；太大就拆，不把整个功能交给一个子 Agent；
- 子 Agent 只做开工自检：evidence 对 HEAD、入口存在、测试命令可执行；
- 自检失败返回 `EVIDENCE_STALE` / `TASK_TOO_BIG` / `MISSING_ENTRY`，不自己重新拆任务；
- 第一次 compaction 就停，不要连续压缩；规则见 `references/task-sizing.md`。

## 写入目录限定

所有写文件必须落在 `<local-root>` 或当前 worktree 内。

- 临时文件：`<local-root>/.aw/tmp/`
- 导出 / 截图 / 日志：`<local-root>/.aw/exports/<REQ>/`
- 随需求提交的证据：`<docs_root>/demands/<REQ>/evidence/`（BA 写）
- 禁止：盘根、`C:/tmp`、`D:/tmp`、`%TEMP%`、Desktop、Downloads、`..` 逃逸
- 工具必须用系统临时目录时：改 `TMP/TEMP/TMPDIR` 到 `.aw/tmp`，或复制回项目内并清理

详见 `references/layout.md`。

## 子 Agent 不接消息

spawn 子 Agent 时设置：

~~~text
AW_SUBAGENT=1
AW_NO_MSG=1
AW_ROLE=dev      # 或 qa / explore
AW_SESSION_ID=<子会话 id>
~~~

- `aw_single.py msg / watch / claim / whoami / handoff / resume / bus / queue` 对子 Agent 直接拒绝，返回 `SUBAGENT_NO_*`；
- OMP `aw-single-wake` 只允许 authoritative session：当前 `AW_SESSION_ID` / `PI_SESSION_ID` 必须等于 `.aw/sessions/<agent>.map.json` 的 `session_id`；
- 子 Agent 的结果交回父 BA，不走 bus。详见 `references/omp.md`。

## 换班（handoff / resume）

常驻 BA / Planner 换班不要新建 `agent_id`：

~~~bash
aw_single.py handoff --note "换班" --next-step "..."
# 新会话：同一个 AW_AGENT_ID + 显式 AW_SESSION_ID
aw_single.py whoami
aw_single.py resume
~~~

handoff 保留 claim、记录未读/待回复消息、重置 wake-seen；resume 不消费消息。
详见 `references/handoff.md`。

## 依赖

MQTT 库已 vendor 到 `vendor/paho/`（paho-mqtt 2.2.0），不需要安装依赖。

## 入口

先读：

- `references/setup.md`
- `references/single-profile.md`
- `references/workflow.md`
- `references/testing.md`
- `references/session-budget.md`
- `references/handoff.md`
- `references/exploration.md`
- `references/task-sizing.md`
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
# 已有分支/worktree 被孤儿认领占用时，保留现场并转给当前 BA
python scripts/aw_single.py claim adopt REQ-001 --branch feature/REQ-001

python scripts/aw_single.py msg send --to ba-1 --type question --body "ping"
python scripts/aw_single.py msg report --subject "用户新任务" --body "REQ-001：目标 / 优先级 / 预期"
python scripts/aw_single.py msg inbox
python scripts/aw_single.py msg wait --timeout 120
python scripts/aw_single.py watch --ensure --exec "bash start-agent.sh"
```
