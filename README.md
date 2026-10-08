# ccsync

Host your Claude Code configuration in this GitHub repository's encrypted
`config/` directory, then pull it onto other devices. Git is the transport;
devices do not need a direct SSH connection to the source computer.

Requires Python 3.10+, Git and git-crypt on macOS/Linux. Personal content remains
under the existing `config/** filter=git-crypt diff=git-crypt` rule. There is no
second configuration repository or hosted service.

## Workflow

```text
Source ~/.claude + referenced instruction files
  -> ccsync push -> encrypted config/ -> GitHub
  -> ccsync pull --profile <name> -> local ~/.claude
```

`push` captures a portable source snapshot. `pull` renders it for the destination
before comparing or writing any files. A source computer can be offline after
pushing; destinations fetch the already-published snapshot independently.

## Commands

Run from your checkout, or pass `--repo /path/to/checkout` before the command:

```bash
python3 ccsync.py status
python3 ccsync.py diff push
python3 ccsync.py push -y -m "sync: update configuration"
python3 ccsync.py diff pull --profile linux-host
python3 ccsync.py pull --profile linux-host -y
python3 ccsync.py pull --profile linux-host -y --install-plugins
```

- `push`: capture, back up replaced repo files, commit exact snapshot paths, push.
- `pull`: `git pull --ff-only`, render, back up, apply and record managed hashes.
- `diff [push|pull]`: preview actual rendered differences without applying them.
- `status [push|pull]`: filename-only change summary (defaults to pull on a
  previously configured destination, push otherwise). `diff` uses the same default.
- `pull --no-fetch`: apply the existing checkout without contacting the remote.
- `--allow-delete`: permit deletions of previously managed files after reviewing
  the diff. `-y` alone never authorizes deletion.
- `pull --overwrite-local`: back up and replace locally edited managed files.
  It does not permit deletion of locally edited files.
- `pull --install-plugins`: explicitly install missing enabled plugins. Failures
  return nonzero; the configuration remains applied and the next run retries
  missing installations. Plugin updates and language-server installation are
  not performed.

Without `-y`, configuration application requires confirmation. Pull fetches
before displaying the preview. Normal sync output lists filenames, not values.
`diff` prints content: use it only in a trusted terminal. Environment and plugin
configuration values in settings diffs are hidden.

## Snapshot contents

| Source | Snapshot / destination |
|---|---|
| `~/.claude/CLAUDE.md` | `CLAUDE.md` |
| Standalone `@file` Markdown imports inside `~/.claude` or `~/.codex` | Collected recursively, relative imports, flat filenames |
| `~/.claude/settings.json` | Settings, excluding `env` and `pluginConfigs` |
| `~/.claude/hooks/`, `skills/` | Files, including binary assets and executable bits |
| `~/.claude/statusline-command.sh` | Statusline script unless the profile preserves its own |

Snapshots include a versioned `snapshot.json` containing file hashes, modes,
source home/platform and destination profiles. Source instruction files outside
the allowed roots, missing imports, filename collisions and import cycles fail
closed. Only standalone `@path` import lines are relocated; remaining absolute
inline imports abort capture. Prose and skill instructions are not blindly rewritten.

Credentials, session history, caches, runtime plugin files, `settings.local.json`
and `settings.host.json` are not collected. Hidden files/directories,
`node_modules`, Python caches and credential-like filenames (`*.env`, `*.key`,
`*.pem`, `credentials*`) are excluded from hooks/skills. Known private-key and
token signatures also abort capture. This is defense in depth, not proof that
arbitrary text contains no secrets; review the snapshot before publishing.

`env` and `pluginConfigs` stay on each device: existing local values survive a
pull, and `~/.claude/settings.host.json` overrides the rendered settings using a
recursive dictionary merge. Arrays are replaced. API keys and git-crypt keys
must never be added to the repository.

## Destination profiles

Import profiles once from an existing `claude-config-sync` directory:

```bash
python3 ccsync.py push --profiles /path/to/claude-config-sync/hosts.json
```

