# 单机工作流

## 1. 角色

| 角色 | 职责 |
|------|------|
| Planner（可选） | 优先级、跨 BA 边界；首版不强制 |
| BA | 需求、验收、状态；唯一写 docs 状态的人 |
| Dev | 在 feature worktree 实现，handoff 后退出 |
| QA | 只读验证，报告交 BA |

没有 Deploy 角色；部署继续用现有流程。

## 2. BA

1. 在 docs 仓库创建 `demands/REQ-xxx/`；
2. 写 `demand.md` / `acceptance.md` / `status.md`；
3. `aw_single.py queue add REQ-xxx`；
4. `aw_single.py claim next`；
5. 把 worktree 路径、docs 路径、base sha 交给 Dev。

## 3. Dev

1. 只读 docs；
2. 在 worktree 实现；
3. 跑提交前快速门禁；
4. 写 `feature-meta/verification-report.md`；
5. 发 handoff，退出；
6. 不等 QA，不修改 docs 的 `status.md`。

## 4. QA

1. 只读 docs + worktree；
2. 跑验证；
3. 报告交 BA；
4. 不提交、不改状态。

## 5. 返工

- BA 在 docs 的 `status.md` 写 `return_reason`；
- BA spawn 新 Dev；
- 新 Dev 只读上一版报告 + return_reason，继续同一 worktree。

## 6. 消息

首版不使用 bus：

- 同一团队用现有聊天/Issue/PR；
- 需要审计的结论写进 docs 的 `decisions.md` 或 PR 描述；
- 不新增消息格式。

## 7. 状态

docs 的 `status.md` 仍是唯一事实：

```text
草稿 → 已就绪 → 进行中 → 待验证 → 已验证 → 已完成
```

`aw_single.py` 不写 status，只负责 claim/worktree。
