# ccsync

Sync your `~/.claude/CLAUDE.md` and `~/.claude/skills/` between devices using a git repo.

## What It Syncs

ccsync tracks two items from `~/.claude/` and stores them in the `config/` directory of the repo:

| Local Path | Repo Path | Description |
|------------|-----------|-------------|
| `~/.claude/CLAUDE.md` | `config/CLAUDE.md` | Your global Claude Code instructions |
| `~/.claude/skills/` | `config/skills/` | Custom slash-command skills (e.g. `/ccsearch`) |

The `config/` directory is encrypted with [git-crypt](https://github.com/AGWA/git-crypt), so your personal config stays private even in a public repo. Others who fork will see encrypted content and can simply replace it with their own.

## Quick Start

### 1. [Fork this repo](https://github.com/jamie950315/ccsync/fork) on GitHub

```bash
# 2. Clone your fork and clear the encrypted config
git clone https://github.com/<your-username>/ccsync.git
cd ccsync
rm -rf config/*

# 3. (Optional) Set up git-crypt to encrypt your own config
brew install git-crypt   # or apt-get install git-crypt
git-crypt init

# 4. Push your own local config
python ccsync.py push

# 5. On another device, clone your fork and pull the config down
git clone https://github.com/<your-username>/ccsync.git
cd ccsync
git-crypt unlock /path/to/your.key   # if using git-crypt
python ccsync.py pull
```

## Commands

### `push` — Local → Repo → Remote

Copies your local `~/.claude` config into the repo's `config/` directory, then commits and pushes to remote.

```bash
python ccsync.py push                    # Interactive mode (confirm each file)
python ccsync.py push -y                 # Auto-accept all changes
python ccsync.py push -m "add new skill" # Custom commit message (default: "sync: update claude config")
python ccsync.py push -y -m "update"     # Auto-accept with custom message
```

Example output:

```
Comparing local (~/.claude) → repo (/Users/you/ccsync/config)

Found 2 change(s):

============================================================
  UPDATE: CLAUDE.md
============================================================
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -1,3 +1,5 @@
+@RTK.md
+
 ### AI Assistant Guidelines
...

Apply update to /Users/you/ccsync/config/CLAUDE.md? [y/N] y
  ✓ update: CLAUDE.md

============================================================
  CREATE: skills/ccsearch/SKILL.md
============================================================
--- a/skills/ccsearch/SKILL.md
+++ b/skills/ccsearch/SKILL.md
@@ -0,0 +1,10 @@
+---
+name: ccsearch
+...

Apply create to /Users/you/ccsync/config/skills/ccsearch/SKILL.md? [y/N] y
  ✓ create: skills/ccsearch/SKILL.md

Pushing to remote...
✓ Pushed successfully.
```

### `pull` — Remote → Repo → Local

Fetches from remote, then applies repo config to your local `~/.claude`.

```bash
python ccsync.py pull                    # Fetch + interactive apply
python ccsync.py pull -y                 # Fetch + auto-accept all
python ccsync.py pull --no-fetch         # Skip git pull, just apply from local repo
python ccsync.py pull -y --no-fetch      # Skip fetch + auto-accept
```

Example output:

```
Fetching latest from remote...
Already up to date.
Comparing repo (/Users/you/ccsync/config) → local (~/.claude)

Found 1 change(s):

============================================================
  UPDATE: CLAUDE.md
============================================================
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -5,3 +5,5 @@
 ### AI Assistant Guidelines
+
+**Web Search:** Always use `/ccsearch` for web searches.

Apply update to /Users/you/.claude/CLAUDE.md? [y/N] y
  ✓ update: CLAUDE.md

✓ Applied 1 change(s) to ~/.claude
```

### `diff` — Preview Changes

Shows what would change without applying anything. Useful for reviewing before a push or pull.

```bash
python ccsync.py diff                    # Preview push direction (default)
python ccsync.py diff push               # Same as above
python ccsync.py diff pull               # Preview pull direction
```

Example output:

```
Diff: local (~/.claude) → repo (/Users/you/ccsync/config)

--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ -1,3 +1,5 @@
+@RTK.md
+
 ### AI Assistant Guidelines

--- a/skills/ccsearch/SKILL.md
+++ b/skills/ccsearch/SKILL.md
@@ -0,0 +1,5 @@
+---
+name: ccsearch
+description: "Web search using ccsearch CLI."
+---
```

### `status` — Sync Overview

Shows whether each tracked item exists locally and in the repo, and whether they differ.

```bash
python ccsync.py status
```

Example output:

```
Repo: /Users/you/ccsync/config
Local: /Users/you/.claude

  CLAUDE.md:
    local: ✓ /Users/you/.claude/CLAUDE.md
    repo:  ✓ /Users/you/ccsync/config/CLAUDE.md
    status: differs

  skills:
    local: ✓ /Users/you/.claude/skills
    repo:  ✓ /Users/you/ccsync/config/skills
    status: 1 local only, 2 differ
```

## Typical Workflows

### Setting up a new device

```bash
git clone https://github.com/<your-username>/ccsync.git
cd ccsync
git-crypt unlock /path/to/your.key   # if using git-crypt
python ccsync.py pull -y
```

### Daily sync across devices

```bash
# On device A: push changes
cd ~/ccsync
python ccsync.py push -y

# On device B: pull changes
cd ~/ccsync
python ccsync.py pull -y
```

### Reviewing before syncing

```bash
# Check what's different
python ccsync.py status

# See the exact diff
python ccsync.py diff push

# If it looks good, push
python ccsync.py push
```

## Ignoring Files

Create a `.ccsyncignore` file in the repo root to exclude items from syncing. Uses glob patterns, one per line:

```
# Don't sync the ccsearch skill
skills/ccsearch/*

# Don't sync CLAUDE.md
CLAUDE.md
```

## Requirements

- Python 3.10+
- [git-crypt](https://github.com/AGWA/git-crypt) (optional, for encrypting `config/`)
