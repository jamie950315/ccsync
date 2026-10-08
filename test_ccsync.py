"""Safety and Git transport tests; all writes stay in temporary directories."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ccsync
import portable as p


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.c = self.home / '.claude'
        self.c.mkdir(parents=True)
        (self.c / 'CLAUDE.md').write_text('Hello\n')

    def test_import_graph_and_binary_symlink_skill(self):
        codex = self.home / '.codex'
        codex.mkdir()
        (codex / 'AGENTS.md').write_text('@RTK.md\n')
        (codex / 'RTK.md').write_text('Use rtk\n')
        (self.c / 'CLAUDE.md').write_text('@' + str(codex / 'AGENTS.md') + '\n')
        asset = self.root / 'skill'
        asset.mkdir()
        (asset / 'asset.bin').write_bytes(b'\x00\xff')
        (self.c / 'skills').mkdir()
        (self.c / 'skills/test').symlink_to(asset, target_is_directory=True)
        files = p.capture(self.home)
        self.assertEqual(files['CLAUDE.md'], b'@AGENTS.md\n')
        self.assertEqual(files['skills/test/asset.bin'], b'\x00\xff')
        self.assertIn('RTK.md', files)

    def test_circular_import_rejected(self):
        (self.c / 'CLAUDE.md').write_text('@AGENTS.md\n')
        (self.c / 'AGENTS.md').write_text('@CLAUDE.md\n')
        with self.assertRaisesRegex(ValueError, 'Circular'):
            p.capture(self.home)

    def test_external_import_rejected(self):
        outside = self.root / 'outside.md'
        outside.write_text('private')
        (self.c / 'CLAUDE.md').write_text('@' + str(outside) + '\n')
        with self.assertRaisesRegex(ValueError, 'outside config'):
            p.capture(self.home)

    def test_inline_absolute_import_rejected(self):
        (self.c / 'CLAUDE.md').write_text('See @~/.codex/AGENTS.md for rules.\n')
        with self.assertRaisesRegex(ValueError, 'inline absolute import'):
            p.capture(self.home)

    def test_cycle_rejected(self):
        skills = self.c / 'skills'
        skills.mkdir()
        (skills / 'loop').symlink_to(skills, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'cycle'):
            p.capture(self.home)

    def test_hidden_and_credential_files_excluded(self):
        for name in ('skills/.trash/secret', 'skills/test/api.env', 'skills/test/.env', 'hooks/token.key'):
            target = self.c / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('do not export')
        files = p.capture(self.home)
        self.assertEqual(set(files), {'CLAUDE.md', p.MANIFEST})

    def test_import_blank_lines_preserved(self):
        (self.c / 'CLAUDE.md').write_text('@RTK.md\n\n# Instructions\n')
        (self.c / 'RTK.md').write_text('rtk')
        self.assertEqual(p.capture(self.home)['CLAUDE.md'], b'@RTK.md\n\n# Instructions\n')

    def test_import_old_profiles_removes_transport_identity(self):
        hostfile = self.root / 'hosts.json'
        hostfile.write_text(json.dumps({'hosts': [{'name': 'server', 'ssh': 'user@private', 'home': '/home/old'}]}))
        notes = self.root / 'hosts/server.LOCAL.md'
        notes.parent.mkdir()
        notes.write_text('Files are pushed from the Mac by `some/path/sync.py` there; edits are overwritten.')
        profile = p.load_profiles(hostfile)['server']
        self.assertNotIn('ssh', profile)
        self.assertNotIn('home', profile)
        self.assertFalse(profile['codex_memory'])
        self.assertIn('GitHub-hosted ccsync', profile['local_md'])

    def test_unresolved_settings_path_rejected(self):
        meta = {'source_home': '/Users/source', 'source_platform': 'Darwin',
                'profiles': {'linux': {'platform': 'Linux'}}}
        files = {'CLAUDE.md': b'Hello', 'settings.json': p.encoded({'permissions': {'additionalDirectories': ['/Users/source/project']}})}
        with self.assertRaisesRegex(ValueError, 'source path'):
            p.render(meta, files, self.home, 'linux')

    def test_locked_legacy_snapshot_rejected(self):
        (self.c / 'CLAUDE.md').write_bytes(b'\x00GITCRYPT\x00ciphertext')
        with self.assertRaisesRegex(ValueError, 'Unlock'):
            p.read_snapshot(self.c)

    def test_snapshot_checksum_and_path_checks(self):
        files = p.capture(self.home)
        for name, data in files.items():
            (self.c / name).write_bytes(data)
        p.read_snapshot(self.c)
        (self.c / 'CLAUDE.md').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            p.read_snapshot(self.c)
        with self.assertRaises(ValueError):
            p.checked(self.c, '../outside')

    def test_linux_render_and_local_overlay(self):
        source_home = '/Users/example'
        settings = {'env': {'TOKEN': 'local-only'}, 'pluginConfigs': {'private': {}},
                    'hooks': {'PreToolUse': [{'hooks': [
                        {'command': source_home + '/.claude/hooks/rtk.sh'},
                        {'command': '/Applications/OnlyMac.app/run'}]}]},
                    'statusLine': {'command': source_home + '/.claude/statusline-command.sh'}}
        (self.c / 'settings.json').write_text(json.dumps(settings))
        captured = p.capture(self.home)
        self.assertNotIn('env', json.loads(captured['settings.json']))
        self.assertNotIn('pluginConfigs', json.loads(captured['settings.json']))
        meta = {'source_home': source_home, 'source_platform': 'Darwin',
                'profiles': {'linux': {'platform': 'Linux', 'sync_statusline': False, 'local_md': 'Linux'}}}
        (self.c / 'settings.host.json').write_text(json.dumps({'model': 'host-model'}))
        out = p.render(meta, captured, self.home, 'linux')
        s = json.loads(out['settings.json'])
        self.assertEqual(s['env']['TOKEN'], 'local-only')
        self.assertEqual(s['model'], 'host-model')
        self.assertEqual(s['hooks']['PreToolUse'][0]['hooks'], [{'command': str(self.c) + '/hooks/rtk.sh'}])
        self.assertNotIn('statusLine', s)
        self.assertEqual(out['LOCAL.md'], b'Linux')

    def test_host_only_and_owned_deletions(self):
        (self.c / 'private.md').write_bytes(b'keep')
        (self.c / 'managed.md').write_bytes(b'remove')
        changes = p.plan(self.c, {}, {'managed.md': p.digest(b'remove')})
        backup = p.apply(self.c, changes, {}, self.root / 'backups')
        self.assertTrue((self.c / 'private.md').exists())
        self.assertFalse((self.c / 'managed.md').exists())
        self.assertEqual((backup / 'managed.md').read_bytes(), b'remove')

    def test_local_edit_conflict_and_symlink_destination(self):
        (self.c / 'managed').write_bytes(b'edited')
        with self.assertRaisesRegex(ValueError, 'Locally modified'):
            p.plan(self.c, {}, {'managed': p.digest(b'original')})
        (self.c / 'link').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            p.plan(self.c, {'link/file': b'unsafe'}, {})

    def test_explicit_overwrite_backs_up_but_not_deletes_edited_file(self):
        (self.c / 'managed').write_bytes(b'edited')
        old = {'managed': p.digest(b'original')}
        changes = p.plan(self.c, {'managed': b'new'}, old, overwrite=True)
        backup = p.apply(self.c, changes, {}, self.root / 'backups')
        self.assertEqual((backup / 'managed').read_bytes(), b'edited')
        with self.assertRaisesRegex(ValueError, 'Locally modified'):
            p.plan(self.c, {}, old, overwrite=True)

    def test_executable_mode_is_repaired(self):
        (self.c / 'script').write_bytes(b'run')
        (self.c / 'script').chmod(0o600)
        changes = p.plan(self.c, {'script': b'run'}, {}, {'script': 0o700})
        p.apply(self.c, changes, {'script': 0o700}, self.root / 'backups')
        self.assertEqual((self.c / 'script').stat().st_mode & 0o777, 0o700)

    def test_partial_write_rollback(self):
        (self.c / 'a').write_bytes(b'original')
        changes = [('a', b'original', b'changed'), ('z', None, b'new')]
        atomic = p.atomic
        def failing(path, data, mode=0o600):
            if path == self.c / 'z':
                raise OSError('simulated disk error')
            return atomic(path, data, mode)
        with patch.object(p, 'atomic', failing), self.assertRaises(OSError):
            p.apply(self.c, changes, {}, self.root / 'backups')
        self.assertEqual((self.c / 'a').read_bytes(), b'original')

    def test_plugin_failure_propagates(self):
        (self.c / 'settings.json').write_text(json.dumps({'enabledPlugins': {'x@m': True},
             'extraKnownMarketplaces': {'m': {'source': {'source': 'github', 'repo': 'org/repo'}}}}))
        with patch('ccsync.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['claude'])):
            with self.assertRaises(subprocess.CalledProcessError):
                ccsync.plugins(self.home)


@unittest.skipUnless(shutil.which('git-crypt'), 'git-crypt is required for real encryption integration')
class GitTests(unittest.TestCase):
    def setUp(self):
        PortableTests.setUp(self)
        self.repo = self.root / 'repo'
        self.remote = self.root / 'remote.git'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '--bare', str(self.remote)], check=True, capture_output=True)
        ccsync.git(self.repo, 'init', '-b', 'main')
        ccsync.git(self.repo, 'config', 'user.email', 'test@example.invalid')
        ccsync.git(self.repo, 'config', 'user.name', 'Test')
        (self.repo / '.gitattributes').write_text('config/** filter=git-crypt diff=git-crypt\n')
        ccsync.git(self.repo, 'add', '.gitattributes')
        ccsync.git(self.repo, 'commit', '-m', 'init')
        ccsync.git(self.repo, 'remote', 'add', 'origin', str(self.remote))
        ccsync.git(self.repo, 'push', '-u', 'origin', 'main')
        subprocess.run(['git-crypt', 'init'], cwd=self.repo, check=True, capture_output=True)

    def args(self, command, **kwargs):
        return argparse.Namespace(repo=str(self.repo), command=command, yes=True,
                                  profiles=None, message=None, no_fetch=True, profile=None,
                                  install_plugins=False, **kwargs)

    def execute(self, args):
        with patch.object(Path, 'home', return_value=self.home), contextlib.redirect_stdout(io.StringIO()):
            ccsync.run(args)

    def test_real_encrypted_push_and_pull(self):
        (self.repo / 'AGENTS.md').write_text('unrelated')
        empty = self.c / 'skills/example/__init__.py'
        empty.parent.mkdir(parents=True)
        empty.touch()
        self.execute(self.args('push'))
        blob = ccsync.git(self.repo, 'show', 'HEAD:config/CLAUDE.md').stdout
        self.assertTrue(blob.startswith(b'\x00GITCRYPT\x00'))
        self.assertNotEqual(ccsync.git(self.repo, 'ls-files', '--error-unmatch', 'AGENTS.md', check=False).returncode, 0)
        self.home = self.root / 'destination'
        self.c = self.home / '.claude'
        self.c.mkdir(parents=True)
        (self.c / 'CLAUDE.md').write_text('old local')
        self.execute(self.args('pull'))
        self.assertEqual((self.c / 'CLAUDE.md').read_text(), 'Hello\n')

    def test_source_pull_refused(self):
        self.execute(self.args('push'))
        with self.assertRaisesRegex(ValueError, 'source home'):
            self.execute(self.args('pull'))

    def test_wrong_platform_refused(self):
        profiles = {'wrong': {'platform': 'NotThisOS'}}
        files = p.capture(self.home, profiles=profiles)
        for name, data in files.items():
            p.atomic(self.repo / 'config' / name, data)
        self.home = self.root / 'destination'
        args = self.args('pull')
        args.profile = 'wrong'
        with self.assertRaisesRegex(ValueError, 'platform'):
            self.execute(args)
        self.assertFalse((self.home / '.claude').exists())

    def test_interrupted_commit_worktree_recovers(self):
        files = p.capture(self.home)
        for name, data in files.items():
            p.atomic(self.repo / 'config' / name, data)
        self.execute(self.args('push'))
        self.assertTrue(ccsync.git(self.repo, 'show', 'HEAD:config/snapshot.json').stdout.startswith(b'\x00GITCRYPT\x00'))

    def test_failed_push_retried_without_changes(self):
        ccsync.git(self.repo, 'remote', 'set-url', 'origin', str(self.root / 'missing.git'))
        with self.assertRaises(subprocess.CalledProcessError):
            self.execute(self.args('push'))
        ccsync.git(self.repo, 'remote', 'set-url', 'origin', str(self.remote))
        self.execute(self.args('push'))
        self.assertEqual(ccsync.git(self.repo, 'rev-parse', 'HEAD').stdout,
                         ccsync.git(self.repo, 'rev-parse', 'origin/main').stdout)

    def test_missing_encryption_blocks_before_writes(self):
        ccsync.git(self.repo, 'config', '--unset', 'filter.git-crypt.clean')
        with self.assertRaisesRegex(ValueError, 'git-crypt'):
            self.execute(self.args('push'))
        self.assertFalse((self.repo / 'config').exists())

    def test_plaintext_filter_rejected_before_commit(self):
        before = ccsync.git(self.repo, 'rev-parse', 'HEAD').stdout
        ccsync.git(self.repo, 'config', 'filter.git-crypt.clean', 'cat')
        with self.assertRaisesRegex(ValueError, 'ciphertext'):
            self.execute(self.args('push'))
        self.assertEqual(ccsync.git(self.repo, 'rev-parse', 'HEAD').stdout, before)
        self.assertFalse(ccsync.git(self.repo, 'diff', '--cached', '--name-only').stdout)

    def test_missing_skill_tree_needs_deletion_opt_in(self):
        skill = self.c / 'skills/example/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('example')
        self.execute(self.args('push'))
        skill.unlink()
        with self.assertRaisesRegex(ValueError, 'allow-delete'):
            self.execute(self.args('push'))
        self.assertTrue((self.repo / 'config/skills/example/SKILL.md').exists())

    def test_destination_reuses_profile_for_status(self):
        files = p.capture(self.home, profiles={'dest': {'platform': p.platform.system()}})
        for name, data in files.items():
            p.atomic(self.repo / 'config' / name, data)
        self.home = self.root / 'destination'
        args = self.args('pull')
        args.profile = 'dest'
        self.execute(args)
        args = self.args('status', direction=None)
        self.execute(args)
        self.assertEqual(args.profile, 'dest')

    def test_legacy_destination_can_adopt_profile(self):
        files = p.capture(self.home, profiles={'dest': {'platform': p.platform.system()}})
        p.atomic(self.repo / 'config/CLAUDE.md', b'Legacy\n')
        self.home = self.root / 'destination'
        self.execute(self.args('pull'))
        for name, data in files.items():
            p.atomic(self.repo / 'config' / name, data)
        args = self.args('pull')
        args.profile = 'dest'
        self.execute(args)
        self.assertEqual((self.home / '.claude/CLAUDE.md').read_text(), 'Hello\n')

    def test_staged_changes_preserved(self):
        (self.repo / 'other').write_text('user work')
        ccsync.git(self.repo, 'add', 'other')
        with self.assertRaisesRegex(ValueError, 'staged'):
            self.execute(self.args('push'))
        self.assertEqual(ccsync.git(self.repo, 'diff', '--cached', '--name-only').stdout, b'other\n')


if __name__ == '__main__':
    unittest.main()
