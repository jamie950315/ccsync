# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ccsync** is a single-file Python CLI tool that synchronizes `~/.claude/CLAUDE.md` and `~/.claude/skills/` between devices using a git repo as the transport layer. It compares files bidirectionally (local ↔ repo), shows unified diffs, and applies changes interactively.

## Running

```bash
# Run directly
python ccsync.py push|pull|diff|status

# Commands
python ccsync.py push [-y] [-m "msg"]   # Local → repo, then git commit & push
python ccsync.py pull [-y] [--no-fetch]  # Repo → local ~/.claude
python ccsync.py diff [push|pull]        # Preview changes without applying
python ccsync.py status                  # Show sync status overview
```

No dependencies beyond the Python standard library. No build step, no tests, no package config.

## Architecture

Single module (`ccsync.py`, ~300 lines). Key flow:

- `SYNC_DIR = "config"` — synced files are stored under `config/` in the repo (not the repo root) to avoid conflicts with the project's own `CLAUDE.md`
- `SYNC_TARGETS` dict defines what to sync: `CLAUDE.md` (file) and `skills/` (directory)
- `build_changes(src, dst)` compares source → destination, returns list of change dicts with unified diffs
- `apply_changes()` iterates changes, shows diffs with ANSI colors, prompts for confirmation (unless `-y`)
- `git_operations()` stages, commits, and pushes after a `push` command
- `collect_files()` recursively walks directories, filtering via `IGNORE_PATTERNS`
