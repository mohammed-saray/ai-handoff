import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_handoff.core import detect_commands, git_state, prompt_for, recent_requests, render, slug, todos

HAS_GIT = shutil.which("git") is not None


def run(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "my-app"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_detect_commands(self):
        (self.root / "package.json").write_text(json.dumps({"scripts": {"test": "x", "build": "y"}}))
        (self.root / "pnpm-lock.yaml").write_text("")
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        self.assertEqual(detect_commands(self.root), ["pnpm test", "pnpm build", "pytest"])

    def test_not_a_repo(self):
        doc = render(self.root, goal="Fix login", state={"is_repo": False})
        self.assertIn("# Handoff — my-app", doc)
        self.assertIn("## Goal\n\nFix login", doc)
        self.assertNotIn("Repository state", doc)

    @unittest.skipUnless(HAS_GIT, "git not installed")
    def test_git_repo_state_and_todos(self):
        run(self.root, "init", "-q")
        run(self.root, "config", "user.email", "t@example.com")
        run(self.root, "config", "user.name", "T")
        (self.root / "a.py").write_text("print(1)\n")
        run(self.root, "add", ".")
        run(self.root, "commit", "-qm", "first commit")
        (self.root / "a.py").write_text("print(2)  # TODO: handle errors\n")
        (self.root / "b.py").write_text("x = 1\n")
        st = git_state(self.root)
        self.assertTrue(st["is_repo"])
        self.assertEqual(sorted(c["path"] for c in st["changed"]), ["a.py", "b.py"])
        self.assertIn("first commit", st["log"])
        self.assertEqual(todos(self.root, ["a.py"]), ["a.py:1 TODO handle errors"])
        doc = render(self.root, goal="g", next_steps="- write tests", target="codex", state=st)
        for part in ("## Repository state", "## Changed files", "## Recent commits",
                     "## TODO / FIXME", "Codex CLI", "- write tests"):
            self.assertIn(part, doc)

    def test_recent_requests_from_logs(self):
        home = Path(self.tmp.name) / "home"
        cdir = home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.root.resolve()))
        cdir.mkdir(parents=True)
        rows = [
            {"type": "user", "message": {"role": "user", "content": "add dark mode to settings"}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}},
            {"type": "user", "isMeta": True, "message": {"content": "<command>meta</command>"}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "also fix the tests"}]}},
        ]
        (cdir / "s.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        sess = home / ".codex" / "sessions" / "2026"
        sess.mkdir(parents=True)
        (sess / "r.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"type": "session_meta", "payload": {"cwd": str(self.root)}},
            {"type": "event_msg", "payload": {"type": "user_message", "message": "port it to rust"}},
        ]), encoding="utf-8")
        old = os.environ.pop("CODEX_HOME", None)
        try:
            found = recent_requests(self.root, home=home)
        finally:
            if old is not None:
                os.environ["CODEX_HOME"] = old
        self.assertEqual(found["claude"], ["add dark mode to settings", "also fix the tests"])
        self.assertEqual(found["codex"], ["port it to rust"])
        doc = render(self.root, state={"is_repo": False}, requests=found)
        self.assertIn("> add dark mode to settings", doc)

    def test_prompts_and_slug(self):
        self.assertIn("docs/handoffs/x.md", prompt_for("gemini", "docs/handoffs/x.md"))
        self.assertIn("BODY", prompt_for("chatgpt", "p", "BODY"))
        self.assertEqual(slug("Fix the Login bug!!"), "fix-the-login-bug")
        self.assertEqual(slug("إصلاح الدخول"), "إصلاح-الدخول")

    def test_cli_writes_file(self):
        from ai_handoff import cli
        self.assertEqual(cli.main(["--goal", "Ship v2", "--dir", str(self.root), "--no-logs"]), 0)
        files = list((self.root / "docs" / "handoffs").glob("*ship-v2.md"))
        self.assertEqual(len(files), 1)
        self.assertIn("Ship v2", files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
