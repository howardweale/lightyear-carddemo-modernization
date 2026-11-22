"""Synthetic custody, schema, boundary and public-worker tests; no host commands."""
import ast
import copy
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tools import intcalc_attended_reference_public as worker
from tools import intcalc_private_reference_host as h

H = 'a'*64
COMMIT = 'a'*40
TREE = 'b'*40


def profile():
    return dict(schema='ha-private-host-profile/1', source_commit=COMMIT, source_tree=TREE,
        private_root='/private-public-fixture', client_config='/private-empty-config',
        binaries={name: dict(path='/usr/bin/'+name, sha256=H) for name in h.BINS}, dockerd_sha256=H)


def custody():
    return dict(schema='ha-separate-account-custody-return/1', status='OBSERVED',
        observed_at_with_offset='2026-11-17T18:00:00-08:00', operation_id=H,
        private_profile_commitment_sha256=H, reviewed_source_commit=COMMIT, reviewed_source_tree=TREE,
        raw_private_evidence_retained_by='Howard', raw_private_values_included=False,
        docker_users_group_state='PRESENT', engine_kind='PRIVATE_DISTRO_ENGINE',
        public_host_qualification='PENDING', qualification_receipt_sha256=None,
        checks={name: True for name in h.PRE+h.POST}, administrators_including_howard_trusted=True,
        no_swap_required=False, no_hibernation_required=False, crash_dump_controls_required=False,
        execution_authorized=False)


def approval():
    return dict(schema='ha-operation-approval/1', authority='Howard', operation_id=H,
        mode='QUALIFY_PUBLIC', profile_sha256=h.sha(h.canonical(profile())), custody_sha256=H,
        source_commit=COMMIT, source_tree=TREE, valid_from='2026-11-17T18:00:00-08:00',
        expires_at='2026-11-17T20:00:00-08:00', public_only=True)


