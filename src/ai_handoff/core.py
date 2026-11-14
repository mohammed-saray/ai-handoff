"""Collect project state and render a model-agnostic handoff document."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

TARGETS = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI / Antigravity",
    "chatgpt": "ChatGPT (web)",
    "copilot": "GitHub Copilot",
    "any": "the next AI assistant",
}


def git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    # rstrip only: porcelain status lines start with a meaningful space
    return out.stdout.rstrip() if out.returncode == 0 else ""


def git_state(root: Path, commits: int = 8) -> dict:
    if not git(root, "rev-parse", "--is-inside-work-tree"):
        return {"is_repo": False}
    status = git(root, "status", "--porcelain=v1")
    changed = []
    for line in status.splitlines():
        if len(line) > 3:
            path = line[3:].split(" -> ")[-1].strip().strip('"')
            changed.append({"status": line[:2].strip() or "?", "path": path})
    return {
        "is_repo": True,
        "branch": git(root, "rev-parse", "--abbrev-ref", "HEAD") or "(detached)",
        "head": git(root, "rev-parse", "--short", "HEAD"),
        "upstream": git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        "ahead_behind": git(root, "rev-list", "--left-right", "--count", "@{u}...HEAD"),
        "log": git(root, "log", f"-{commits}", "--pretty=format:%h %ad %s", "--date=short"),
        "changed": changed,
        "diffstat": git(root, "diff", "HEAD", "--stat") if git(root, "rev-parse", "HEAD") else "",
    }


def detect_commands(root: Path) -> List[str]:
    cmds = []
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {})
        except ValueError:
            scripts = {}
        runner = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm run"
        for name in ("test", "lint", "typecheck", "build", "dev"):
            if name in scripts:
                cmds.append(f"{runner} {name}")
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace") if (root / "pyproject.toml").is_file() else ""
        cmds.append("pytest" if "pytest" in text or (root / "pytest.ini").exists() else "python -m unittest discover")
    if (root / "Cargo.toml").is_file():
        cmds.append("cargo test")
    if (root / "go.mod").is_file():
        cmds.append("go test ./...")
    mk = root / "Makefile"
    if mk.is_file():
        targets = re.findall(r"^([a-zA-Z][\w-]*):", mk.read_text(encoding="utf-8", errors="replace"), re.M)
        cmds += [f"make {t}" for t in targets if t in ("test", "lint", "build", "check")]
    return cmds


TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.{0,120})")


def todos(root: Path, paths: List[str], limit: int = 20) -> List[str]:
    out = []
    for rel in paths:
        p = root / rel
        if not p.is_file() or p.stat().st_size > 500_000:
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = TODO_RE.search(line)
                if m:
                    out.append(f"{rel}:{i} {m.group(1)} {m.group(2).strip()}")
                    if len(out) >= limit:
                        return out
        except OSError:
            continue
    return out


# --------------------------------------------------------------------------- agent transcripts

def _claude_project_dir(root: Path, home: Path) -> Path:
    return home / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))


def _user_texts_from_claude(path: Path) -> List[str]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
            continue
        content = (rec.get("message") or {}).get("content")
        text = content if isinstance(content, str) else " ".join(
            c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text")
        text = text.strip()
        if text and not text.startswith("<") and "tool_result" not in text[:40]:
            out.append(text)
    return out


def _user_texts_from_codex(path: Path, root: Path) -> Optional[List[str]]:
    out, cwd_ok = [], False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        p = rec.get("payload") or {}
        if not isinstance(p, dict):
            continue
        cwd = p.get("cwd")
        if cwd and Path(cwd).resolve() == root.resolve():
            cwd_ok = True
        if rec.get("type") == "event_msg" and p.get("type") == "user_message" and p.get("message"):
            out.append(str(p["message"]).strip())
    return out if cwd_ok else None


def recent_requests(root: Path, home: Optional[Path] = None, n: int = 5, max_chars: int = 600) -> dict:
    """Last user requests from the newest Claude Code and Codex sessions for this folder."""
    home = home or Path.home()
    found = {}
    cdir = _claude_project_dir(root, home)
    if cdir.is_dir():
        files = sorted(cdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:3]:
            texts = _user_texts_from_claude(f)
            if texts:
                found["claude"] = [t[:max_chars] for t in texts[-n:]]
                break
    codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    sess = codex_home / "sessions"
    if sess.is_dir():
        files = sorted(sess.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:40]:
            texts = _user_texts_from_codex(f, root)
            if texts:
                found["codex"] = [t[:max_chars] for t in texts[-n:]]
                break
    return found


# --------------------------------------------------------------------------- rendering

def render(root: Path, *, goal: str = "", done: str = "", next_steps: str = "", notes: str = "",
           blockers: str = "", target: str = "any", state: Optional[dict] = None,
           requests: Optional[dict] = None, now: Optional[datetime] = None) -> str:
    now = now or datetime.now().astimezone()
    state = state if state is not None else git_state(root)
    cmds = detect_commands(root)
    changed = [c["path"] for c in state.get("changed", [])]
    lines = [f"# Handoff — {root.name}", "",
             f"_Written {now.strftime('%Y-%m-%d %H:%M UTC%z')} for **{TARGETS.get(target, target)}**. "
             "Read this whole file before doing anything else._", ""]

    def section(title, body):
        if body and str(body).strip():
            lines.extend([f"## {title}", "", str(body).strip(), ""])

    section("Goal", goal or "_(not provided — ask the user before making large changes)_")
    section("Done so far", done)
    section("Next steps", next_steps)
    section("Blockers / open questions", blockers)
    section("Notes", notes)

    if state.get("is_repo"):
        repo = [f"- Branch: `{state['branch']}` @ `{state['head']}`"]
        if state.get("upstream"):
            behind, _, ahead = (state.get("ahead_behind") or "0\t0").partition("\t")
            repo.append(f"- Upstream: `{state['upstream']}` (ahead {ahead or 0}, behind {behind or 0})")
        repo.append(f"- Uncommitted changes: {len(changed)} file(s)")
        section("Repository state", "\n".join(repo))
        if changed:
            body = "\n".join(f"- `{c['status']}` {c['path']}" for c in state["changed"][:60])
            if len(changed) > 60:
                body += f"\n- … and {len(changed) - 60} more"
            if state.get("diffstat"):
                body += "\n\n```text\n" + "\n".join(state["diffstat"].splitlines()[-25:]) + "\n```"
            section("Changed files (uncommitted)", body)
        if state.get("log"):
            section("Recent commits", "```text\n" + state["log"] + "\n```")
    found_todos = todos(root, changed)
    if found_todos:
        section("TODO / FIXME in changed files", "\n".join(f"- {t}" for t in found_todos))
    if cmds:
        section("How to verify", "\n".join(f"- `{c}`" for c in cmds))
    if requests:
        body = []
        for src, texts in requests.items():
            body.append(f"**Last requests in {src}:**")
            body += [f"> {t.replace(chr(10), ' ')}" for t in texts]
            body.append("")
        section("What the user was asking (from session logs)", "\n".join(body))
    lines += ["## Rules for the next agent", "",
              "1. Don't redo finished work. Check the changed files and commits above first.",
              "2. Run the verify commands before and after your changes.",
              "3. Keep changes small and tell the user what you changed.",
              "4. When you stop, update this file (Done / Next steps) so the next handoff is easy.", ""]
    return "\n".join(lines)


PROMPTS = {
    "claude": "Read {path} first. It is a handoff from another AI session that hit its usage limit. "
              "Continue the work from 'Next steps', follow its rules, and update the file when you stop.",
    "codex": "Open and read {path} before anything else. It's a handoff from a previous agent. Continue from "
             "'Next steps', run the verify commands, and update the handoff file at the end.",
    "gemini": "Read the file {path} in this workspace. It's a handoff from another assistant. Execute the "
              "'Next steps', verify with the listed commands, and write your progress back into the same file.",
    "chatgpt": "Below is a handoff from another AI coding session that hit its usage limit. Read it, then tell "
               "me the next concrete step and help me do it.\n\n---\n{content}",
    "copilot": "#file:{path} is a handoff from another session. Continue from 'Next steps'.",
    "any": "Read {path} — a handoff from a previous AI session — and continue from 'Next steps'.",
}


def prompt_for(target: str, path: str, content: str = "") -> str:
    return PROMPTS.get(target, PROMPTS["any"]).format(path=path, content=content)


def slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^\w]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return s[:n].strip("-") or "handoff"
