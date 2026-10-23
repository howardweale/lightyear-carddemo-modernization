"""CI-only synthetic secrets. No operator paths, Tower, models or signing."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import copau_private_prerequisites as helper


class CopauPrerequisiteTests(unittest.TestCase):
    def setUp(self):
        # Hosted Windows TEMP can have replaceable shared ancestors. Keep the
        # disposable fixture under the runner profile; production ACL checks stay on.
        parent = Path(os.environ['USERPROFILE']).resolve(strict=True) if os.name == 'nt' else None
        self.temp = tempfile.TemporaryDirectory(prefix='copau-ci-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.exposed = self.base / 'candidate'
        self.exposed.mkdir()
        self.store = helper.Store(self.base / 'private', [self.exposed])
        try:
            self.store.initialize()
        except helper.Refused:
            # CI-only public ACL metadata; never print files, paths or key values.
            if os.name == 'nt' and not getattr(type(self), '_acl_reported', False):
                type(self)._acl_reported = True
                try:
                    sid, rows = helper.windows_acl(list(self.store.root.parents))
                    refused = []
                    for index, row in enumerate(rows):
                        try:
                            helper.ancestors_acl([row], sid)
                        except helper.Refused:
                            refused.append(dict(ancestor_index=index, acl=row))
                    print('CI_ANCESTOR_ACL_REFUSAL ' + json.dumps(
                        dict(sid=sid, refused=refused), sort_keys=True), file=sys.stderr)
                except Exception:
                    print('CI_ANCESTOR_ACL_DIAGNOSTIC_UNAVAILABLE', file=sys.stderr)
            raise

    def source(self):
        return dict(schema='copau-private-source/1', freeze_sha256=helper.FREEZE_SHA,
                    amendment_sha256=helper.AMENDMENT_SHA, source_reference='synthetic-private-source',
                    coverage_description='CI-only expected-state fixture',
                    approved_expected_state_source=True,
                    values=['synthetic-ci-secret-value-never-print-this-value-' + 'A' * 40])

    def stage(self, source=None):
        self.store.write('expected-source.json', helper.encoded(source or self.source()))

    def test_key_generation_and_registration_preserve_bytes(self):
        helper.key_info(self.store, 'ci-operator', 'ci-copau-2026', create=True)
        raw = self.store.read('work-order-hmac.txt')
        self.assertRegex(raw.decode(), '^[0-9a-f]{64}$')
        with self.assertRaises(helper.Refused):
            helper.key_info(self.store, 'ci-operator', 'ci-other', create=True)
        self.assertEqual(raw, self.store.read('work-order-hmac.txt'))

    def test_existing_root_is_not_reinitialized(self):
        self.store.write('preserved.json', b'{"synthetic":true}')
        with self.assertRaises(helper.Refused):
            self.store.initialize()
        self.assertEqual(self.store.read('preserved.json'), b'{"synthetic":true}')

    def test_freeze_constants_bind_exact_committed_public_records(self):
        root = Path(__file__).resolve().parents[1]
        for name, digest in [
            ('copau-factory-judge-freeze-2026-10-18.json', helper.FREEZE_SHA),
            ('copau-factory-judge-freeze-amendment-2026-10-20.json', helper.AMENDMENT_SHA)
        ]:
            self.assertEqual(helper.hashlib.sha256((root / 'docs/factory' / name).read_bytes()).hexdigest(), digest)

    def test_existing_key_never_replaced_and_short_key_refused(self):
        raw = b'CI-existing-private-key-' + b'z' * 40
        self.store.write('work-order-hmac.txt', raw)
        helper.key_info(self.store, 'ci-operator', 'ci-existing')
        self.assertEqual(raw, self.store.read('work-order-hmac.txt'))
        other = helper.Store(self.base / 'short', [self.exposed])
        other.initialize()
        other.write('work-order-hmac.txt', b'too-short')
        with self.assertRaises(helper.Refused):
            helper.key_info(other, 'ci-operator', 'ci-short')
        self.assertFalse(other.path('work-order-custody.json').exists())

    def test_bundle_binding_exact_bytes_and_private_provenance(self):
        self.stage()
        info = helper.prepare_bundle(self.store, helper.FREEZE_SHA, helper.AMENDMENT_SHA)
        raw = self.store.read('copau-expected-values.json')
        self.assertEqual(info, helper.bundle_info(raw))
        self.assertEqual(set(info), {'sha256', 'size_bytes', 'count'})
        self.assertNotIn(b'source_reference', raw)
        self.assertEqual(helper.load_json(self.store.read('expected-source.json')), self.source())
        with self.assertRaises(helper.Refused):
            helper.prepare_bundle(self.store, helper.FREEZE_SHA, helper.AMENDMENT_SHA)
        self.assertEqual(raw, self.store.read('copau-expected-values.json'))

    def test_existing_bundle_keeps_original_serialization(self):
        self.stage()
        data = dict(schema='factory-private-expected-values/1', values=self.source()['values'])
        raw = json.dumps(data, indent=4).encode()
        self.store.write('copau-expected-values.json', raw)
        info = helper.prepare_bundle(self.store, helper.FREEZE_SHA, helper.AMENDMENT_SHA, existing=True)
        self.assertEqual(raw, self.store.read('copau-expected-values.json'))
        self.assertEqual(info['size_bytes'], len(raw))

    def test_wrong_frozen_binding_and_unattested_source_refused(self):
        self.stage()
        with self.assertRaises(helper.Refused):
            helper.prepare_bundle(self.store, '3' * 64, helper.AMENDMENT_SHA)
        self.assertFalse(self.store.path('copau-expected-values.json').exists())
        wrong = self.source()
        wrong['approved_expected_state_source'] = False
        other = helper.Store(self.base / 'unattested', [self.exposed])
        other.initialize()
        other.write('expected-source.json', helper.encoded(wrong))
        with self.assertRaises(helper.Refused):
            helper.prepare_bundle(other, helper.FREEZE_SHA, helper.AMENDMENT_SHA)

    def test_schema_duplicates_limits_and_normalized_values(self):
        base = dict(schema='factory-private-expected-values/1', values=['x' * 40])
        invalid = [dict(base, values=[]), dict(base, values=['x' * 39]),
                   dict(base, values=['x' * 40, 'x' * 40]),
                   dict(base, values=['x' * 40, 'X ' * 40]),
                   dict(base, values=[False]), dict(base, private_path='forbidden'),
                   dict(base, values=[str(i) + 'x' * 40 for i in range(65)])]
        for item in invalid:
            with self.subTest(item=invalid.index(item)), self.assertRaises(helper.Refused):
                helper.bundle_info(helper.encoded(item))
        with self.assertRaises(helper.Refused):
            helper.bundle_info(b' ' * (helper.LIMIT + 1))
        with self.assertRaises(helper.Refused):
            helper.bundle_info(b'{"schema":"wrong","schema":"factory-private-expected-values/1","values":[]}')

    def test_exposed_roots_and_git_ancestor_refused(self):
        for root, exposed in [(self.exposed / 'private', self.exposed),
                              (self.base, self.exposed), (self.exposed, self.exposed)]:
            with self.assertRaises(helper.Refused):
                helper.Store(root, [exposed]).initialize()
        repo = self.base / 'checkout'
        repo.mkdir()
        (repo / '.git').write_text('gitdir: synthetic')
        with self.assertRaises(helper.Refused):
            helper.Store(repo / 'private', [self.exposed]).initialize()

    def test_hardlink_and_directory_instead_of_file_refused(self):
        self.store.write('expected-source.json', helper.encoded(self.source()))
        os.link(self.store.path('expected-source.json'), self.store.root / 'second-link.json')
        with self.assertRaises(helper.Refused):
            self.store.read('expected-source.json')
        self.store.path('directory.json').mkdir()
        with self.assertRaises(helper.Refused):
            self.store.read('directory.json')

    def test_link_ancestor_refused(self):
        linked = self.base / 'linked'
        if os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(linked), str(self.store.root)],
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)
        else:
            linked.symlink_to(self.store.root, target_is_directory=True)
        self.addCleanup(lambda: os.rmdir(linked) if os.name == 'nt' else linked.unlink())
        with self.assertRaises(helper.Refused):
            helper.Store(linked, [self.exposed]).check()

    def test_unsafe_real_acl_refused_before_key_creation(self):
        if os.name == 'nt':
            script = r'''
$ErrorActionPreference='Stop'
$p=[Console]::In.ReadToEnd() | ConvertFrom-Json
$a=[IO.Directory]::GetAccessControl($p)
$a.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
  [Security.Principal.SecurityIdentifier]::new('S-1-1-0'),'ReadAndExecute',
  'ContainerInherit,ObjectInherit','None','Allow'))
[IO.Directory]::SetAccessControl($p,$a)
'''
            helper.powershell(script, str(self.store.root))
        else:
            self.store.root.chmod(0o755)
        with self.assertRaises(helper.Refused):
            helper.key_info(self.store, 'ci-operator', 'ci-unsafe', create=True)
        self.assertFalse(self.store.path('work-order-hmac.txt').exists())

    def test_unsafe_ancestor_and_root_acl_rows_refused(self):
        sid = 'S-1-5-21-123'
        safe = dict(owner=sid, protected=True, rules=[
            dict(sid=sid, allow=True, inheritOnly=False, rights=0x1F01FF)])
        helper.private_acl(safe, sid, True)
        for change in [dict(owner='S-1-1-0'), dict(protected=False),
                       dict(rules=[dict(sid='S-1-1-0', allow=True, inheritOnly=False, rights=0x1F01FF)])]:
            with self.assertRaises(helper.Refused):
                helper.private_acl(dict(safe, **change), sid, True)
        unsafe = dict(safe, rules=[dict(sid='S-1-1-0', allow=True, inheritOnly=False, rights=0x40)])
        with self.assertRaises(helper.Refused):
            helper.ancestors_acl([unsafe], sid)

    def test_public_projection_has_no_values_key_or_private_path(self):
        helper.key_info(self.store, 'ci-operator', 'ci-key', create=True)
        self.stage()
        helper.prepare_bundle(self.store, helper.FREEZE_SHA, helper.AMENDMENT_SHA)
        record = helper.public_record(self.store, 'a' * 40, helper.FREEZE_SHA, helper.AMENDMENT_SHA)
        raw = helper.encoded(record)
        for secret in [self.store.read('work-order-hmac.txt'), self.source()['values'][0].encode(),
                       str(self.store.root).encode(), b'synthetic-private-source']:
            self.assertNotIn(secret, raw)
        self.assertFalse(record['signed'])
        self.assertFalse(record['run_authorized'])
        self.assertEqual(helper.validate_public(record), record)
        self.assertEqual(self.store.read('public-prerequisites.json'), raw)
        bad = deepcopy(record)
        bad['private_expected_values']['values'] = ['do not accept']
        with self.assertRaises(helper.Refused):
            helper.validate_public(bad)
        with self.assertRaises(helper.Refused):
            helper.public_record(self.store, 'a' * 40, helper.FREEZE_SHA, helper.AMENDMENT_SHA)

    def test_replaced_key_refuses_public_export(self):
        helper.key_info(self.store, 'ci-operator', 'ci-key', create=True)
        self.stage()
        helper.prepare_bundle(self.store, helper.FREEZE_SHA, helper.AMENDMENT_SHA)
        self.store.path('work-order-hmac.txt').write_bytes(b'b' * 64)
        with self.assertRaises(helper.Refused):
            helper.public_record(self.store, 'a' * 40, helper.FREEZE_SHA, helper.AMENDMENT_SHA)
        self.assertFalse(self.store.path('public-prerequisites.json').exists())

    def test_changed_file_identity_during_read_refused(self):
        self.store.write('synthetic.json', b'{"synthetic":true}')
        with patch.object(helper, 'identity', side_effect=[('original',), ('changed',)]):
            with self.assertRaises(helper.Refused):
                self.store.read('synthetic.json')

    def test_cli_suppresses_private_exception_and_refuses_non_windows(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ['helper', 'initialize', '--exposed-root', str(self.exposed)]
        with patch.object(sys, 'argv', argv), patch.object(helper, 'windows_host', return_value=True), \
                patch.object(helper, 'ROOT', self.store.root), \
                patch.object(helper.Store, 'initialize', side_effect=ValueError('PRIVATE-CONTENT')) as action, \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(helper.main(), 1)
            action.assert_called_once()
        self.assertNotIn('PRIVATE-CONTENT', stdout.getvalue() + stderr.getvalue())
        self.assertNotIn('PREPARED', stdout.getvalue())
        with patch.object(sys, 'argv', argv), patch.object(helper, 'windows_host', return_value=False), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(helper.main(), 1)


class CopauAclTransportTests(unittest.TestCase):
    def test_acl_metadata_transport_on_disposable_public_directory(self):
        if os.name != 'nt':
            # No skip: the portable half verifies the production error channel.
            result = subprocess.CompletedProcess([], 1, b'')
            with patch.dict(os.environ, {'SystemRoot': '/synthetic'}), \
                    patch.object(helper.subprocess, 'run', return_value=result) as call:
                with self.assertRaises(helper.Refused):
                    helper.powershell(helper.ACL_SCRIPT, ['/synthetic'])
                self.assertIs(call.call_args.kwargs['stderr'], subprocess.DEVNULL)
            return
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            paths = [str(base), *(str(p) for p in base.parents)]
            executable = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            # This fixture contains no keys, bundle or operator configuration.
            # Capture only its ACL transport error; production remains redacted.
            result = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-Command', helper.ACL_SCRIPT],
                input=helper.encoded(paths), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace')[-2000:])
            data = helper.load_json(result.stdout)
            self.assertEqual(len(data['rows']), len(paths))
            self.assertTrue(data['sid'].startswith('S-1-'))



class CopauOwnerRightsTests(unittest.TestCase):
    def test_owner_rights_resolve_only_to_the_checked_current_owner(self):
        sid = 'S-1-5-21-123'
        owners = [sid, 'S-1-5-18', 'S-1-5-32-544',
                  'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464']
        for owner in owners:
            # Exact public ACE shape observed on the hosted Windows fixture.
            row = dict(owner=owner, protected=True, rules=[
                dict(sid='S-1-3-4', allow=True, inheritOnly=False, rights=2032127),
                dict(sid='S-1-5-18', allow=True, inheritOnly=False, rights=2032127),
                dict(sid='S-1-5-32-544', allow=True, inheritOnly=False, rights=2032127)])
            with self.subTest(owner=owner):helper.ancestors_acl([row], sid)
        for owner in ['S-1-1-0', 'S-1-5-21-999', 'S-1-3-4', 'S-1-3-0']:
            row['owner'] = owner
            with self.subTest(untrusted_owner=owner), self.assertRaises(helper.Refused):
                helper.ancestors_acl([row], sid)

    def test_owner_rights_do_not_hide_other_dangerous_ancestor_grants(self):
        sid = 'S-1-5-21-123'
        owner_rule = dict(sid='S-1-3-4', allow=True, inheritOnly=False, rights=0x1F01FF)
        for principal in ['S-1-1-0', 'S-1-5-21-999', 'S-1-3-0', 'S-1-3-1']:
            for right in [0x40, 0x10000, 0x40000, 0x80000]:
                extra = dict(sid=principal, allow=True, inheritOnly=False, rights=right)
                row = dict(owner=sid, protected=True, rules=[owner_rule, extra])
                with self.subTest(principal=principal, right=right), self.assertRaises(helper.Refused):
                    helper.ancestors_acl([row], sid)
                # Existing deny and inherit-only handling is unchanged.
                helper.ancestors_acl([dict(row, rules=[owner_rule, dict(extra, allow=False)])], sid)
                helper.ancestors_acl([dict(row, rules=[owner_rule, dict(extra, inheritOnly=True)])], sid)

    def test_private_directory_and_file_policy_stays_exact_sid_only(self):
        sid = 'S-1-5-21-123'
        own = dict(sid=sid, allow=True, inheritOnly=False, rights=0x1F01FF)
        alias = dict(own, sid='S-1-3-4')
        for directory in [False, True]:
            helper.private_acl(dict(owner=sid, protected=True, rules=[own]), sid, directory)
            for rules in [[alias], [own, alias]]:
                with self.subTest(directory=directory, rules=rules), self.assertRaises(helper.Refused):
                    helper.private_acl(dict(owner=sid, protected=True, rules=rules), sid, directory)


if __name__ == '__main__':
    unittest.main()
