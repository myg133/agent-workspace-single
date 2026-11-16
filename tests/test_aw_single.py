import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "aw_single.py"


def run(args, cwd, env=None):
    full = dict(os.environ)
    full.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=full)


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class SingleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awsingle-"))
        self.code = self.tmp / "app"
        self.docs = self.tmp / "docs"
        self.code.mkdir()
        self.docs.mkdir()
        (self.docs / "demands").mkdir()
        git(["init", "-q", "-b", "main"], self.code)
        git(["config", "user.name", "t"], self.code)
        git(["config", "user.email", "t@t"], self.code)
        (self.code / "README.md").write_text("x\n", encoding="utf-8")
        git(["add", "."], self.code)
        git(["commit", "-q", "-m", "init"], self.code)
        self.env = {"AW_AGENT_ID": "ba-1", "AW_SESSION_ID": "sess-1"}
        out = run(["init", "--root", str(self.tmp), "--code-root", str(self.code),
                   "--docs-root", str(self.docs), "--base-branch", "main"], self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_and_whoami(self):
        cfg = json.loads((self.tmp / ".aw" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["profile"], "single")
        out = run(["whoami"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ba-1", out.stdout)
        session = json.loads((self.tmp / ".aw" / "sessions" / "ba-1.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(session["session_id"], "sess-1")

    def test_queue_and_claim_next(self):
        self.assertEqual(run(["queue", "add", "REQ-001", "--title", "x"],
                             self.tmp).returncode, 0)
        out = run(["claim", "next"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("CLAIMED REQ-001", out.stdout)
        wt = self.tmp / "worktrees" / "REQ-001"
        self.assertTrue(wt.is_dir())
        self.assertEqual(git(["branch", "--show-current"], wt).stdout.strip(),
                         "feature/REQ-001")
        again = run(["claim", "next"], self.tmp, self.env)
        self.assertEqual(again.returncode, 3)
        self.assertIn("ALREADY_HOLDING REQ-001", again.stdout)

    def test_take_and_release(self):
        self.assertEqual(run(["queue", "add", "REQ-002"], self.tmp).returncode, 0)
        out = run(["claim", "take", "REQ-002"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        rel = run(["claim", "release", "REQ-002"], self.tmp, self.env)
        self.assertEqual(rel.returncode, 0, rel.stderr)
        self.assertIn("RELEASED REQ-002", rel.stdout)
        self.assertFalse((self.tmp / ".aw" / "claims" / "REQ-002.json").exists())
        self.assertTrue(list((self.tmp / ".aw" / "archive").glob("REQ-002-*.json")))
        self.assertTrue((self.tmp / "worktrees" / "REQ-002").is_dir())

    def test_doctor_detects_missing_worktree(self):
        run(["queue", "add", "REQ-003"], self.tmp)
        self.assertEqual(run(["claim", "next"], self.tmp, self.env).returncode, 0)
        shutil.rmtree(self.tmp / "worktrees" / "REQ-003")
        out = run(["claim", "doctor"], self.tmp)
        self.assertEqual(out.returncode, 1)
        self.assertIn("missing-worktree", out.stdout)

    def test_missing_config(self):
        other = Path(tempfile.mkdtemp(prefix="awsingle-other-"))
        self.addCleanup(shutil.rmtree, other, True)
        out = run(["whoami"], other, self.env)
        self.assertEqual(out.returncode, 2)
        self.assertIn("找不到 .aw/config.json", out.stderr)

    def test_duplicate_queue(self):
        self.assertEqual(run(["queue", "add", "REQ-004"], self.tmp).returncode, 0)
        out = run(["queue", "add", "REQ-004"], self.tmp)
        self.assertEqual(out.returncode, 3)
        self.assertIn("ALREADY_QUEUED", out.stdout)

    def test_msg_send_inbox_ack(self):
        sent = run(["msg", "send", "--to", "ba-2", "--type", "question",
                    "--body", "ping"], self.tmp, self.env)
        self.assertEqual(sent.returncode, 0, sent.stderr)
        mid = sent.stdout.split()[1]
        inbox = run(["msg", "inbox"], self.tmp,
                    {"AW_AGENT_ID": "ba-2"})
        self.assertEqual(inbox.returncode, 0, inbox.stderr)
        self.assertIn(mid, inbox.stdout)
        ack = run(["msg", "ack", mid], self.tmp,
                  {"AW_AGENT_ID": "ba-2"})
        self.assertEqual(ack.returncode, 0, ack.stderr)
        self.assertIn("ACKED", ack.stdout)
        back = run(["msg", "inbox"], self.tmp, self.env)
        self.assertEqual(back.returncode, 0, back.stderr)
        self.assertIn("ACK", back.stdout)

    def test_msg_wait_timeout(self):
        out = run(["msg", "wait", "--timeout", "1"], self.tmp, self.env)
        self.assertEqual(out.returncode, 3)
        self.assertIn("NO_MESSAGES", out.stdout)

    def test_watch_once_writes_wake(self):
        sent = run(["msg", "send", "--to", "ba-1", "--type", "question",
                    "--body", "wake-me"], self.tmp, {"AW_AGENT_ID": "ba-2"})
        mid = sent.stdout.split()[1]
        first = run(["watch", "--once"], self.tmp)
        self.assertEqual(first.returncode, 0, first.stderr)
        wake = self.tmp / ".aw" / "wake" / "ba-1.json"
        self.assertTrue(wake.is_file())
        self.assertIn(mid, wake.read_text(encoding="utf-8"))
        second = run(["watch", "--once"], self.tmp)
        self.assertEqual(second.returncode, 3)

    def test_watch_ensure_start_stop(self):
        started = run(["watch", "--ensure", "--interval", "1"], self.tmp)
        self.assertEqual(started.returncode, 0, started.stderr)
        status = run(["watch", "--status"], self.tmp)
        self.assertIn("WATCH_RUNNING", status.stdout)
        stopped = run(["watch", "--stop"], self.tmp)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertIn("WATCH_STOPPED", stopped.stdout)

    def test_watch_status_stopped(self):
        out = run(["watch", "--status"], self.tmp)
        self.assertIn("WATCH_STOPPED", out.stdout)


if __name__ == "__main__":
    unittest.main()
