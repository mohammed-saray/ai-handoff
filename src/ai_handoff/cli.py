"""ai-handoff command-line interface."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .core import TARGETS, prompt_for, recent_requests, render, slug


def copy_to_clipboard(text: str) -> bool:
    for cmd in (["clip"], ["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, input=text.encode("utf-16le" if cmd[0] == "clip" else "utf-8"), check=True)
                return True
            except (OSError, subprocess.SubprocessError):
                continue
    return False


def _read(value):
    if value == "-":
        return sys.stdin.read()
    p = Path(value) if value and len(value) < 260 else None
    if p and p.is_file():
        return p.read_text(encoding="utf-8")
    return value or ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ai-handoff", description="Write a handoff file so another AI "
                                 "(Claude, Codex, Gemini, ChatGPT) can continue your task when you hit a limit.")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("create", help="write a handoff file (default)")
    c.add_argument("--goal", "-g", default="", help="what the task is (text or a file path)")
    c.add_argument("--done", "-d", default="", help="what is finished")
    c.add_argument("--next", "-n", dest="next_steps", default="", help="what to do next")
    c.add_argument("--blockers", "-b", default="")
    c.add_argument("--notes", default="", help="free notes; '-' reads stdin")
    c.add_argument("--to", choices=sorted(TARGETS), default="any", help="who continues (tailors the prompt)")
    c.add_argument("--dir", default=".", help="project root (default: .)")
    c.add_argument("--out", help="output path (default: docs/handoffs/<date>-<goal>.md)")
    c.add_argument("--no-logs", action="store_true", help="don't read recent requests from Claude/Codex logs")
    c.add_argument("--stdout", action="store_true", help="print the handoff instead of writing a file")
    c.add_argument("--copy", action="store_true", help="copy the ready-to-paste prompt to the clipboard")
    p = sub.add_parser("prompt", help="print the paste-ready prompt for an existing handoff")
    p.add_argument("file")
    p.add_argument("--to", choices=sorted(TARGETS), default="any")
    ls = sub.add_parser("list", help="list handoffs in docs/handoffs")
    ls.add_argument("--dir", default=".")
    ap.add_argument("--version", action="version", version=f"ai-handoff {__version__}")
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help", "--version"):
        argv.insert(0, "create")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if a.cmd == "prompt":
        path = Path(a.file)
        content = path.read_text(encoding="utf-8") if a.to == "chatgpt" else ""
        print(prompt_for(a.to, str(path).replace("\\", "/"), content))
        return 0
    if a.cmd == "list":
        d = Path(a.dir) / "docs" / "handoffs"
        files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
        for f in files:
            print(f"{datetime.fromtimestamp(f.stat().st_mtime):%Y-%m-%d %H:%M}  {f.as_posix()}")
        if not files:
            print("no handoffs yet — run `ai-handoff --goal \"...\"`")
        return 0

    root = Path(a.dir).resolve()
    goal = _read(a.goal)
    doc = render(root, goal=goal, done=_read(a.done), next_steps=_read(a.next_steps),
                 blockers=_read(a.blockers), notes=_read(a.notes), target=a.to,
                 requests=None if a.no_logs else recent_requests(root))
    if a.stdout:
        print(doc)
        return 0
    out = Path(a.out) if a.out else root / "docs" / "handoffs" / \
        f"{datetime.now():%Y-%m-%d-%H%M}-{slug(goal.splitlines()[0] if goal else root.name)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8", newline="\n")
    try:
        shown = out.resolve().relative_to(root).as_posix()
    except ValueError:
        shown = out.as_posix()
    prompt = prompt_for(a.to, shown, doc)
    print(f"✓ handoff written: {shown}  (~{len(doc) // 4} tokens)\n")
    print(f"Paste this into {TARGETS[a.to]}:\n")
    print(prompt if a.to != "chatgpt" else prompt[:300] + " …[full file content]")
    if a.copy:
        print("\n(copied to clipboard)" if copy_to_clipboard(prompt) else "\n(clipboard tool not found)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
