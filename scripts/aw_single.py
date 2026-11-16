#!/usr/bin/env python3
"""agent-workspace-single: 单机、双仓、传统分支的轻量协作层。

只负责本地 claim / queue / feature worktree；不写 docs 状态，不创建
demand/bus/deploy 分支。依赖 Python 3.8+ 标准库与 git。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

REQ_RE = re.compile(r"^REQ-\d{3,}$")
STATE_DIR = ".aw"


class ToolError(RuntimeError):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _init_console() -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _win_no_window() -> dict:
    if os.name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def git(*args: str, cwd: Path | str, check: bool = True,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        **_win_no_window(),
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ToolError("git %s 失败: %s" % (" ".join(args), detail), 1)
    return proc


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.%d.%s.tmp" % (path.name, os.getpid(), secrets.token_hex(3)))
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class FileLock:
    """跨进程锁；Windows msvcrt，POSIX fcntl。"""

    def __init__(self, path: Path, timeout: float = 10.0):
        self.path = path
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.time() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() >= deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise ToolError("等待 claim 锁超时: %s" % self.path, 1)
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None


def _find_config(args) -> Path:
    explicit = getattr(args, "config", None) or os.environ.get("AW_SINGLE_CONFIG")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            path = path / STATE_DIR / "config.json"
        if not path.is_file():
            raise ToolError("配置文件不存在: %s" % path, 2)
        return path.resolve()
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / STATE_DIR / "config.json"
        if candidate.is_file():
            return candidate
    raise ToolError("找不到 .aw/config.json；先运行 aw_single.py init", 2)


def load_config(args) -> tuple[Path, dict]:
    path = _find_config(args)
    data = read_json(path, None)
    if not isinstance(data, dict):
        raise ToolError("配置文件不是合法 JSON: %s" % path, 2)
    root = path.parent.parent
    required = ("code_root", "docs_root", "base_branch", "worktree_root")
    missing = [k for k in required if not str(data.get(k) or "").strip()]
    if missing:
        raise ToolError("配置缺字段: %s" % ", ".join(missing), 2)
    for key in ("code_root", "docs_root", "worktree_root"):
        value = Path(str(data[key])).expanduser()
        if not value.is_absolute():
            value = root / value
        data[key] = str(value.resolve())
    data.setdefault("branch_prefix", "feature/")
    data.setdefault("demand_dir", "demands")
    if not Path(data["code_root"]).is_dir():
        raise ToolError("code_root 不存在: %s" % data["code_root"], 2)
    if not Path(data["docs_root"]).is_dir():
        raise ToolError("docs_root 不存在: %s" % data["docs_root"], 2)
    return root, data


def _session() -> tuple[str, str]:
    for key in ("AW_SESSION_ID", "PI_SESSION_ID", "DSH_SESSION_ID", "CLAUDE_SESSION_ID"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value, key
    return "proc-%d" % os.getpid(), "generated"


def _identity(args) -> dict:
    agent = (getattr(args, "agent", None) or os.environ.get("AW_AGENT_ID") or "").strip()
    if not agent:
        raise ToolError("MISSING_AGENT_ID\n提供 --agent 或设置 AW_AGENT_ID", 2)
    sid, source = _session()
    return {"agent_id": agent, "session_id": sid, "session_source": source}


def _record_session(root: Path, ident: dict) -> None:
    path = root / STATE_DIR / "sessions" / ("%s.json" % ident["agent_id"])
    old = read_json(path, {})
    sid = ident["session_id"]
    source = ident["session_source"]
    if source == "generated" and old.get("session_id") and old.get("session_source") != "generated":
        sid = old["session_id"]
        source = old.get("session_source") or source
    write_json(path, {
        "agent_id": ident["agent_id"],
        "session_id": sid,
        "session_source": source,
        "started_at": old.get("started_at") or _now(),
        "last_seen": _now(),
        "pid": os.getpid(),
        "host": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", ""),
    })


def _claims(root: Path) -> list[dict]:
    out = []
    for path in sorted((root / STATE_DIR / "claims").glob("*.json")):
        data = read_json(path, None)
        if isinstance(data, dict) and data.get("req"):
            data["_path"] = str(path)
            out.append(data)
    return out


def _holding(claims: list[dict], agent: str) -> dict | None:
    return next((c for c in claims
                 if c.get("agent_id") == agent and c.get("state") == "active"), None)


def _claim_path(root: Path, req: str) -> Path:
    return root / STATE_DIR / "claims" / ("%s.json" % req)


def _queue(root: Path) -> list[dict]:
    data = read_json(root / STATE_DIR / "queue.json", [])
    return data if isinstance(data, list) else []


def _save_queue(root: Path, queue: list[dict]) -> None:
    write_json(root / STATE_DIR / "queue.json", queue)


def _resolve_base(cfg: dict) -> str:
    proc = git("rev-parse", "--verify", cfg["base_branch"], cwd=cfg["code_root"], check=False)
    if proc.returncode != 0:
        raise ToolError("base_branch 不存在: %s" % cfg["base_branch"], 2)
    return proc.stdout.strip()


def _create_claim(root: Path, cfg: dict, ident: dict, req: str, title: str = "") -> dict:
    base_sha = _resolve_base(cfg)
    branch = "%s%s" % (cfg["branch_prefix"], req)
    worktree = str(Path(cfg["worktree_root"]) / req)
    claim = {
        "req": req,
        "title": title,
        "agent_id": ident["agent_id"],
        "session_id": ident["session_id"],
        "session_source": ident["session_source"],
        "branch": branch,
        "worktree": worktree,
        "base_branch": cfg["base_branch"],
        "base_sha": base_sha,
        "state": "active",
        "claimed_at": _now(),
    }
    write_json(_claim_path(root, req), claim)
    return claim


def _finish_claim(root: Path, cfg: dict, claim: dict) -> None:
    code = Path(cfg["code_root"])
    worktree = Path(claim["worktree"])
    branch = claim["branch"]
    if worktree.exists():
        _rollback_claim(root, claim)
        raise ToolError("worktree 已存在: %s" % worktree, 3)
    proc = git("show-ref", "--verify", "--quiet", "refs/heads/%s" % branch,
               cwd=code, check=False)
    if proc.returncode == 0:
        _rollback_claim(root, claim)
        raise ToolError("分支已存在: %s" % branch, 3)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    proc = git("worktree", "add", "-b", branch, str(worktree), cfg["base_branch"],
               cwd=code, check=False, timeout=120)
    if proc.returncode != 0:
        _rollback_claim(root, claim)
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ToolError("CLAIM_FAILED 创建 worktree 失败: %s" % detail, 1)


def _rollback_claim(root: Path, claim: dict) -> None:
    try:
        _claim_path(root, claim["req"]).unlink(missing_ok=True)
    except OSError:
        pass
    queue = _queue(root)
    if not any(q.get("req") == claim["req"] for q in queue):
        queue.append({"req": claim["req"], "title": claim.get("title", ""), "added_at": _now()})
        _save_queue(root, queue)


def _claim_next(root: Path, cfg: dict, ident: dict) -> int:
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claims = _claims(root)
        mine = _holding(claims, ident["agent_id"])
        if mine:
            print("ALREADY_HOLDING %s" % mine["req"])
            return 3
        queue = _queue(root)
        taken = {c["req"] for c in claims if c.get("state") == "active"}
        candidate = next((q for q in queue if q.get("req") not in taken), None)
        if not candidate:
            print("QUEUE_EMPTY")
            return 3
        req = candidate["req"]
        claim = _create_claim(root, cfg, ident, req, candidate.get("title", ""))
        _save_queue(root, [q for q in queue if q.get("req") != req])
    _finish_claim(root, cfg, claim)
    print("CLAIMED %s" % req)
    return 0


def _claim_take(root: Path, cfg: dict, ident: dict, req: str) -> int:
    req = req.strip().upper()
    if not REQ_RE.match(req):
        raise ToolError("REQ 格式应为 REQ-001", 2)
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claims = _claims(root)
        mine = _holding(claims, ident["agent_id"])
        if mine:
            print("ALREADY_HOLDING %s" % mine["req"])
            return 3
        existing = next((c for c in claims
                         if c.get("req") == req and c.get("state") == "active"), None)
        if existing:
            print("TAKEN_BY %s" % existing.get("agent_id", "?"))
            return 3
        queue = _queue(root)
        title = next((q.get("title", "") for q in queue if q.get("req") == req), "")
        claim = _create_claim(root, cfg, ident, req, title)
        _save_queue(root, [q for q in queue if q.get("req") != req])
    _finish_claim(root, cfg, claim)
    print("CLAIMED %s" % req)
    return 0


def _claim_release(root: Path, cfg: dict, ident: dict, req: str,
                   force: bool = False, remove_worktree: bool = False) -> int:
    req = req.strip().upper()
    claim = read_json(_claim_path(root, req), None)
    if not isinstance(claim, dict):
        print("NOT_CLAIMED %s" % req)
        return 3
    if claim.get("agent_id") != ident["agent_id"] and not force:
        print("NOT_YOURS %s（属于 %s）" % (req, claim.get("agent_id")))
        return 3
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claim["state"] = "released"
        claim["released_at"] = _now()
        archive = root / STATE_DIR / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
        write_json(archive / ("%s-%s.json" % (req, stamp)), claim)
        _claim_path(root, req).unlink(missing_ok=True)
    if remove_worktree:
        wt = Path(claim["worktree"])
        if wt.exists():
            dirty = git("status", "--porcelain", cwd=wt, check=False).stdout.strip()
            if dirty and not force:
                print("RELEASED %s（worktree 有未提交改动，已保留）" % req)
                return 0
            git("worktree", "remove", str(wt), cwd=cfg["code_root"], check=False)
    print("RELEASED %s" % req)
    return 0


def _claim_list(root: Path) -> int:
    claims = _claims(root)
    if not claims:
        print("（无认领）")
        return 0
    rows = [["REQ", "agent", "state", "branch", "worktree"]]
    for c in claims:
        rows.append([c["req"], c.get("agent_id", "-"), c.get("state", "-"),
                     c.get("branch", "-"), c.get("worktree", "-")])
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))
    return 0


def _claim_doctor(root: Path, cfg: dict) -> int:
    claims = _claims(root)
    problems = []
    by_agent = {}
    for c in claims:
        if c.get("state") != "active":
            continue
        by_agent.setdefault(c.get("agent_id", "?"), []).append(c)
        wt = Path(c.get("worktree", ""))
        if not wt.is_dir():
            problems.append("[missing-worktree] %s %s" % (c["req"], wt))
            continue
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt, check=False).stdout.strip()
        if branch and c.get("branch") and branch != c["branch"]:
            problems.append("[branch-mismatch] %s: claim=%s actual=%s"
                            % (c["req"], c["branch"], branch))
    for agent, items in by_agent.items():
        if len(items) > 1:
            problems.append("[multi-claim] %s: %s" %
                            (agent, ", ".join(c["req"] for c in items)))
    active_names = {c["req"] for c in claims if c.get("state") == "active"}
    wt_root = Path(cfg["worktree_root"])
    if wt_root.is_dir():
        for p in wt_root.iterdir():
            if p.is_dir() and REQ_RE.match(p.name) and p.name not in active_names:
                problems.append("[orphan-worktree] %s" % p)
    if not problems:
        print("OK 没有发现问题（%d 个认领）" % len(claims))
        return 0
    for item in problems:
        print(item)
    return 1


def cmd_init(args) -> int:
    root = Path(args.root).expanduser().resolve()
    code = Path(args.code_root).expanduser().resolve()
    docs = Path(args.docs_root).expanduser().resolve()
    if not code.is_dir():
        raise ToolError("code_root 不存在: %s" % code, 2)
    if not docs.is_dir():
        raise ToolError("docs_root 不存在: %s" % docs, 2)
    proc = git("rev-parse", "--show-toplevel", cwd=code, check=False)
    if proc.returncode != 0:
        raise ToolError("code_root 不是 git 仓库: %s" % code, 2)
    top = Path(proc.stdout.strip()).resolve()
    if top != code:
        raise ToolError("code_root 必须是 git 仓库根: %s" % top, 2)
    proc = git("rev-parse", "--verify", args.base_branch, cwd=code, check=False)
    if proc.returncode != 0:
        raise ToolError("base_branch 不存在: %s" % args.base_branch, 2)
    state = root / STATE_DIR
    if (state / "config.json").exists():
        raise ToolError("已经初始化: %s" % (state / "config.json"), 2)
    for name in ("claims", "sessions", "locks", "archive"):
        (state / name).mkdir(parents=True, exist_ok=True)
    if args.worktree_root:
        wt_value = Path(args.worktree_root).expanduser()
        worktree_root = wt_value.resolve() if wt_value.is_absolute() else (root / wt_value).resolve()
    else:
        worktree_root = (root / "worktrees").resolve()
    worktree_root.mkdir(parents=True, exist_ok=True)
    config = {
        "profile": "single",
        "version": 1,
        "code_root": str(code),
        "docs_root": str(docs),
        "base_branch": args.base_branch,
        "worktree_root": str(worktree_root),
        "branch_prefix": args.branch_prefix,
        "demand_dir": args.demand_dir,
    }
    write_json(state / "config.json", config)
    if not (state / "queue.json").exists():
        write_json(state / "queue.json", [])
    print("INITIALIZED %s" % root)
    return 0


def cmd_whoami(args) -> int:
    root, _cfg = load_config(args)
    ident = _identity(args)
    _record_session(root, ident)
    print("agent_id  : %s" % ident["agent_id"])
    print("session   : %s" % ident["session_id"])
    print("source    : %s" % ident["session_source"])
    print("repo      : %s" % root)
    return 0


def cmd_queue(args) -> int:
    root, _cfg = load_config(args)
    action = args.action
    if action == "add":
        req = args.req.strip().upper()
        if not REQ_RE.match(req):
            raise ToolError("REQ 格式应为 REQ-001", 2)
        with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
            queue = _queue(root)
            if any(q.get("req") == req for q in queue):
                print("ALREADY_QUEUED %s" % req)
                return 3
            queue.append({"req": req, "title": args.title or "", "added_at": _now()})
            _save_queue(root, queue)
        print("QUEUED %s" % req)
        return 0
    if action == "list":
        queue = _queue(root)
        if not queue:
            print("（队列为空）")
            return 0
        for q in queue:
            print("%s\t%s\t%s" % (q.get("req", ""), q.get("title", ""), q.get("added_at", "")))
        return 0
    raise ToolError("未知 queue 操作: %s" % action, 2)


def cmd_claim(args) -> int:
    root, cfg = load_config(args)
    action = args.action
    if action == "list":
        return _claim_list(root)
    if action == "doctor":
        return _claim_doctor(root, cfg)
    ident = _identity(args)
    _record_session(root, ident)
    if action == "next":
        return _claim_next(root, cfg, ident)
    if action == "take":
        if not args.req:
            raise ToolError("用法: claim take REQ-001", 2)
        return _claim_take(root, cfg, ident, args.req)
    if action == "release":
        if not args.req:
            raise ToolError("用法: claim release REQ-001", 2)
        return _claim_release(root, cfg, ident, args.req,
                              force=args.force, remove_worktree=args.remove_worktree)
    raise ToolError("未知 claim 操作: %s" % action, 2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aw_single.py", description="单机双仓 Agent 协作")
    parser.add_argument("--config", default=None, help=".aw/config.json 或其目录")
    parser.add_argument("--agent", default=None, help="agent_id（优先于 AW_AGENT_ID）")
    parser.add_argument("--session", default=None, help="session_id")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化本地 .aw 配置")
    p_init.add_argument("--root", default=".", help="本地根目录，默认当前目录")
    p_init.add_argument("--code-root", required=True)
    p_init.add_argument("--docs-root", required=True)
    p_init.add_argument("--base-branch", default="develop")
    p_init.add_argument("--worktree-root", default=None)
    p_init.add_argument("--branch-prefix", default="feature/")
    p_init.add_argument("--demand-dir", default="demands")
    p_init.set_defaults(func=cmd_init)

    p_who = sub.add_parser("whoami")
    p_who.set_defaults(func=cmd_whoami)

    p_q = sub.add_parser("queue")
    p_q.add_argument("action", choices=["add", "list"])
    p_q.add_argument("req", nargs="?", default="")
    p_q.add_argument("--title", default="")
    p_q.set_defaults(func=cmd_queue)

    p_c = sub.add_parser("claim")
    p_c.add_argument("action", choices=["next", "take", "release", "list", "doctor"])
    p_c.add_argument("req", nargs="?", default="")
    p_c.add_argument("--force", action="store_true")
    p_c.add_argument("--remove-worktree", action="store_true")
    p_c.set_defaults(func=cmd_claim)

    for sp in sub.choices.values():
        sp.add_argument("--agent", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--session", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    _init_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "session", None):
        os.environ["AW_SESSION_ID"] = args.session
    try:
        return args.func(args)
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except OSError as exc:
        print("系统错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