class HostContractTests(unittest.TestCase):
    def validate(self, row, post=False):
        return h.custody(row, H, H, COMMIT, TREE, post=post)

    def test_all_required_preflight_fields_and_no_extra_keys(self):
        self.validate(custody())
        for key in h.PRE:
            for value in (False, None, 1):
                row = custody(); row['checks'][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(h.Refused, 'host-custody'):
                    self.validate(row)
        row = custody(); row['checks']['extra'] = True
        with self.assertRaises(h.Refused): self.validate(row)

    def test_postflight_and_continuity_are_required(self):
        for key in h.POST:
            row = custody(); row['checks'][key] = None
            self.validate(row)
            with self.subTest(key=key), self.assertRaisesRegex(h.Refused, 'host-custody'):
                self.validate(row, post=True)

    def test_wrong_operation_source_profile_cannot_reuse_receipt(self):
        for key in ('operation_id', 'private_profile_commitment_sha256', 'reviewed_source_commit', 'reviewed_source_tree'):
            row = custody(); row[key] = '0'*64
            with self.subTest(key=key), self.assertRaisesRegex(h.Refused, 'host-custody'):
                self.validate(row)

    def test_unknown_group_or_desktop_engine_refuses(self):
        for key, value in (('docker_users_group_state', 'UNKNOWN'), ('engine_kind', 'DESKTOP'),
                           ('raw_private_values_included', True), ('status', 'NOT_OBSERVED')):
            row = custody(); row[key] = value
            with self.subTest(key=key), self.assertRaises(h.Refused): self.validate(row)
        row = custody(); row['docker_users_group_state'] = 'ABSENT'
        self.validate(row)

    def test_absent_swap_controls_do_not_weaken_first_write_boundary(self):
        row = custody()
        self.validate(row)
        self.assertFalse(row['no_swap_required'])
        self.assertIn('plaintext memory', h.FIRST_WRITE_LIMIT)
        self.assertTrue(row['administrators_including_howard_trusted'])

    def test_profile_requires_every_binary_hash(self):
        h.profile(profile())
        for name in h.BINS:
            row = profile(); row['binaries'][name]['sha256'] = None
            with self.subTest(name=name), self.assertRaises(h.Refused): h.profile(row)

    def test_approval_binds_exact_bytes_not_only_semantics(self):
        row = approval(); raw = h.canonical(row)
        now = datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc)
        self.assertEqual(h.approval(row, h.sha(raw), raw, profile(), 'QUALIFY_PUBLIC', now), 5400)
        with self.assertRaisesRegex(h.Refused, 'host-approval'):
            h.approval(row, h.sha(raw), raw+b'\n', profile(), 'QUALIFY_PUBLIC', now)

    def test_approval_mode_profile_and_source_refuse(self):
        for key, value in (('mode', 'PRIVATE_REFERENCE'), ('profile_sha256', '0'*64),
                           ('source_tree', '0'*40), ('public_only', False), ('authority', 'other')):
            row = approval(); row[key] = value; raw = h.canonical(row)
            with self.subTest(key=key), self.assertRaises(h.Refused):
                h.approval(row, h.sha(raw), raw, profile(), 'QUALIFY_PUBLIC',
                           datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc))

    def test_aware_order_expiry_and_maximum_window(self):
        for key, value in (('valid_from', '2026-11-17T18:00:00'),
                           ('expires_at', '2026-11-17T18:30:00-08:00'),
                           ('expires_at', '2026-11-18T01:00:00-08:00')):
            row = approval(); row[key] = value; raw = h.canonical(row)
            with self.subTest(key=key, value=value), self.assertRaisesRegex(h.Refused, 'host-clock'):
                h.approval(row, h.sha(raw), raw, profile(), 'QUALIFY_PUBLIC',
                           datetime(2026, 11, 18, 2, 30, tzinfo=timezone.utc))

    def test_strict_duplicate_float_and_nonfinite_refuse(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":1.0}', b'{"a":NaN}', b'{"a":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(h.Refused): h.strict(raw)

    def test_engine_join_requires_process_namespace_and_socket_listener(self):
        args = ['42', '/', 'mnt:[123]', 'mnt:[123]', '/run/docker.sock',
                ['u_str LISTEN /run/docker.sock users:(("dockerd",pid=42,fd=3))'],
                dict(OSType='linux', Architecture='amd64', DockerRootDir='/var/lib/docker')]
        h.engine_join(*args)
        for index, value in ((0, '0'), (1, '/other'), (2, 'mnt:[456]'),
                             (4, '/mnt/wsl/docker-desktop/shared.sock'), (5, []),
                             (5, ['u_str LISTEN /run/docker.sock users:(("proxy",pid=42,fd=3))']),
                             (5, ['u_str LISTEN /run/docker.sock users:(("dockerd",pid=43,fd=3))'])):
            changed = copy.deepcopy(args); changed[index] = value
            with self.subTest(index=index), self.assertRaisesRegex(h.Refused, 'host-endpoint'):
                h.engine_join(*changed)

    def test_desktop_with_plausible_local_socket_is_rejected(self):
        for info in (dict(OSType='linux', Architecture='amd64', OperatingSystem='Docker Desktop'),
                     dict(OSType='linux', Architecture='arm64'), dict(OSType='windows', Architecture='amd64')):
            with self.subTest(info=info), self.assertRaises(h.Refused):
                h.engine_join('42', '/', 'a', 'a', '/run/docker.sock',
                             ['x /run/docker.sock users:(("dockerd",pid=42,fd=3))'], info)


    def test_socket_activation_joins_dockerd_pid_in_same_tuple(self):
        args = ('42', '/', 'mnt:[12]', 'mnt:[12]', '/run/docker.sock')
        info = dict(OSType='linux', Architecture='amd64')
        start = 'u_str LISTEN 0 4096 /run/docker.sock 123 * 0 users:'
        h.engine_join(*args, [start + '(("systemd",pid=1,fd=7),("dockerd",pid=42,fd=3))'], info)
        for owners in ('(("dockerd",pid=41,fd=3),("proxy",pid=42,fd=4))',
                       '(("systemd",pid=1,fd=7))'):
            with self.subTest(owners=owners), self.assertRaisesRegex(h.Refused, 'host-endpoint'):
                h.engine_join(*args, [start + owners], info)

    def test_non_numeric_pid_never_reaches_privileged_reader(self):
        for pid in ('0', '1', '042', '../2', '42/exe', '-3', '４２', '2147483648'):
            with self.subTest(pid=pid), patch.object(h, 'attended_read') as read:
                with self.assertRaisesRegex(h.Refused, 'host-endpoint'):
                    h.attended_engine_facts(None, pid)
                read.assert_not_called()

    def test_fixed_argv_and_engine_only_results(self):
        commands = Mock()
        pid = '42'
        exe = '/proc/42/exe'
        responses = ['/usr/bin/dockerd\n', H+'  '+exe+'\n', '/\n', 'mnt:[12]\n', 'listener\n']
        with patch.object(h, 'system_tool', side_effect=lambda _, n: '/usr/bin/'+n), \
             patch.object(h, 'attended_read', side_effect=responses) as reader:
            self.assertEqual(h.attended_engine_facts(commands, pid), (H, '/', 'mnt:[12]', ['listener']))
        prefix = ['/usr/bin/sudo', '-k', '-u', 'root', '--']
        expected = [
            ['/usr/bin/readlink', '--', exe], ['/usr/bin/sha256sum', '--', exe],
            ['/usr/bin/readlink', '--', '/proc/42/root'],
            ['/usr/bin/readlink', '--', '/proc/42/ns/mnt'],
            ['/usr/bin/ss', '-Hxlpn', 'src', '=', '/run/docker.sock', 'or', 'src', '=', '/var/run/docker.sock'],
        ]
        self.assertEqual([c.args for c in reader.call_args_list],
                         [(prefix+args, commands.deadline, commands.wall_deadline) for args in expected])

    def test_engine_reader_failure_or_malformed_facts_refuse(self):
        expected = ['/usr/bin/dockerd\n', H+'  /proc/42/exe\n', '/\n', 'mnt:[12]\n', 'listener\n']
        for index, bad in ((0, '/tmp/proxy\n'), (1, H+'  /tmp/file\n'), (2, '/other\n'),
                           (3, ''), (4, h.Refused('host-command'))):
            values = expected.copy()
            values[index] = bad
            with self.subTest(index=index), patch.object(h, 'system_tool', return_value='fixed'), \
                 patch.object(h, 'attended_read', side_effect=values), self.assertRaises(h.Refused):
                h.attended_engine_facts(Mock(), '42')

    def test_profile_rejects_missing_privileged_tool_pin(self):
        row = profile()
        del row['binaries']['sudo']
        with self.assertRaisesRegex(h.Refused, 'host-profile'):
            h.profile(row)
        with self.assertRaisesRegex(h.Refused, 'host-cli'):
            h.system_tool({'sudo': {'path': '/tmp/sudo', 'sha256': H}}, 'sudo')

    def test_no_generic_sudo_command(self):
        with self.assertRaisesRegex(h.Refused, 'host-command'):
            h.Commands(profile()['binaries'], 0, 0).run(['sudo', '--version'])

    def test_c06_false_refuses_both_custody_returns(self):
        for post in (False, True):
            row = custody()
            row['checks']['no_codex_background_or_autostart'] = False
            with self.subTest(post=post), self.assertRaisesRegex(h.Refused, 'host-custody'):
                self.validate(row, post)

    def test_native_filesystem_excludes_windows_network_and_unknown(self):
        h.native_filesystem(dict(filesystems=[dict(fstype='ext4', source='/dev/sdb', target='/')]))
        for kind, source in (('9p', 'C:'), ('drvfs', 'C:'), ('ntfs', '/dev/sdb'),
                             ('nfs', 'server:/root'), ('ext4', 'overlay')):
            with self.subTest(kind=kind), self.assertRaisesRegex(h.Refused, 'host-native-fs'):
                h.native_filesystem(dict(filesystems=[dict(fstype=kind, source=source)]))

    def test_inspection_and_host_modes_never_import_generator_or_age(self):
        tree = ast.parse(Path(h.__file__).read_text())
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): names.extend(a.name for a in node.names)
            if isinstance(node, ast.ImportFrom): names.append(node.module or '')
        self.assertFalse(any('generate_intcalc_heldout' in n or 'age' == n for n in names))
        self.assertNotIn('PRIVATE_REFERENCE', Path(h.__file__).read_text())

    def test_fixed_refusal_codes_never_echo_exception_content(self):
        self.assertEqual(str(h.Refused('PRIVATE-PATH-AND-ACCOUNT')), 'host-fault')
        for code in h.CODES: self.assertEqual(str(h.Refused(code)), code)

    def test_public_bindings_recheck_retained_source_hashes_without_ci(self):
        with patch.dict(h.os.environ, {}, clear=True):
            row, _, suite, probes, _ = h.public_bindings()
        self.assertEqual(row['public_suite_sha256'], h.SUITE)
        self.assertEqual(row['package_library_sha256'], h.PACKAGE)
        self.assertEqual(len(suite['cases']), 16)
        self.assertEqual(len(probes), 9)

    def boundary(self):
        return dict(Image='sha256:'+H, HostConfig=dict(NetworkMode='none', ReadonlyRootfs=True,
            Privileged=False, CapDrop=['ALL'], CapAdd=[], SecurityOpt=['no-new-privileges'],
            Memory=2147483648, PidsLimit=128, LogConfig=dict(Type='none'), Devices=[],
            CgroupnsMode='private',
            Tmpfs={'/tmp': 'rw', '/work': 'rw'}), Config=dict(User='1000:1000'),
            Mounts=[dict(Type='bind', Destination=dest, Source=src, RW=rw) for dest, src, rw in
                    (('/source', 'source', False), ('/output', 'output', True),
                     ('/host-public-permit.json', 'permit', False))])

    def check_boundary(self, row):
        h.public_boundary(row, 'sha256:'+H, 'source', 'output', 'permit', '1000:1000')

    def test_public_container_boundary_requires_fixed_limits_and_no_network(self):
        self.check_boundary(self.boundary())
        for key, value in (('NetworkMode', 'host'), ('ReadonlyRootfs', False), ('Privileged', True),
                           ('CapDrop', []), ('Memory', 0), ('PidsLimit', 0),
                           ('LogConfig', {'Type': 'json-file'}), ('Devices', ['device'])):
            row = self.boundary(); row['HostConfig'][key] = value
            with self.subTest(key=key), self.assertRaises(h.Refused): self.check_boundary(row)

    def test_unreviewed_mounts_or_writable_source_refuse(self):
        for mutation in ('writable-source', 'extra-volume', 'different-source'):
            row = self.boundary()
            if mutation == 'writable-source': row['Mounts'][0]['RW'] = True
            if mutation == 'extra-volume': row['Mounts'].append(dict(Type='volume', Destination='/secret'))
            if mutation == 'different-source': row['Mounts'][0]['Source'] = 'elsewhere'
            with self.subTest(mutation=mutation), self.assertRaises(h.Refused): self.check_boundary(row)

    def test_ci_variable_is_not_an_attended_entry(self):
        with patch.dict(worker.os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True), \
             patch.object(worker.platform, 'system', return_value='Linux'), \
             patch.object(worker.platform, 'machine', return_value='x86_64'):
            with self.assertRaisesRegex(worker.Refused, 'host-public-container'):
                worker.public_container()

    def test_public_worker_permit_without_ci_environment(self):
        permit = h.canonical(dict(schema='ha-public-container/1', public_only=True, suite_sha256=h.SUITE))
        with patch.dict(worker.os.environ, {}, clear=True), \
             patch.object(worker.platform, 'system', return_value='Linux'), \
             patch.object(worker.platform, 'machine', return_value='x86_64'), \
             patch.object(worker.ref, 'bounded', return_value=permit):
            worker.public_container()

    def test_oracle_worker_classifies_only_modelled_failures(self):
        from carddemo_oracle.oracle import OracleExecutionError
        from carddemo_oracle.records import RecordError
        for error in (OracleExecutionError('synthetic'), RecordError('synthetic')):
            with patch.object(worker, 'public_container'), \
                 patch('carddemo_oracle.oracle.run_directory', side_effect=error), \
                 patch('sys.stderr'):
                self.assertEqual(worker.main(['oracle', '--input', 'synthetic-in', '--output', 'synthetic-out']), 2)
        with patch.object(worker, 'public_container'), \
             patch('carddemo_oracle.oracle.run_directory', side_effect=RuntimeError('unexpected')):
            with self.assertRaises(RuntimeError):
                worker.main(['oracle', '--input', 'synthetic-in', '--output', 'synthetic-out'])

    def test_linux_only_operations_refuse_before_platform_specific_calls(self):
        with patch.object(h.os, 'name', 'nt'):
            with self.assertRaisesRegex(h.Refused, 'host-platform'):
                h.private_directory('unused')


if __name__ == '__main__':
    unittest.main()
