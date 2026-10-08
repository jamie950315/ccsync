---
name: ccsync
description: "Sync portable Claude Code configuration through an encrypted GitHub repository. Use for push/pull/diff/status of instructions, settings, hooks and skills."
argument-hint: <push|pull|diff|status> [options]
---

# ccsync - Claude Code Config Sync

Run the ccsync CLI from its checkout. Personal configuration is stored in the
git-crypt-encrypted `config/` directory. Read README.md for setup and profiles.
Never invoke the old version's pull to upgrade the program; use plain Git first.

## Commands

- `push [-y] [-m "msg"]` — Local → repo → remote
- `pull [-y] [--no-fetch]` — Remote → repo → local
- `diff [push|pull]` — Preview changes without applying
- `status` — Show sync status overview

For a destination, use `diff pull --profile <name>` before
`pull --profile <name>`. Unknown profiles or locked checkouts must be fixed,
not bypassed. `--install-plugins` explicitly installs missing enabled plugins.
Use `push --profiles /path/to/hosts.json` to import existing host profiles.
Never publish credentials or git-crypt keys, and never run two sync writers
against the same Claude home.

## Execution

Run the following command with the user's arguments:

```bash
python3 ccsync.py <command> [options]
```

If no arguments are provided, run `status` by default. Resolve and validate user
arguments; do not interpolate arbitrary text into a shell command.

If the command requires interactive confirmation (no `-y` flag), inform the user of the changes and ask them to confirm, then re-run with `-y`.

## Ignoring Files

A `.ccsyncignore` file in the repo root can exclude items from syncing using glob patterns (one per line, `#` for comments). Example: `skills/ccsearch/*` to skip the ccsearch skill.
