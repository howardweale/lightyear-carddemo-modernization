"""CI-only real Git object tests; synthetic companion bytes grant no authority.

These cover binding loading and companion object checks, not full inspect()
with the real trusted anchor, live PR context, or an operator-approved profile.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import check_f2_fence_exceptions as gate


class DurableBindingGitTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        temp = tempfile.TemporaryDirectory(prefix='p5-binding-git-')
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / 'objects.git'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME='Synthetic CI Fixture', GIT_AUTHOR_EMAIL='ci@example.invalid',
                        GIT_COMMITTER_NAME='Synthetic CI Fixture', GIT_COMMITTER_EMAIL='ci@example.invalid',
                        GIT_AUTHOR_DATE='2026-10-26T00:00:00+00:00',
                        GIT_COMMITTER_DATE='2026-10-26T00:00:00+00:00')
        subprocess.run(['git', 'init', '--bare', str(self.repo)], env=self.env,
                       check=True, capture_output=True)
        self.env['GIT_INDEX_FILE'] = str(Path(temp.name) / 'fixture.index')
        root = Path(__file__).resolve().parents[1]
        self.pending = json.loads((root / gate.DURABLE_BINDING).read_text(encoding='utf-8'))
        self.pending.update(status='pending-exact-hash-approval', approval=None,
                            approved_change_commit=None)

    def git(self, *args, data=None):
        return subprocess.run(['git', '-C', str(self.repo), *args], input=data,
                              env=self.env, check=True, capture_output=True).stdout

    def commit(self, files, parent=None):
        # Same real Git objects; cache immutable blobs and batch only index input.
        # No checkout, hooks, signing, network, or ref updates.
        self.git('read-tree', '--empty')
        blobs = getattr(self, '_fixture_blob_oids', None)
        if blobs is None:
            blobs = self._fixture_blob_oids = {}
        records = []
        for path, (mode, raw) in sorted(files.items()):
            if '\x00' in path:
                raise ValueError('NUL in fixture path')
            oid = blobs.get(raw)
            if oid is None:
                oid = self.git('hash-object', '-w', '--stdin', data=raw).decode().strip()
                blobs[raw] = oid
            records.append((mode + ' ' + oid + '\t' + path + '\x00').encode('utf-8'))
        if records:
            self.git('update-index', '-z', '--index-info', data=b''.join(records))
        tree = self.git('write-tree').decode().strip()
        parents = ['-p', parent] if parent else []
        return self.git('commit-tree', tree, *parents, '--no-gpg-sign',
                        '-m', 'Synthetic binding CI fixture').decode().strip()

    def companion_fixture(self):
        # Exact runtime path set, but synthetic content and helper-only metadata.
        before, after, entries = {}, {}, []
        for path, pinned in sorted(gate.DURABLE_RUNTIME.items()):
            old = ('synthetic preimage '+path+'\n').encode()
            new = ('synthetic postimage '+path+'\n').encode()
            if pinned['before'] is not None:
                before[path] = ('100644', old)
            after[path] = ('100644', new)
            entries.append(dict(path=path,
                before=None if pinned['before'] is None else dict(mode='100644', sha256=gate.sha(old)),
                after=dict(mode='100644', sha256=gate.sha(new))))
        base = self.commit(before); head = self.commit(after, base)
        binding = dict(entries=entries, approved_change_commit=head)
        # Deliberately not a valid approval document: only the object helper consumes this.
        with self.assertRaises(ValueError):
            gate.validate_durable_binding(binding)
        return before, after, base, head, binding

    def test_real_git_pending_load_absence_candidate_mutation_and_mode_refusals(self):
        raw = json.dumps(self.pending, sort_keys=True).encode()
        files = {gate.DURABLE_BINDING: ('100644', raw)}
        absent = self.commit({})
        base = self.commit(files, absent)
        unchanged = self.commit(dict(files, **{'unfenced.txt': ('100644', b'fixture')}), base)
        self.assertIsNone(gate.load_durable_binding(self.repo, absent, absent))
        self.assertIsNone(gate.load_durable_binding(self.repo, base, unchanged))
        with self.assertRaisesRegex(ValueError, 'candidate-durable-binding-refused'):
            gate.load_durable_binding(self.repo, absent, base)
        for mode, content, reason in [('100644', raw+b' ', 'candidate-durable-binding-refused'),
                                      ('100755', raw, 'blob-mode')]:
            candidate = self.commit({gate.DURABLE_BINDING: (mode, content)}, base)
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, reason):
                gate.load_durable_binding(self.repo, base, candidate)
        with self.assertRaisesRegex(ValueError, 'missing-or-ambiguous-blob'):
            gate.load_durable_binding(self.repo, base, absent)

    def test_real_git_all_companions_and_candidate_or_approved_object_refusals(self):
        before, after, base, head, binding = self.companion_fixture()
        result = gate.inspect_durable_companions(self.repo, base, head, binding, set(), set())
        self.assertEqual(result, binding['entries'])
        for path in sorted(after):
            for kind in ('bytes', 'mode', 'missing'):
                bad = dict(after)
                if kind == 'bytes': bad[path] = ('100644', after[path][1]+b'changed')
                elif kind == 'mode': bad[path] = ('100755', after[path][1])
                else: del bad[path]
                bad_commit = self.commit(bad, base)
                for target in ('head', 'approved'):
                    selected = copy.deepcopy(binding)
                    if target == 'approved': selected['approved_change_commit'] = bad_commit
                    with self.subTest(path=path, kind=kind, target=target), self.assertRaises(ValueError):
                        gate.inspect_durable_companions(self.repo, base,
                            bad_commit if target == 'head' else head, selected, set(), set())
        bad = dict(binding, approved_change_commit='0'*40)
        with self.assertRaises(subprocess.CalledProcessError):
            gate.inspect_durable_companions(self.repo, base, head, bad, set(), set())

    def test_real_git_preimage_absence_and_protected_path_refusals(self):
        before, after, base, head, binding = self.companion_fixture()
        for entry in binding['entries']:
            path = entry['path']; bad = dict(before)
            if entry['before'] is None:
                bad[path] = ('100644', b'unexpected preimage')
                reason = 'durable-preimage-not-absent'
            else:
                bad[path] = ('100644', before[path][1]+b'changed')
                reason = 'durable-preimage'
            bad_base = self.commit(bad)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, reason):
                gate.inspect_durable_companions(self.repo, bad_base, head, binding, set(), set())
            for excluded, prefixes in [({path}, set()), (set(), {path.rsplit('/', 1)[0]+'/'} )]:
                with self.subTest(path=path, prefixes=prefixes), self.assertRaisesRegex(
                        ValueError, 'judge-or-posttran-exception-refused'):
                    gate.inspect_durable_companions(self.repo, base, head, binding, excluded, prefixes)

    def test_batched_fixture_objects_match_original_git_construction(self):
        def reference_commit(self, files, parent=None):
            # No checkout, hooks, signing, network, or ref updates; disposable CI objects only.
            self.git('read-tree', '--empty')
            for path, (mode, raw) in sorted(files.items()):
                oid = self.git('hash-object', '-w', '--stdin', data=raw).decode().strip()
                self.git('update-index', '--add', '--cacheinfo', mode, oid, path)
            tree = self.git('write-tree').decode().strip()
            parents = ['-p', parent] if parent else []
            return self.git('commit-tree', tree, *parents, '--no-gpg-sign',
                            '-m', 'Synthetic binding CI fixture').decode().strip()

        cases = [
            {},
            {'a.txt': ('100644', b'same'), 'nested/b.txt': ('100755', b'same')},
            {'space name.txt': ('100644', b'changed'),
             'tab\tand\nnewline.txt': ('100644', b'raw\x00bytes')},
            {'a.txt': ('100755', b'same')},
            {},
        ]
        parent = None
        for files in cases:
            with self.subTest(paths=sorted(files)):
                expected = reference_commit(self, files, parent)
                actual = self.commit(files, parent)
                self.assertEqual(actual, expected)
                self.assertEqual(self.git('cat-file', '-p', actual),
                                 self.git('cat-file', '-p', expected))
                parent = actual

    def test_batched_fixture_reuses_blobs_but_writes_each_real_tree(self):
        from unittest import mock
        files = {'one': ('100644', b'shared'), 'two': ('100755', b'shared')}
        with mock.patch.object(self, 'git', wraps=self.git) as observed:
            first = self.commit(files)
            second = self.commit({'one': ('100755', b'shared'),
                                  'three': ('100644', b'new')}, first)
        calls = observed.call_args_list
        self.assertEqual(sum(c.args[0] == 'hash-object' for c in calls), 2)
        self.assertEqual(sum(c.args[0] == 'update-index' for c in calls), 2)
        self.assertEqual(sum(c.args[0] == 'read-tree' for c in calls), 2)
        self.assertEqual(sum(c.args[0] == 'write-tree' for c in calls), 2)
        self.assertEqual(sum(c.args[0] == 'commit-tree' for c in calls), 2)
        self.assertNotEqual(first, second)
        self.assertEqual(self.git('show', second + ':one'), b'shared')
        self.assertEqual(self.git('show', second + ':three'), b'new')
        self.assertEqual(self.git('ls-tree', second, 'two'), b'')
