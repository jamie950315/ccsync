"""Portable Claude configuration snapshots; no network access or implicit installs."""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import re
import tempfile
from pathlib import Path

MANIFEST = 'snapshot.json'
IGNORED = {'.git', '__pycache__', 'node_modules', '.DS_Store'}
PRIVATE_NAMES = ('*.env', '.env*', '*.pem', '*.key', 'credentials*', '.credentials*')
SECRET = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-(?:or-v1-|ant-)[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}')
IMPORT = re.compile(r'^@([^\s]+)[ \t]*$', re.M)


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode()


def safe_name(name):
    p = Path(name)
    if not name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError(f'Unsafe relative path: {name}')
    return p


def checked(root, name):
    p = root / safe_name(name)
    # Do not follow existing destination symlinks, including ancestor directories.
    for part in (p, *p.parents):
        if part.is_symlink():
            raise ValueError(f'Refusing symlink destination: {p}')
        if part == root:
            break
    return p


def digest(data):
    return hashlib.sha256(data).hexdigest()


def excluded(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def walk(root, parents=frozenset()):
    real = root.resolve()
    if real in parents:
        raise ValueError(f'Symlink cycle: {root}')
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if (p.name not in IGNORED and not p.name.startswith('.') and not p.name.endswith('.pyc')
                    and not excluded(p.name, PRIVATE_NAMES)):
                yield from walk(p, parents | {real})
    elif root.is_file():
        yield root
    else:
        raise ValueError(f'Broken link or unsupported file: {root}')


def load_profiles(path):
    """Import the existing SSH sync host file, without storing SSH endpoints."""
    if path is None:
        return {}
    raw = json.loads(path.read_text())
    profiles = {}
    for host in raw.get('hosts', []):
        name = host['name']
        safe_name(name)
        profile = {k: host[k] for k in ('codex_memory', 'sync_statusline',
                    'web_search_section', 'web_search_note') if k in host}
        profile.setdefault('codex_memory', False)
        profile.update(platform='Linux', skip_skills=raw.get('skip_skills', []),
                       skip_plugins=raw.get('skip_plugins', []))
        notes = path.parent / 'hosts' / f'{name}.LOCAL.md'
        if notes.exists():
            profile['local_md'] = re.sub(
                r'are pushed from the Mac by `[^`]+/sync\.py` there',
                'are rendered from the GitHub-hosted ccsync snapshot', notes.read_text())
        profiles[name] = profile
    return profiles


def capture(home, patterns=(), profiles=None):
    """Read an explicit allowlist; never capture credentials or session stores."""
    c = home / '.claude'
    files, modes, sources, visiting = {}, {}, {}, set()

    def add(path, name):
        safe_name(name)
        if excluded(name, patterns):
            return
        data = path.read_bytes()
        if SECRET.search(data):
            raise ValueError(f'Possible secret in {name}; keep it host-local')
        files[name] = data
        modes[name] = 0o700 if path.stat().st_mode & 0o111 else 0o600

    def instruction(path, name):
        real = path.resolve(strict=True)
        if real in visiting:
            raise ValueError(f'Circular instruction import: {name}')
        if name in sources:
            if sources[name] != real:
                raise ValueError(f'Instruction filename collision: {name}')
            return
        sources[name] = real
        visiting.add(real)
        add(real, name)
        if name not in files:
            raise ValueError(f'Required instruction excluded: {name}')
        text = files[name].decode()
        def relocate(match):
            value = match[1]
            target = (home / value[2:]) if value.startswith('~/') else Path(value)
            if not target.is_absolute():
                target = path.parent / target
            resolved = target.resolve(strict=True)
            if not any(resolved.is_relative_to((home / d).resolve()) for d in ('.claude', '.codex')):
                raise ValueError(f'Instruction import outside config roots: {name}')
            if resolved.suffix != '.md':
                raise ValueError(f'Non-Markdown instruction import: {name}')
            instruction(resolved, resolved.name)
            return '@' + resolved.name
        files[name] = IMPORT.sub(relocate, text).encode()
        if re.search(rb'@(?:/|~/)', files[name]):
            raise ValueError(f'Unsupported inline absolute import: {name}; use a standalone import line')
        visiting.remove(real)

    if not (c / 'CLAUDE.md').is_file():
        raise ValueError('Missing ~/.claude/CLAUDE.md; refusing an empty snapshot')
    instruction(c / 'CLAUDE.md', 'CLAUDE.md')
    settings = c / 'settings.json'
    if settings.exists() and not excluded('settings.json', patterns):
        data = json.loads(settings.read_text())
        # These fields commonly contain credentials. They belong in settings.host.json.
        data.pop('env', None)
        data.pop('pluginConfigs', None)
        files['settings.json'] = encoded(data)
        modes['settings.json'] = 0o600
    for name in ('hooks', 'skills'):
        root = c / name
        if root.exists():
            for p in walk(root):
                add(p, p.relative_to(c).as_posix())
    if (c / 'statusline-command.sh').exists():
        add(c / 'statusline-command.sh', 'statusline-command.sh')
    meta = dict(version=1, source_home=str(home), source_platform=platform.system(),
                files={n: {'sha256': digest(b), 'mode': modes[n]} for n, b in files.items()},
                profiles=profiles or {})
    for name, data in {**files, MANIFEST: encoded(meta)}.items():
        if SECRET.search(data):
            raise ValueError(f'Possible secret in {name}; refusing snapshot')
    return {**files, MANIFEST: encoded(meta)}


def read_snapshot(root):
    manifest = checked(root, MANIFEST)
    if not manifest.exists():
        # Read legacy repositories without claiming ownership of local-only files.
        files = {}
        for name in ('CLAUDE.md', 'skills'):
            p = checked(root, name)
            if p.exists():
                for f in walk(p):
                    rel = f.relative_to(root).as_posix()
                    checked(root, rel)
                    files[rel] = f.read_bytes()
        if not files:
            raise ValueError('No configuration snapshot found')
        if any(v.startswith(b'\x00GITCRYPT\x00') for v in files.values()):
            raise ValueError('Unlock this repository with git-crypt before pulling')
        return {}, files
    raw = manifest.read_bytes()
    if raw.startswith(b'\x00GITCRYPT\x00'):
        raise ValueError('Unlock this repository with git-crypt before pulling')
    meta = json.loads(raw)
    if meta.get('version') != 1:
        raise ValueError('Unsupported snapshot version')
    files = {}
    for name, info in meta['files'].items():
        allowed = (name in ('settings.json', 'statusline-command.sh')
                   or ('/' not in name and name.endswith('.md'))
                   or name.startswith(('skills/', 'hooks/')))
        if not allowed or name.startswith('.'):
            raise ValueError(f'Protected snapshot path: {name}')
        data = checked(root, name).read_bytes()
        if digest(data) != info['sha256']:
            raise ValueError(f'Snapshot checksum mismatch: {name}')
        if info['mode'] not in (0o600, 0o700):
            raise ValueError(f'Invalid mode: {name}')
        files[name] = data
    return meta, files


def merge(base, override):
    out = dict(base)
    for k, value in override.items():
        out[k] = merge(out[k], value) if isinstance(value, dict) and isinstance(out.get(k), dict) else value
    return out


def render(meta, files, home, profile_name=None):
    profiles = meta.get('profiles', {})
    if profile_name and profile_name not in profiles:
        raise ValueError(f'Unknown profile: {profile_name}')
    profile = profiles.get(profile_name, {})
    system = profile.get('platform', platform.system())
    source_home = meta.get('source_home', str(home))
    cross = system != meta.get('source_platform', system)
    if cross and not profile_name:
        raise ValueError('Cross-platform pull requires an explicit --profile')
    out = dict(files)
    for name in list(out):
        if any(name.startswith(f'skills/{s}/') for s in profile.get('skip_skills', [])):
            del out[name]
    if not profile.get('sync_statusline', True):
        out.pop('statusline-command.sh', None)
    if 'local_md' in profile:
        out['LOCAL.md'] = profile['local_md'].encode()
    elif cross and 'LOCAL.md' in out:
        raise ValueError('Cross-platform pull needs a profile with local_md')
    if 'CLAUDE.md' in out:
        text = out['CLAUDE.md'].decode()
        if profile.get('codex_memory') is False:
            text = re.sub(r'^## Codex memory\n.*?(?=^## |\Z)', '', text, flags=re.M | re.S)
        web = profile.get('web_search_section')
        if web:
            text, count = re.subn(r'^## Web search in Claude Code\n.*?(?=^## |\Z)',
                                  lambda _: web.rstrip() + '\n\n', text, flags=re.M | re.S)
            if count != 1:
                raise ValueError('Expected Web search in Claude Code section')
        elif profile.get('web_search_note'):
            text, count = re.subn(r'(^## Web search in Claude Code\n)',
                                 lambda m: m[0] + '\n' + profile['web_search_note'] + '\n', text, flags=re.M)
            if count != 1:
                raise ValueError('Expected Web search in Claude Code section')
        out['CLAUDE.md'] = text.encode()
    if 'settings.json' in out:
        s = json.loads(out['settings.json'])
        if cross:
            def portable(command):
                rest = command.replace(source_home + '/.claude/', '')
                return source_home + '/' not in rest and '/Applications/' not in rest
            hooks = {}
            for event, groups in s.get('hooks', {}).items():
                kept = []
                for group in groups:
                    hs = [h for h in group.get('hooks', []) if portable(h.get('command', ''))]
                    if hs:
                        kept.append({**group, 'hooks': hs})
                if kept:
                    hooks[event] = kept
            s['hooks'] = hooks
            if not portable(s.get('statusLine', {}).get('command', '')):
                s.pop('statusLine', None)
            markets = {k: v for k, v in s.get('extraKnownMarketplaces', {}).items()
                       if v.get('source', {}).get('source') == 'github'}
            s['extraKnownMarketplaces'] = markets
            s['enabledPlugins'] = {k: v for k, v in s.get('enabledPlugins', {}).items()
                                   if k.split('@')[-1] in markets}
        s['enabledPlugins'] = {k: v for k, v in s.get('enabledPlugins', {}).items()
                               if k not in profile.get('skip_plugins', [])}
        if not profile.get('sync_statusline', True):
            s.pop('statusLine', None)
        text = json.dumps(s)
        if cross:
            text = text.replace(source_home + '/.claude/', str(home / '.claude') + '/')
            if source_home + '/' in text or '/Applications/' in text:
                raise ValueError('Unresolved source path in settings')
        else:
            text = text.replace(source_home + '/', str(home) + '/')
        s = json.loads(text)
        # Values excluded from export remain local, including on the source Mac.
        current = checked(home / '.claude', 'settings.json')
        if current.exists():
            previous = json.loads(current.read_text())
            for key in ('env', 'pluginConfigs'):
                if key in previous:
                    s[key] = previous[key]
        local = checked(home / '.claude', 'settings.host.json')
        if local.exists():
            s = merge(s, json.loads(local.read_text()))
        out['settings.json'] = encoded(s)
    if meta:
        validate_imports(out)
    return out


def validate_imports(files):
    visited, visiting = set(), set()
    def visit(name):
        if name in visiting:
            raise ValueError(f'Circular instruction import: {name}')
        if name in visited:
            return
        if name not in files:
            raise ValueError(f'Missing instruction import: {name}')
        visiting.add(name)
        for value in IMPORT.findall(files[name].decode()):
            safe_name(value)
            visit(value)
        visiting.remove(name)
        visited.add(name)
    visit('CLAUDE.md')


def plan(root, files, old, modes=None, overwrite=False):
    changes = []
    for name in sorted(set(files) | set(old)):
        dest = checked(root, name)
        if dest.exists() and not dest.is_file():
            raise ValueError(f'Not a regular file: {dest}')
        current = dest.read_bytes() if dest.exists() else None
        new = files.get(name)
        mode_changed = (new is not None and dest.exists() and modes and name in modes
                        and (dest.stat().st_mode & 0o777) != modes[name])
        if current == new and not mode_changed:
            continue
        if name in old and current is not None and digest(current) != old[name] and not (overwrite and new is not None):
            raise ValueError(f'Locally modified managed file: {name}; reconcile before syncing')
        changes.append((name, current, new))
    return changes


def atomic(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.ccsync-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def apply(root, changes, modes, backup_root):
    """Back up first; roll back completed writes if any write fails."""
    if not changes:
        return None
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = Path(tempfile.mkdtemp(prefix='sync-', dir=backup_root))
    previous_modes = {}
    for name, before, _ in changes:
        if before is not None:
            previous_modes[name] = checked(root, name).stat().st_mode & 0o777
            atomic(backup / name, before)
    atomic(backup / 'restore.json', encoded({'created': [n for n, b, _ in changes if b is None],
                                            'modes': previous_modes}))
    done = []
    try:
        for name, before, after in changes:
            dest = checked(root, name)
            if (dest.read_bytes() if dest.exists() else None) != before:
                raise ValueError(f'File changed after planning: {name}')
            if after is None:
                dest.unlink()
            else:
                atomic(dest, after, modes.get(name, 0o600))
            done.append((name, before))
    except BaseException:
        for name, before in reversed(done):
            dest = checked(root, name)
            if before is None:
                dest.unlink(missing_ok=True)
            else:
                atomic(dest, before, previous_modes[name])
        raise
    return backup
