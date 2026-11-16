# agent-workspace-single

单机版的轻量 Agent 协作层：**传统代码仓库 + 独立文档仓库 + 本地 `.aw/`**。

它不要求把现有项目改造成 workspace 布局，也不创建 `demand` / `bus` / `deploy` 孤立分支。

- 代码仓库保持原样（通常 `main` / `develop` / `feature/*`）；
- 需求、验收、状态继续放在现有文档仓库；
- feature worktree 放在独立的 `worktrees/` 目录；
- 认领、WIP、session 放在本地 `.aw/`，不提交到任何仓库。

## 状态

当前是 **设计骨架**，还没有 `aw_single.py` 实现。

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

## 只做什么

- 单机多 agent；
- WIP=1；
- feature worktree 隔离；
- 认领、队列、session；
- 读 docs 仓库的需求/验收，写回状态由 BA 负责。

## 不做什么

- 不改代码仓库的分支模型；
- 不建 `demand` / `bus` / `deploy` 分支；
- 不做跨机 claim；
- 不做完整 audit / verify / upgrade；
- 不替代现有 CI/CD 和消息系统；
- 不复制 workspace 版的 `aw.py`。

## 文档

- [单机 profile](references/single-profile.md)
- [工作流](references/workflow.md)
- [目录布局](references/layout.md)
