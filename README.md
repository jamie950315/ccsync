# ccsync

Sync your `~/.claude/CLAUDE.md` and `~/.claude/skills/` between devices using a git repo.

## Usage

```bash
python ccsync.py <command>
```

### Commands

| Command | Description |
|---------|-------------|
| `push` | Copy local `~/.claude` config into the repo, then commit & push |
| `pull` | Fetch latest from remote and apply repo config to local `~/.claude` |
| `diff [push\|pull]` | Preview changes without applying (default direction: `push`) |
| `status` | Show sync status overview |

### Options

```bash
push [-y, --yes] [-m, --message "msg"]   # -y skips prompts, -m sets commit message
pull [-y, --yes] [--no-fetch]            # --no-fetch skips git pull before syncing
```

## How It Works

1. Compares files between `~/.claude/` and the repo directory
2. Shows a unified diff for each changed file
3. Prompts for confirmation before applying each change (skip with `-y`)
4. On `push`, automatically stages, commits, and pushes to remote

## Requirements

Python 3.10+ (no external dependencies)
