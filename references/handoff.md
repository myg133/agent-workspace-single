# 会话换班：handoff / resume

> **agent_id 是工位，session 是租约。** 换班不换 agent_id；本地 inbox、claim、已读集合都按 agent_id 走。

## 1. 命令

~~~bash
# 旧会话退出前
aw_single.py handoff --note "换班原因" --next-step "下一步" [--json]

# 新会话启动后（同一个 AW_AGENT_ID）
aw_single.py resume [--json]
~~~

## 2. handoff 做什么

- 读取本地 inbox，收集未读消息和 `expect=ack/reply` 的未结消息；
- 写入 `.aw/handoff/<agent_id>.json`（只存 id / 类型 / 主题 / 状态，不存正文）；
- 把 `.aw/sessions/<agent_id>.json` 标记为 `offline`，`pid=0`；
- 把 `.aw/wake-seen/<agent_id>.json` 重置为“已读集合”，让未读消息重新可唤醒、已读不重复；
- **保留 claim**，不释放、不改 docs/status；
- **不推进已读**，不会替新会话消费消息。

## 3. resume 做什么

- 读 `.aw/handoff/<agent_id>.json`；
- 写 `resumed_at` / `resumed_session_id`；
- 重新设置 wake-seen，让未读消息还能叫醒新会话；
- 打印当前 claim、未处理消息、换班备注和下一步；
- **不消费消息**，新会话仍需 `msg inbox` / `msg ack` 处理。

## 4. 换班流程

### 旧会话

1. 停止接新任务；claim 保持；
2. 只读盘点：
   ~~~text
   aw_single.py msg inbox --peek --json
   ~~~
3. 写 handoff：
   ~~~bash
   aw_single.py handoff --note "BA 值班换班" --next-step "先处理未读消息"
   ~~~
4. 停止旧进程；
5. 不要为了换班去 `claim release`。

### 新会话

1. 用**同一个 `AW_AGENT_ID`** 启动；
2. 显式设置 `AW_SESSION_ID`，不要依赖自动生成（自动 session 不写 map）；
3. `aw_single.py whoami` 更新 session 文件 / map；
4. `aw_single.py resume`；
5. 按 handoff 里的 id 处理消息，处理完再消费；
6. `aw_single.py claim list` 确认 claim 还在；
7. 启动/接管 watcher。

## 5. 状态边界

| 状态 | 按什么 | 换 session 后 |
|------|--------|--------------|
| inbox / 已读集合 | agent_id | 保留 |
| claim / WIP | agent_id | 保留 |
| session 文件 / map | session_id | 新会话覆盖 |
| wake-seen | agent_id | handoff 重置为已读集合 |
| 终端 / 进程 | 进程 | 旧进程必须停 |

## 6. 常见错误

| 错误 | 后果 | 正确做法 |
|------|------|----------|
| 新会话用了新 agent_id | 新 inbox、新 claim，看起来"消息丢了" | 始终复用同一个 agent_id |
| 旧进程还活着 | 两个会话抢同一 inbox | 先停旧进程 |
| 用自动生成的 session | 不写 map，watcher 路由不到新会话 | 显式设置 `AW_SESSION_ID` |
| handoff 前已读消息 | 新会话看不到未处理项 | 用 `--peek` 盘点，handoff 记录未处理 id |
| 换班时 release claim | 任务回到队列，别人可能领走 | 只 handoff，claim 保留 |
| 不清 wake-seen | 新会话不被未读叫醒 | handoff 自动重置 |

## 7. 常驻模式

- **常驻的是 watcher + agent 工位，不是模型会话**；
- BA 值班会话只做 triage / claim / 派单，默认 ≤20–30 轮；
- 到换班点或上下文阈值，handoff → 停旧会话 → 新会话 resume；
- Dev / QA 每个任务一个短会话，完成后退出；
- Planner 按需短会话，计划/ADR 写文件，不靠聊天记忆。

完整预算见 [session-budget.md](session-budget.md)。
