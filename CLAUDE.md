# Project guidance

ccsync synchronizes Claude Code configuration through the existing GitHub
repository's git-crypt-protected `config/` directory. Keep personal host names,
paths, profiles and content out of public code and documentation.

## Architecture

- `ccsync.py`: CLI, Git transport, encryption checks, locking, state and optional
  plugin installation. Commands: push, pull, diff, status; `--repo` selects a checkout.
- `portable.py`: allowlisted capture, recursive Markdown imports, versioned
  snapshot validation, per-host rendering, managed-file planning and backed-up
  application. No network calls.
- `config/snapshot.json`: encrypted source metadata, profiles, hashes and modes;
  existing `config/CLAUDE.md` and `config/skills/` paths remain valid.
- `~/.claude/settings.host.json`: local-only overrides. Never capture credentials,
  runtime state, env values or pluginConfigs; preserve local values on pull.
- `~/.local/state/ccsync/`: ownership hashes and backups. Named destination
  profiles cannot push rendered output back over source configuration.

## Development and verification

Python 3.10+ standard library; macOS/Linux. Run `python3 -m unittest -q`.
Git encryption integration tests require git-crypt and use local temporary repos.
Never run push/pull against real user configuration as a test. Do not change
existing schedulers or deploy devices unless explicitly requested.

Preserve unrelated Git changes. Only stage exact generated config paths inside
the CLI. Fail closed on missing encryption, invalid imports, unsafe symlinks,
corrupt manifests or local edits to managed files. Files removed by sync must
be previously managed and backed up. Never add plaintext personal data to Git.