The importer reads `hosts`, global `skip_skills` / `skip_plugins`, and sibling
`hosts/<name>.LOCAL.md` files. It stores profiles inside the encrypted snapshot;
it does not retain SSH addresses or fixed destination home paths. Subsequent
pushes preserve these profiles unless `--profiles` is supplied again.

Supported per-host fields are `name`, `codex_memory`, `sync_statusline`,
`web_search_section`, and `web_search_note`. Imported profiles target Linux.
For example:

```json
{
  "skip_skills": ["mac-only-tool"],
  "skip_plugins": ["swift-lsp@claude-plugins-official"],
  "hosts": [{"name": "linux-host", "sync_statusline": false}]
}
```

Provide `hosts/linux-host.LOCAL.md` with destination-specific instructions.
The first pull records the selected profile; later pulls and previews reuse it
unless explicitly supplied. Switching an already-managed profile is refused.
Cross-platform pulls require an explicit profile; unknown profiles fail.
Actual pulls reject a profile for a different OS. Pulling onto the original
source home/platform is refused, preserving its original Codex instruction
references; this workflow uses that home as the publisher, not a destination.
On Linux, settings commands referencing Mac-only paths and local marketplaces
are excluded; remaining source-home paths in settings are relocated to the
actual destination home. Profile-specific search and memory instruction
sections use the same headings as the prior sync tool.

This is not an arbitrary shell-script porting engine. Hook/script bodies and
skill prose are copied as files; audit their platform assumptions before enabling
them on another OS. A destination that has applied a named profile cannot push
its lossy rendered copy back over the source snapshot.

## Git and file safety

- Push requires git-crypt protection and checks staged bytes are ciphertext
  before committing. A locked checkout cannot be pulled as plaintext.
- Existing staged changes block push. Only exact generated paths are staged;
  unrelated source edits and untracked files are not included.
- A failed push is retried even if the source has not changed. A failed commit
  unstages this operation's files, leaving them available for the next push.
- Pull refuses a dirty `config/` before fetching. Diverged Git history is not
  force-pushed or automatically resolved.
- If fetching changes the sync program, pull stops and asks for a rerun, instead
  of applying the new snapshot with old code still loaded.
- A process lock prevents overlapping operations in one checkout.
- Only previously managed, unmodified files can be removed. Destination-only
  files survive. Local modifications to managed files stop the operation for
  reconciliation rather than silently overwriting them. To replace them after
  previewing, use `--overwrite-local`; replaced content is backed up.
- Source symlinks are materialized, with cycle detection. Destination symlinks
  are refused, including symlinked parent directories.
- All planned changes are backed up under `~/.local/state/ccsync/backups/`.
  `restore.json` identifies newly created files and original modes. Completed
  writes are rolled back if another file write fails. This is not a full
  crash-consistent filesystem transaction; keep backups until verified.

State lives in `~/.local/state/ccsync/state.json`. One destination Claude home
is managed by one checkout. Do not run the old SSH writer and ccsync pull against
the same home concurrently: both manage the same files.

## Existing repositories and migration

Legacy `config/CLAUDE.md` and `config/skills/` snapshots remain readable. Their
contents are not cross-platform transformed without a new snapshot. The first
new push adds a manifest and captures the expanded allowlist; unrelated legacy
files remain in Git but are not deployed by the manifest reader.

1. Update the program with plain `git pull` first, **not the old `ccsync pull`**.
2. Unlock the checkout with your existing git-crypt key (never store it here).
3. On the source, preview and push a new snapshot, importing profiles if needed.
4. On a destination, preview `diff pull --profile <name>` and inspect exclusions.
5. Back up and stop any previous writer before the first actual pull.
6. Verify the destination, then change your scheduler to the new command.

The tool does not install or modify schedulers. A six-hour schedule can invoke
`push -y` on the source and `pull -y --profile <name> --install-plugins` on each
destination. Device setup and encryption-key provisioning are separate steps.

## Development

```bash
python3 -m unittest -q
```

Tests use temporary homes, local bare Git remotes and real git-crypt encryption
(encryption integration tests skip when git-crypt is unavailable). They do not
contact GitHub or modify real Claude settings.

The optional Claude skill is in `skills/SKILL.md`. License: MIT.
