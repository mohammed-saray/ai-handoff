# ai-handoff 🤝

**Out of Claude messages halfway through a task? Write one handoff file and continue in Codex, Gemini, ChatGPT or Copilot without re-explaining anything.**

[![CI](https://github.com/mohammed-saray/ai-handoff/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammed-saray/ai-handoff/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

```text
$ ai-handoff --goal "Add OAuth login" --next "wire the callback route, then add tests" --to codex --copy
✓ handoff written: docs/handoffs/2026-11-14-1844-add-oauth-login.md  (~640 tokens)

Paste this into Codex CLI:

Open and read docs/handoffs/2026-11-14-1844-add-oauth-login.md before anything else. It's a handoff
from a previous agent. Continue from 'Next steps', run the verify commands, and update the handoff file at the end.

(copied to clipboard)
```

## The problem

Every subscription runs out at some point: Claude's 5-hour window, Codex's weekly
limit, Gemini's daily quota. When it happens mid-task, the next assistant starts
from zero. You re-explain the goal, it re-reads the repo, it redoes finished
work, and it burns the quota you just switched to.

Compaction summaries stay inside one tool. A plain Markdown handoff works with
**any** model. `ai-handoff` builds that file for you in a second.

## What goes into the handoff

| Section | Where it comes from |
|---|---|
| Goal / Done / Next steps / Blockers / Notes | your flags (text, a file path, or `-` for stdin) |
| Repository state | branch, HEAD, ahead/behind upstream |
| Changed files + diffstat | `git status` / `git diff HEAD --stat` |
| Recent commits | `git log` |
| TODO / FIXME | scanned in the changed files only |
| How to verify | detected from `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Makefile` |
| What the user was asking | the last requests from your **Claude Code** and **Codex CLI** sessions for this folder (read locally; turn off with `--no-logs`) |
| Rules for the next agent | short rules so it doesn't redo work and updates the file when it stops |

## Install

```bash
pipx install git+https://github.com/mohammed-saray/ai-handoff
```

## Usage

```bash
ai-handoff --goal "Migrate to Postgres"               # write docs/handoffs/<date>-migrate-to-postgres.md
ai-handoff -g task.md -n next.md --to gemini          # read sections from files, prompt tailored for Gemini
ai-handoff --notes - < notes.txt                      # notes from stdin
ai-handoff --stdout                                   # print instead of writing
ai-handoff --to chatgpt --copy                        # copy a prompt with the whole file inlined (for web chats)
ai-handoff prompt docs/handoffs/x.md --to claude      # re-print the paste prompt later
ai-handoff list                                       # newest handoffs first
```

Targets: `claude`, `codex`, `gemini`, `chatgpt`, `copilot`, `any`.

### Tip: let the agent write its own handoff

Add this line to your `CLAUDE.md` / `AGENTS.md`:

```markdown
When I say "handoff", run `ai-handoff --goal "<task>" --done "<what you did>" --next "<what's left>"`.
```

## Privacy

Everything runs locally. Session logs are read only to pull out your last few
requests for **this folder**, and the result goes only into the file you write.
Check the file before you share it.

## Limitations

- Prompts from session logs are cut to 600 characters each.
- Gemini CLI logs aren't read yet (contributions welcome).

## Roadmap

- [ ] `ai-handoff resume` to show the newest handoff and its next steps
- [ ] Gemini CLI and Cursor session import
- [ ] Optional short AI summary of the diff (bring your own model)

## Related tools in this suite

Small, dependency-free tools for people fighting AI usage limits:

| Tool | What it does |
|---|---|
| [burnrate](https://github.com/mohammed-saray/burnrate) | Forecast Claude Code / Codex limits from local logs |
| [context-diet](https://github.com/mohammed-saray/context-diet) | Find the CLAUDE.md / AGENTS.md / GEMINI.md bloat you pay for on every message |
| **ai-handoff** | Hit a limit? Move the task to another AI with a handoff file |
| [ai-error-decoder](https://github.com/mohammed-saray/ai-error-decoder) | Explain 429 / 529 / quota errors from Anthropic, OpenAI and Gemini |
| [ratelimit-retry](https://github.com/mohammed-saray/ratelimit-retry) | Retry that respects provider rate-limit headers (JS) |
| [chat-export-md](https://github.com/mohammed-saray/chat-export-md) | ChatGPT / Claude / Gemini exports → Markdown |
| [mcp-token-audit](https://github.com/mohammed-saray/mcp-token-audit) | Measure how many tokens each MCP server's tools cost |
| [logslim](https://github.com/mohammed-saray/logslim) | Shrink logs and stack traces before pasting them into a chat |
| [chunkwise](https://github.com/mohammed-saray/chunkwise) | Split big files into token-budgeted chunks with continuation prompts |
| [ai-reset-clock](https://github.com/mohammed-saray/ai-reset-clock) | When does my quota reset? A countdown in your timezone |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
