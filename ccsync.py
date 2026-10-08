#!/usr/bin/env python3
"""Sync portable Claude configuration through an encrypted Git repository."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import difflib
import json
import platform
from pathlib import Path
import subprocess
import sys

import portable as p


def git(repo, *args, check=True):
    return subprocess.run(['git', '-C', str(repo), *args], check=check, capture_output=True)


def syncignore(repo):
    path = repo / '.ccsyncignore'
    return [s.strip() for s in path.read_text().splitlines() if s.strip() and not s.startswith('#')] if path.exists() else []


@contextmanager
def lock(repo):
    # flock is released by the OS even when a process crashes (macOS/Linux).
    import fcntl
    directory = Path(git(repo, 'rev-parse', '--absolute-git-dir').stdout.decode().strip())
    with (directory / 'ccsync.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another ccsync operation is running') from None
        yield


def encrypted(repo, names):
    for name in names:
        path = 'config/' + name
        attr = git(repo, 'check-attr', 'filter', '--', path).stdout.decode().strip()
        if not attr.endswith(': git-crypt'):
            raise ValueError(f'Missing git-crypt protection: {path}')
    clean = git(repo, 'config', '--get', 'filter.git-crypt.clean', check=False)
    if clean.returncode or not clean.stdout.strip():
        raise ValueError('git-crypt is not unlocked/configured in this checkout')


def publish(repo, names, message):
    """Only stage exact generated paths; always retry pending commits on push."""
    if git(repo, 'diff', '--cached', '--name-only').stdout.strip():
        raise ValueError('Existing staged changes; commit or unstage them before pushing config')
    if names:
        encrypted(repo, names)
        git(repo, 'add', '--', *['config/' + n for n in names])
        try:
            for name in names:
                blob = git(repo, 'show', ':config/' + name, check=False)
                if blob.returncode == 0 and not blob.stdout.startswith(b'\x00GITCRYPT\x00'):
                    raise ValueError(f'Encryption did not produce ciphertext: config/{name}')
        except BaseException:
            git(repo, 'reset', '-q', 'HEAD', '--', *['config/' + n for n in names])
            raise
        if git(repo, 'diff', '--cached', '--quiet', check=False).returncode:
            try:
                git(repo, 'commit', '-m', message)
            except BaseException:
                git(repo, 'reset', '-q', 'HEAD', '--', *['config/' + n for n in names])
                raise
    git(repo, 'push')


def preview(changes, show_diff=False):
    for name, before, after in changes:
        action = 'delete' if after is None else ('create' if before is None else 'update')
        print(f'{action}: {name}')
        # Default output never prints configuration values into unattended logs.
        if show_diff:
            if name == 'settings.json':
                def redact(data):
                    if data is None:
                        return None
                    value = json.loads(data)
                    for key in ('env', 'pluginConfigs'):
                        if key in value:
                            value[key] = '[host-local values hidden]'
                    return p.encoded(value)
                before, after = redact(before), redact(after)
            try:
                old = (before or b'').decode().splitlines(keepends=True)
                new = (after or b'').decode().splitlines(keepends=True)
            except UnicodeDecodeError:
                print('  Binary content changed')
            else:
                print(''.join(difflib.unified_diff(old, new, fromfile='a/' + name, tofile='b/' + name)), end='')
    print(f'{len(changes)} file change(s)')


def plugins(home):
    """Reconcile declared enabled plugins. Explicit opt-in; failure is nonzero."""
    c = home / '.claude'
    settings = json.loads((c / 'settings.json').read_text())
    installed = c / 'plugins/installed_plugins.json'
    have = set(json.loads(installed.read_text()).get('plugins', {})) if installed.exists() else set()
    known = c / 'plugins/known_marketplaces.json'
    markets = set(json.loads(known.read_text())) if known.exists() else set()
    for plugin, enabled in settings.get('enabledPlugins', {}).items():
        if not enabled or plugin in have:
            continue
        market = plugin.rsplit('@', 1)[-1]
        if market not in markets:
            source = settings.get('extraKnownMarketplaces', {}).get(market, {}).get('source', {})
            if source.get('source') != 'github' or not source.get('repo'):
                raise ValueError(f'Missing GitHub marketplace definition: {market}')
            subprocess.run(['claude', 'plugin', 'marketplace', 'add', source['repo']], check=True, capture_output=True)
            markets.add(market)
        subprocess.run(['claude', 'plugin', 'install', plugin], check=True, capture_output=True)


def run(args):
    repo = Path(args.repo).resolve() if args.repo else Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel']).decode().strip())
    home = Path.home()
    root = repo / 'config'
    state_root = home / '.local/state/ccsync'
    state_path = p.checked(state_root, 'state.json')
    local_state = json.loads(state_path.read_text()) if state_path.exists() else {}
    command = args.command
    if command != 'push' and getattr(args, 'profile', None) is None:
        args.profile = local_state.get('profile')
    direction = args.direction if command in ('diff', 'status') else command
    if direction is None:
        direction = 'pull' if local_state.get('profile') else 'push'
    with lock(repo):
        if command == 'pull' and not args.no_fetch:
            if git(repo, 'status', '--porcelain', '--', 'config').stdout.strip():
                raise ValueError('Dirty config/; refusing to fetch and apply')
            code = {n: (repo / n).read_bytes() for n in ('ccsync.py', 'portable.py') if (repo / n).exists()}
            git(repo, 'pull', '--ff-only')
            if any(not (repo / n).exists() or (repo / n).read_bytes() != b for n, b in code.items()):
                raise ValueError('Sync code updated; rerun the command to load the new version')
        if direction == 'push':
            existing = p.checked(root, p.MANIFEST)
            meta, _ = p.read_snapshot(root) if existing.exists() else ({}, {})
            if not existing.exists() and (root / 'CLAUDE.md').exists():
                p.read_snapshot(root)  # Reject locked legacy data before capture.
            if state_path.exists() and json.loads(state_path.read_text()).get('profile'):
                raise ValueError('A rendered destination cannot push the source snapshot')
            profile_path = getattr(args, 'profiles', None)
            profiles = p.load_profiles(Path(profile_path)) if profile_path else meta.get('profiles', {})
            files = p.capture(home, syncignore(repo), profiles)
            # Only remove files owned by the previous snapshot, never legacy or unrelated files.
            old = {n: info['sha256'] for n, info in meta.get('files', {}).items()}
            if existing.exists():
                old[p.MANIFEST] = p.digest(existing.read_bytes())
            modes = {n: 0o600 for n in files}
            changes = p.plan(root, files, old, modes)
        else:
            meta, source = p.read_snapshot(root)
            selected = getattr(args, 'profile', None)
            if command == 'pull' and meta.get('source_home') == str(home) and meta.get('source_platform') == platform.system():
                raise ValueError('Refusing pull onto the source home: keep its original instruction imports intact')
            selected_profile = meta.get('profiles', {}).get(selected, {})
            if command == 'pull' and selected_profile.get('platform', platform.system()) != platform.system():
                raise ValueError('Destination profile platform does not match this machine')
            files = p.render(meta, source, home, getattr(args, 'profile', None))
            files = {n: b for n, b in files.items() if not p.excluded(n, syncignore(repo))}
            state = json.loads(state_path.read_text()) if state_path.exists() else {}
            if state and state.get('repo') != str(repo):
                raise ValueError('This Claude home is managed by another ccsync checkout')
            if state.get('profile') is not None and state.get('profile') != selected:
                raise ValueError('Destination profile changed; reconcile the previous managed state first')
            profile = meta.get('profiles', {}).get(getattr(args, 'profile', None), {})
            protected = not profile.get('sync_statusline', True)
            old = {n: h for n, h in state.get('files', {}).items()
                   if not p.excluded(n, syncignore(repo)) and not (protected and n == 'statusline-command.sh')}
            modes = {n: info['mode'] for n, info in meta.get('files', {}).items()}
            if not meta:
                modes = {n: (0o700 if p.checked(root, n).stat().st_mode & 0o111 else 0o600) for n in files}
            changes = p.plan(home / '.claude', files, old, modes,
                             overwrite=command in ('diff', 'status') or getattr(args, 'overwrite_local', False))
        preview(changes, command == 'diff')
        if command in ('diff', 'status'):
            return
        if any(after is None for _, _, after in changes) and not getattr(args, 'allow_delete', False):
            raise ValueError('Managed deletions require --allow-delete after reviewing the diff')
        if not args.yes and input(f'Apply {command} and contact Git remote? [y/N] ').lower() != 'y':
            return
        if command == 'push':
            if git(repo, 'diff', '--cached', '--name-only').stdout.strip():
                raise ValueError('Existing staged changes; refusing to modify the snapshot')
            encrypted(repo, files)
            backup = p.apply(root, changes, modes, state_root / 'backups')
            names = {n for n, _, _ in changes}
            # Recover failures between writing the snapshot and committing it.
            for n in files:
                tracked = git(repo, 'ls-files', '--error-unmatch', '--', 'config/' + n, check=False)
                dirty = git(repo, 'diff', '--quiet', 'HEAD', '--', 'config/' + n, check=False)
                if tracked.returncode or dirty.returncode:
                    names.add(n)
            publish(repo, sorted(names), args.message or 'sync: update claude config')
        else:
            backup = p.apply(home / '.claude', changes, modes, state_root / 'backups')
            p.atomic(state_path, p.encoded(dict(repo=str(repo), profile=args.profile,
                     revision=git(repo, 'rev-parse', 'HEAD').stdout.decode().strip(),
                     files={n: p.digest(b) for n, b in files.items()})))
            if args.install_plugins:
                plugins(home)
        if backup:
            print(f'Backup: {backup}')
        print('Sync completed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', help='Repository checkout (default: current Git root)')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('push', 'pull', 'diff', 'status'):
        cmd = sub.add_parser(name)
        if name in ('push', 'pull'):
            cmd.add_argument('-y', '--yes', action='store_true')
            cmd.add_argument('--allow-delete', action='store_true', help='Allow reviewed, backed-up managed deletions')
        if name == 'push':
            cmd.add_argument('-m', '--message')
            cmd.add_argument('--profiles', help='Import existing sync hosts.json and sibling hosts/*.LOCAL.md')
        else:
            cmd.add_argument('--profile', help='Named destination profile from the encrypted snapshot')
        if name == 'pull':
            cmd.add_argument('--no-fetch', action='store_true')
            cmd.add_argument('--overwrite-local', action='store_true', help='Back up and replace locally edited managed files; never delete edited files')
            cmd.add_argument('--install-plugins', action='store_true', help='Install missing enabled plugins after applying')
        if name in ('diff', 'status'):
            cmd.add_argument('direction', nargs='?', choices=['push', 'pull'])
    try:
        run(parser.parse_args())
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # Do not echo subprocess output: plugins and Git filters can contain secrets.
        if isinstance(exc, subprocess.CalledProcessError):
            print(f'Operation failed: {exc.cmd[0]} exited {exc.returncode}; sync incomplete', file=sys.stderr)
        else:
            print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
