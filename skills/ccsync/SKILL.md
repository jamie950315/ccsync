---
name: ccsync
description: "Sync ~/.claude/CLAUDE.md and ~/.claude/skills/ between devices via git repo. Use when the user wants to push/pull/diff/status their Claude Code config."
argument-hint: <push|pull|diff|status> [options]
---

# ccsync - Claude Code Config Sync

Run the ccsync CLI to sync `~/.claude/CLAUDE.md` and `~/.claude/skills/` with the `config/` directory in the git repo at `~/ccsync`.

## Commands

- `push [-y] [-m "msg"]` — Local → repo → remote
- `pull [-y] [--no-fetch]` — Remote → repo → local
- `diff [push|pull]` — Preview changes without applying
- `status` — Show sync status overview

## Execution

Run the following command with the user's arguments:

```bash
cd ~/ccsync && python ccsync.py $ARGUMENTS
```

If no arguments are provided, run `status` by default.

If the command requires interactive confirmation (no `-y` flag), inform the user of the changes and ask them to confirm, then re-run with `-y`.

## Ignoring Files

A `.ccsyncignore` file in the repo root can exclude items from syncing using glob patterns (one per line, `#` for comments). Example: `skills/ccsearch/*` to skip the ccsearch skill.
