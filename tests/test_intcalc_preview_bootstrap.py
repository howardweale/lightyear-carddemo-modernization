"""Synthetic CI only. No real key, provider, Docker or verifier inputs."""
from datetime import datetime, timezone, timedelta
from contextlib import ExitStack, redirect_stdout
import io
import ctypes
import getpass
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from lightyear_factory import intcalc_preview_bootstrap as boot
from lightyear_factory import intcalc_preview_composition as c
from lightyear_factory import intcalc_preview_ledger_volume as v
from lightyear_factory import intcalc_preview_admission as a


class BootstrapTests(unittest.TestCase):
    def ports(self):
        packet = {'request_bound_proof_sha256': boot.PROOF_RULE_SHA256,
                  'public_context_approval_sha256': 'b' * 64}
        return boot.Ports(packet, {}, {}, 'c' * 64, {}, {}, {})

    def test_inline_bound_exact_cap_then_one_byte_refusal(self):
        ports = self.ports()
        projection = dict(model=c.MODEL, instructions=c.ROLE_INSTRUCTIONS['planner'], input='x')
        bound = len(c.canonical(projection)) + 4096
        with patch.object(boot, 'source_check'), patch.dict(c.ROLE_INPUT_CAPS, planner=bound):
            proof = ports.prove_request('planner', projection)
            self.assertEqual(proof.token_upper_bound, bound)
            projection['input'] += 'x'
            with self.assertRaises(boot.BootstrapRefused):
                self.ports().prove_request('planner', projection)

    def test_proof_wrong_role_or_instruction_refused(self):
        with patch.object(boot, 'source_check'):
            for role, instruction in (('builder-attempt1', 'x'), ('planner', 'x')):
                with self.assertRaises(boot.BootstrapRefused):
                    self.ports().prove_request(role, dict(model=c.MODEL, instructions=instruction))

    def test_hidden_prompt_no_echo_fallback(self):
        with patch.object(boot.sys.stdin, 'isatty', return_value=True), \
                patch.object(boot.getpass, 'getpass', side_effect=getpass.GetPassWarning('synthetic')):
            with self.assertRaises(getpass.GetPassWarning):
                boot.hidden_api_key()

    def test_hidden_prompt_non_tty_refused_before_read(self):
        with patch.object(boot.sys.stdin, 'isatty', return_value=False), patch.object(boot.getpass, 'getpass') as prompt:
            with self.assertRaises(boot.BootstrapRefused):
                boot.hidden_api_key()
            prompt.assert_not_called()

    def test_hidden_prompt_uses_only_returned_synthetic_value(self):
        with patch.object(boot.sys.stdin, 'isatty', return_value=True), patch.object(boot.getpass, 'getpass', return_value='synthetic-sentinel'):
            self.assertEqual(boot.hidden_api_key(), 'synthetic-sentinel')

    def test_ephemeral_envelope_synthetic_hmac(self):
        import hashlib, hmac
        value = boot.ephemeral_envelope({'synthetic': True}, 'synthetic', b'x' * 32)
        unsigned = {k: v for k, v in value.items() if k != 'signature'}
        expected = hmac.new(b'x' * 32, a.DOMAIN + a._canonical(unsigned), hashlib.sha256).hexdigest()
        self.assertEqual(value['signature']['value'], expected)
        self.assertNotIn('key', value)

    def test_non_mac_refused_before_any_effect(self):
        with patch.object(boot.sys, 'platform', 'linux'):
            with self.assertRaises(boot.BootstrapRefused):
                boot.native()

    def disk_fixture(self, available=None, age=600, window=1800):
        available = v.MIN_FREE if available is None else available
        observed = datetime.now(timezone.utc) - timedelta(seconds=age)
        raw = ('Filesystem 1024-blocks Used Available Capacity Mounted on\n'
               'overlay 99999999 100 ' + str(available // 1024) + ' 1% /\n').encode()
        receipt = dict(schema='full-intcalc-docker-headroom/1', observed_at=observed.isoformat(),
            endpoint_sha256=c.digest(b'unix:///synthetic'), image_manifest_sha256=boot.b.JRE,
            method='pinned-readonly-container-df-P-k-root', df_stdout=raw.decode(),
            df_stdout_sha256=c.digest(raw), available_bytes=available, cleanup_confirmed=True)
        approval = dict(issued_at=(observed + timedelta(seconds=1)).isoformat(),
                        expires_at=(observed + timedelta(seconds=window)).isoformat())
        return receipt, approval

    def check_disk(self, receipt, approval):
        raw = c.canonical(receipt)
        with patch.object(boot, 'host_disk_check') as host, patch.object(boot.b, 'read_file', return_value=raw):
            boot.disk_check(dict(endpoint='unix:///synthetic', disk_receipt_path='synthetic'),
                            dict(disk_receipt_sha256=c.digest(raw)), approval)
            host.assert_called_once()

    def test_disk_receipt_can_survive_review_within_fixed_window(self):
        self.check_disk(*self.disk_fixture(age=600))  # no obsolete 60-second cutoff

    def test_expired_or_extended_disk_window_refuses(self):
        for age, window in ((1900, 1800), (600, 1801), (-10, 1800)):
            with self.subTest(age=age, window=window), self.assertRaises(boot.BootstrapRefused):
                self.check_disk(*self.disk_fixture(age=age, window=window))

    def test_small_or_operator_changed_docker_headroom_refuses(self):
        with self.assertRaises(boot.BootstrapRefused):
            self.check_disk(*self.disk_fixture(available=v.MIN_FREE - 1024))
        receipt, approval = self.disk_fixture()
        receipt['available_bytes'] += 1024
        with self.assertRaises(boot.BootstrapRefused):
            self.check_disk(receipt, approval)

    def test_df_refuses_extra_mount_or_malformed_count(self):
        for raw in (b'header\noverlay 100 0 nope 0% /\n', b'header\noverlay 100 0 100 0% /\nother\n'):
            with self.assertRaises(boot.BootstrapRefused):
                boot.parse_df(raw)

    def test_close_drops_secret_and_closes_volume(self):
        ports = self.ports()
        ports.key = 'synthetic'
        ports.transport_instance = SimpleNamespace(_key='synthetic')
        ports.ledger, ports.lease = Mock(), Mock()
        ports.close()
        ports.close()
        self.assertIsNone(ports.key)
        self.assertIsNone(ports.transport_instance._key)
        ports.ledger.close.assert_called_once()
        ports.lease.close.assert_called_once()

    def test_artifact_c0_and_caps(self):
        schema = {'properties': {'text': {'type': 'string'}}, 'required': ['text'], 'additionalProperties': False}
        self.assertTrue(boot.artifact_valid({'text': 'plain'}, schema))
        for text in ('x\x00', 'x' * 8193):
            with self.assertRaises(boot.BootstrapRefused):
                boot.artifact_valid({'text': text}, schema)

    def test_rehearsal_mode_rejects_live_before_io(self):
        with patch.object(boot, 'native'), patch.object(boot, 'hidden_api_key') as prompt, patch.object(boot.t, 'PreviewTransport') as transport:
            with self.assertRaises(boot.BootstrapRefused):
                boot.rehearse({}, {'mode': 'LIVE'}, 'a' * 64, {}, {})
            prompt.assert_not_called()
            transport.assert_not_called()


class PreflightTests(unittest.TestCase):
    def intent(self):
        value = {k: 'a' * 64 for k in boot.REHEARSAL_HASHES}
        value.update(schema='full-intcalc-rehearsal-intent/1', runtime_platform='linux/arm64',
            byte_policy_sha256='STRICT', prerequisites={k: dict(status='PRESENT', evidence_sha256='b' * 64)
                                                      for k in boot.REHEARSAL_REQUIRED})
        value.update(runtime_manifest_sha256=boot.b.JRE, runtime_config_sha256=boot.b.JRE_CONFIG,
            toolchain_manifest_sha256=boot.b.JDK, javac_sha256=boot.b.JAVAC, jar_sha256=boot.b.JAR_TOOL)
        return value

    def test_rehearsal_minimal_set_excludes_live_and_own_results(self):
        intent = self.intent()
        self.assertTrue(c.is_hash(boot.validate_intent(intent, 'REHEARSAL')))
        packet = boot.rehearsal_packet(intent, 'c' * 64)
        self.assertTrue(all(row['status'] == 'MISSING' for row in packet['prerequisites'].values()))
        self.assertNotIn('count_billing', intent['prerequisites'])
        self.assertNotIn('trusted_build_gate_adapter', intent['prerequisites'])
        self.assertNotIn('request_bound_proof', intent['prerequisites'])
        self.assertNotIn('public_context_review', intent['prerequisites'])
        with self.assertRaises(boot.BootstrapRefused):
            boot.validate_intent(intent, 'LIVE')

    def test_rehearsal_still_requires_all_six_prior_evidence_rows(self):
        for name in boot.REHEARSAL_REQUIRED:
            intent = self.intent()
            del intent['prerequisites'][name]
            with self.assertRaises(boot.BootstrapRefused):
                boot.validate_intent(intent, 'REHEARSAL')

    def test_live_binding_retains_exact_admission_window(self):
        packet = boot.rehearsal_packet(self.intent(), 'c' * 64)
        packet['prerequisites'] = {k: dict(status='PRESENT', evidence_sha256='d' * 64) for k in c.PREREQUISITES}
        intent = boot.intent_for(packet)
        issued = datetime.now(timezone.utc)
        binding = boot.bindings_for(intent, {}, issued_at=issued.isoformat(), nonce='e' * 64,
            admission_expires_at=(issued + timedelta(seconds=1800)).isoformat())
        self.assertEqual(a._timestamp(binding['admission_expires_at']) - a._timestamp(binding['issued_at']), timedelta(seconds=1800))

    def test_zero_spend_approval_has_no_billing_hash(self):
        intent = self.intent()
        now = datetime.now(timezone.utc)
        approval = dict(schema='full-intcalc-attended-approval/2', mode='REHEARSAL',
            intent_sha256=c.digest(c.canonical(intent)), scope=boot.SCOPE, cap_microdollars=0,
            count_billing_known=False, account_billing_evidence_sha256=None,
            issued_at=now.isoformat(), expires_at=(now + timedelta(seconds=1700)).isoformat(),
            qualified=False, production_controller_receipt=False,
            local_config_sha256='d' * 64, qualification_sha256='e' * 64)
        self.assertEqual(boot.approval_record(intent, approval, c.digest(c.canonical(approval)), now),
                         c.digest(c.canonical(intent)))
        approval['count_billing_known'] = True
        with self.assertRaises(boot.BootstrapRefused):
            boot.approval_record(intent, approval, c.digest(c.canonical(approval)), now)

    def test_preflight_repeat_checks_without_writes_keys_or_consumption(self):
        # Read-only checks execute repeatedly, with only platform observations mocked.
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            marker = Path(tmp) / 'retained'
            marker.write_bytes(b'unchanged')
            intent = self.intent()
            binding = c.canonical(dict(case_manifest={'sha256': intent['case_manifest_sha256']}, runtime_platform='linux/arm64'))
            config = dict(verifier_binding='binding', verifier_binding_sha256=c.digest(binding),
                source_root=tmp, gate_source_sha256=c.digest(b'gate'), public_fixture_path='fixture',
                public_fixture_sha256=c.digest(b'public'), build_parent=tmp)
            checks = [stack.enter_context(patch.object(boot, name)) for name in
                ('native', 'approval_record', 'qualify_record', 'source_check', 'local_images', 'disk_check')]
            stack.enter_context(patch.dict('sys.modules', fcntl=SimpleNamespace(F_FULLFSYNC=51)))
            def read(path, cap):
                text = str(path)
                return binding if text == 'binding' else b'gate' if text.endswith('intcalc_candidate_gate.py') else b'public'
            stack.enter_context(patch.object(boot.b, 'read_file', side_effect=read))
            forbidden = [stack.enter_context(patch.object(obj, name, side_effect=AssertionError('effect forbidden')))
                for obj, name in ((boot, 'hidden_api_key'), (boot, 'volume_preflight'),
                    (boot.secrets, 'token_bytes'), (boot.secrets, 'token_hex'), (boot.b, 'exclusive'),
                    (boot.a, 'admit_preview'), (boot.t, 'PreviewTransport'), (Path, 'mkdir'))]
            before = [(p.name, p.read_bytes()) for p in Path(tmp).iterdir()]
            for _ in range(2):
                self.assertEqual(boot.read_only_checks(intent, {'mode': 'REHEARSAL'}, 'c' * 64, config, {}),
                                 'preflight-ready-write-probe-pending')
            self.assertEqual(before, [(p.name, p.read_bytes()) for p in Path(tmp).iterdir()])
            for check in checks:
                self.assertEqual(check.call_count, 2)
            for effect in forbidden:
                effect.assert_not_called()

    def test_local_images_uses_fixed_empty_config_prefix(self):
        prefix = ['docker', '--config', 'empty', '--host', 'unix:///synthetic']
        ids = dict(jre='sha256:' + boot.b.JRE, jdk='sha256:' + boot.b.JDK)
        results = [dict(rc=0, stdout=b'{"os":"linux","architecture":"aarch64"}')]
        for key, digest in (('jre', boot.b.JRE), ('jdk', boot.b.JDK)):
            results.append(dict(rc=0, stdout=c.canonical([dict(Os='linux', Architecture='arm64',
                Id=ids[key], RepoDigests=['docker.io/library/eclipse-temurin@sha256:' + digest])])) )
        with patch.object(boot, 'docker_prefix', return_value=prefix), patch.object(boot.b, 'capture', side_effect=results) as call:
            boot.local_images({}, dict(image_ids=ids))
            for args in call.call_args_list:
                self.assertEqual(args.args[0][:5], prefix)
                self.assertNotIn('create', args.args[0])

    def test_cli_refusals_are_codes_only_before_any_secret(self):
        args = ['--intent', 'i', '--approval', 'a', '--config', 'c', '--qualification', 'q', '--approval-sha256', 'a' * 64]
        for mode in ('preflight', 'run', 'rehearse'):
            out = io.StringIO()
            with (patch.object(boot, 'native'), patch.object(boot, 'read_json', side_effect=OSError('private value')),
                    redirect_stdout(out), patch.object(boot, 'hidden_api_key') as prompt):
                self.assertEqual(boot.main([mode, *args]), 2)
            self.assertEqual(out.getvalue(), 'io-refused\n')
            prompt.assert_not_called()

    def test_known_refusal_survives_and_unknown_text_does_not(self):
        self.assertEqual(boot.refusal_code(boot.BootstrapRefused('docker-disk-headroom')), 'docker-disk-headroom')
        self.assertEqual(boot.refusal_code(boot.BootstrapRefused('private value')), 'preflight-refused')

    def test_pre_admission_code_survives_composition_error_wrapper(self):
        ports = boot.Ports({}, {}, {}, 'a' * 64, {}, {}, {})
        def stopped():
            try:
                ports.admit({})
            except boot.BootstrapRefused:
                raise c.CompositionRefused('composition-stopped-no-resume') from None
        with (patch.object(boot, 'native'), patch.object(ports, '_admit', side_effect=boot.BootstrapRefused('docker-disk-headroom')),
              patch.object(c, 'Composition') as factory):
            factory.return_value.run.side_effect = stopped
            with self.assertRaisesRegex(boot.BootstrapRefused, '^docker-disk-headroom$'):
                boot.run_session({}, b'', b'', ports)
        self.assertTrue(ports.closed)

    def test_controller_disk_observation_derives_value_and_confirms_removal(self):
        raw = b'Filesystem 1024-blocks Used Available Capacity Mounted on\noverlay 50000000 100 30000000 1% /\n'
        for failed in (False, True):
            with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                config = dict(build_parent=tmp, disk_receipt_path=str(Path(tmp) / 'disk.json'), endpoint='unix:///synthetic')
                prefix = ['docker', '--config', 'empty', '--host', config['endpoint']]
                stack.enter_context(patch.object(boot, 'native'))
                stack.enter_context(patch.object(boot, 'host_disk_check'))
                stack.enter_context(patch.object(boot, 'docker_prefix', return_value=prefix))
                stack.enter_context(patch.object(boot.b, 'safe_path', side_effect=lambda p, **kw: Path(p)))
                registry = stack.enter_context(patch.object(boot.b, 'Registry')).return_value
                capture = stack.enter_context(patch.object(boot.b, 'capture', side_effect=[
                    dict(rc=0, stdout=b'[{"Os":"linux","Architecture":"arm64"}]'),
                    dict(rc=0, stdout=b'{"os":"linux","architecture":"arm64"}'),
                    dict(rc=0, stdout=b'container'), dict(rc=1 if failed else 0, stdout=raw, stderr=b'')]))
                cleanup = stack.enter_context(patch.object(boot.b, 'cleanup', return_value=[{'absence_confirmed': True}]))
                write = stack.enter_context(patch.object(boot.b, 'exclusive'))
                if failed:
                    with self.assertRaises(boot.BootstrapRefused):
                        boot.observe_disk(config)
                    write.assert_not_called()
                else:
                    boot.observe_disk(config)
                    receipt = c.strict_json(write.call_args.args[1])
                    self.assertEqual(receipt['available_bytes'], 30000000 * 1024)
                    self.assertEqual(receipt['df_stdout_sha256'], c.digest(raw))
                    self.assertTrue(receipt['cleanup_confirmed'])
                cleanup.assert_called_once()
                registry.register.assert_called_once()
                argv = capture.call_args_list[2].args[0]
                self.assertEqual(argv[:5], prefix)
                for flag in ('--pull=never', '--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges'):
                    self.assertIn(flag, argv)
                self.assertEqual(argv[-3:], ['-P', '-k', '/'])


class VolumeTests(unittest.TestCase):
    def test_native_refusal_before_fcntl_or_posix_flags(self):
        with patch.object(v.os, 'name', 'nt'):
            with self.assertRaises(v.VolumeRefused):
                v.full_sync(-1, 'file')
            with self.assertRaises(v.VolumeRefused):
                v.open_parent('.')

    def test_statfs_layout(self):
        self.assertEqual(ctypes.sizeof(v.StatFS64), 2168)
        self.assertEqual(v.StatFS64.flags.offset, 64)

    def test_filesystem_negatives(self):
        good = dict(filesystem='apfs', fsid=[1, 2], flags=0x1000, available_bytes=v.MIN_FREE)
        v.validate_filesystem(good)
        for key, value in (('filesystem', 'nfs'), ('flags', 0), ('flags', 0x1001),
                           ('flags', 0x1200), ('available_bytes', v.MIN_FREE - 1)):
            with self.subTest(key=key, value=value), self.assertRaises(v.VolumeRefused):
                v.validate_filesystem({**good, key: value})

    def test_fullsync_error_preserves_file_kind_errno(self):
        if os.name != 'posix':
            with self.assertRaises(v.VolumeRefused):
                v.full_sync(-1, 'directory')
            return
        import fcntl
        with patch.object(v, 'native'), patch.object(fcntl, 'F_FULLFSYNC', 51, create=True), \
                patch.object(fcntl, 'fcntl', side_effect=OSError(22, 'synthetic private text')):
            with self.assertRaises(v.VolumeRefused) as caught:
                v.full_sync(-1, 'directory')
            self.assertEqual(caught.exception.public_record()['errno'], 22)
            self.assertEqual(caught.exception.public_record()['file_kind'], 'directory')
            self.assertNotIn('private', str(caught.exception.public_record()))

    def test_probe_exclusive_readback_retained(self):
        if os.name != 'posix':
            with self.assertRaises(v.VolumeRefused):
                v.open_parent('.')
            return
        with tempfile.TemporaryDirectory() as temp, patch.object(v, 'full_sync') as sync:
            fd = os.open(Path(temp).resolve(), os.O_RDONLY | os.O_DIRECTORY)
            try:
                receipt = v.probe_directory(fd, 'a' * 64)
                self.assertTrue(receipt['exclusive_create'])
                self.assertEqual(sync.call_count, 2)
                with self.assertRaises(v.VolumeRefused):
                    v.probe_directory(fd, 'a' * 64)
                self.assertEqual(len(list(Path(temp).iterdir())), 1)
            finally:
                os.close(fd)
