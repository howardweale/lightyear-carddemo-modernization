"""Synthetic contracts only. No host, Docker, JVM, candidate or reference execution."""
import copy
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from lightyear_factory import public_repair_controller as c
from tools import intcalc_native_candidate_runtime as n


def archive(major=65, manifest=None, extra=None):
    mem = BytesIO()
    with ZipFile(mem, 'w') as jar:
        jar.writestr('META-INF/MANIFEST.MF', manifest or 'Manifest-Version: 1.0\r\nMain-Class: Main\r\n\r\n')
        jar.writestr('Main.class', b'\xca\xfe\xba\xbe\0\0' + major.to_bytes(2, 'big'))
        if extra:
            jar.writestr(extra, b'x')
    return mem.getvalue()


def image_data():
    conf = c.canonical(dict(os='linux', architecture='amd64', config={'Env': ['JAVA_VERSION=jdk-21.0.8+1']}))
    manifest = c.canonical(dict(schemaVersion=2, mediaType='application/vnd.oci.image.manifest.v1+json',
                                config={'digest': 'sha256:' + c.sha(conf), 'size': len(conf)}))
    license_bytes = b'unit-test only'
    row = dict(schema='native-candidate-binding/1', platform='linux/amd64', repository=n.REPOSITORY,
               manifest_sha256=c.sha(manifest), config_sha256=c.sha(conf), java_sha256='a'*64,
               java_version_stderr_sha256='b'*64, docker_cli_sha256='c'*64,
               host_profile_sha256='d'*64, licence_inventory_sha256=c.sha(license_bytes))
    return row, manifest, conf, license_bytes


def image():
    row, manifest, conf, licences = image_data()
    raw = c.canonical(row)
    return n.reviewed_image(raw, c.sha(raw), manifest, conf, licences)


def sample(files=True):
    observation = dict(exit=0, timed_out=False, output_capped=False, stdout=b'o', stderr=b'',
                       ACCTFILE=b'A', TRANSACT=b'')
    case = dict(inputs={}, expected={k: v for k, v in observation.items()
                if k not in ('timed_out', 'output_capped') and (files or k not in n.p5.OUTPUTS)},
                compare_output_files=files, timestamp='unused', processing_date='unused')
    return observation, case


def stage():
    jar = archive()
    binding = dict(runtime_profile_sha256='1'*64, worker_source_sha256='2'*64,
                   heldout_commitment_sha256='3'*64, public_answer_key_sha256=n.KEY_HASH)
    closure = dict(schema='staged-model-closure/1', binding_sha256=c.digest(binding),
                   model_ports_closed=True, further_model_calls_allowed=False)
    closing_hash = c.sha(c.canonical(closure) + b'\n')
    selected = dict(artifact_sha256='4'*64, build_receipt_sha256='5'*64,
                    public_receipt_sha256='6'*64, match=16, different=0)
    descriptor = dict(schema='retained-selected-jar/1', source_sha256=selected['artifact_sha256'],
                      binding_sha256=c.digest(binding), jar_sha256=c.sha(jar), jar_bytes=len(jar),
                      retained_leaf=n.s1.LEAF, readback_sha256=c.sha(jar),
                      closure_record_sha256=closing_hash)
    for k in ('runtime_profile_sha256', 'worker_source_sha256', 'heldout_commitment_sha256'):
        descriptor[k] = binding[k]
    for k in ('build_receipt_sha256', 'public_receipt_sha256'):
        descriptor[k] = selected[k]
    result = dict(schema='staged-public-result/1', mode='STAGED_PUBLIC',
                  status='PUBLIC_COMPLETE_HIDDEN_PENDING', selected=selected, retained_jar=descriptor,
                  public_answer_key_sha256=n.KEY_HASH, binding_sha256=c.digest(binding),
                  pre_run_commitment_sha256=binding['heldout_commitment_sha256'], closure_record_sha256=closing_hash,
                  hidden_execution_authorized=False, hidden=dict(status='PENDING',
                  reason='separate-human-verifier', selected_jar_sha256=c.sha(jar)))
    prof = image()
    proof = c.canonical(dict(schema='native-candidate-public-check/1', runtime_binding_sha256=prof.digest,
                        host_profile_sha256=prof.host_profile, answer_key_manifest_sha256=n.KEY_HASH,
                        public_cases_matched=16, public_cases_with_parity=16, adversarial_probes_passed=3,
                        private_execution_authorized=False, fixtures_sha256='8'*64, arm64_observations_sha256='9'*64,
                        limits=list(n.LIMITS)))
    return [None, prof, jar, result, binding, closure, proof, c.sha(proof)]


class NativeProfileTests(unittest.TestCase):
    def test_manifest_is_joined_to_config(self):
        self.assertTrue(image().ref.startswith('docker.io/library/eclipse-temurin@sha256:'))

    def test_wrong_manifest_config_licence_or_approval_refuses(self):
        row, manifest, conf, licences = image_data()
        raw = c.canonical(row)
        good = [raw, c.sha(raw), manifest, conf, licences]
        for i in range(5):
            args = list(good)
            args[i] += 'a' if i == 1 else b' '
            with self.subTest(i=i), self.assertRaises(n.Refused):
                n.reviewed_image(*args)

    def test_arm64_index_and_credential_env_refused(self):
        row, manifest, conf, licences = image_data()
        for arch, extra_env, make_index in [('arm64', None, False), ('amd64', 'TOKEN=fake', False),
                                            ('amd64', None, True)]:
            config = n.s1.strict(conf)
            config['architecture'] = arch
            if extra_env:
                config['config']['Env'].append(extra_env)
            cfg = c.canonical(config)
            desc = n.s1.strict(manifest)
            desc['config'].update(digest='sha256:' + c.sha(cfg), size=len(cfg))
            if make_index:
                desc['manifests'] = []
            data = c.canonical(desc)
            raw = c.canonical(dict(row, config_sha256=c.sha(cfg), manifest_sha256=c.sha(data)))
            with self.subTest(arch=arch, env=extra_env, index=make_index), self.assertRaises(n.Refused):
                n.reviewed_image(raw, c.sha(raw), data, cfg, licences)

    def test_java21_headers_only(self):
        n.classpath(archive())
        with self.assertRaisesRegex(n.Refused, 'runtime-class-version'):
            n.classpath(archive(66))

    def test_classpath_escape_and_manifest_agent_refused(self):
        for args in [dict(extra='../Other.class'), dict(extra='META-INF/versions/21/M.class'),
                     dict(extra='lib/x.jar'), dict(manifest='Manifest-Version: 1.0\nMain-Class: Main\nClass-Path: /x')]:
            with self.subTest(args=args), self.assertRaises(n.Refused):
                n.classpath(archive(**args))

    def test_retained_descriptor_and_exact_jar(self):
        args = stage()
        with patch.object(n, '_Runtime') as create:
            self.assertIs(n.retained_runtime(*args), create.return_value)
            create.assert_called_once_with(*args[:3])

    def test_changed_jar_closure_public_score_and_commitment_refused(self):
        for index in range(5):
            args = stage()
            if index == 0:
                args[2] += b'x'
            elif index == 1:
                args[5]['model_ports_closed'] = False
            elif index == 2:
                args[3]['selected']['different'] = 1
            elif index == 3:
                args[3]['pre_run_commitment_sha256'] = '7'*64
            else:
                args[3]['retained_jar']['public_receipt_sha256'] = 'a'*64
            with self.subTest(index=index), patch.object(n, '_Runtime') as create:
                with self.assertRaises((n.Refused, c.Refused)):
                    n.retained_runtime(*args)
                create.assert_not_called()

    def test_public_qualification_digest_required(self):
        args = stage()
        args[-1] = 'b'*64
        with self.assertRaisesRegex(n.Refused, 'runtime-qualification'):
            n.retained_runtime(*args)

    def test_fixed_flags_no_extra_mount(self):
        self.assertIn('--platform=linux/amd64', n.ISOLATION)
        for flag in ('--network=none', '--read-only', '--pull=never', '--runtime=runc',
                     '--memory=512m', '--cpus=1', '--pids-limit=64', '--log-driver=none'):
            self.assertIn(flag, n.ISOLATION)
        self.assertFalse(any('privileged' in f for f in n.ISOLATION))

    def test_container_readback_checks_hidden_mount_and_namespace(self):
        prof = image()
        mounts = {'/output': ('volume-a', True, 'volume')}
        state = dict(Image='sha256:' + prof.config, Config=dict(Image=prof.ref, Healthcheck={'Test': ['NONE']},
                     User='65534:65534', Cmd=['infinity'], Entrypoint=['/bin/sleep'], Env=list(prof.environment)),
                     HostConfig=dict(NetworkMode='none', ReadonlyRootfs=True, PidsLimit=64, Memory=512*1024*1024,
                     NanoCpus=1000000000, CapDrop=['ALL'], SecurityOpt=['no-new-privileges'],
                     LogConfig={'Type': 'none'}, Runtime='runc', IpcMode='private', CgroupnsMode='private'),
                     Mounts=[dict(Destination='/output', Type='volume', RW=True, Name='volume-a')])
        n.boundary(state, prof, mounts, '/bin/sleep', ['infinity'])
        for field in ('mount', 'env', 'pid', 'devices', 'entry'):
            bad = copy.deepcopy(state)
            if field == 'mount':
                bad['Mounts'].append(dict(Destination='/answers', Type='tmpfs'))
            elif field == 'env':
                bad['Config']['Env'].append('SECRET=fake')
            elif field == 'pid':
                bad['HostConfig']['PidMode'] = 'host'
            elif field == 'devices':
                bad['HostConfig']['DeviceRequests'] = ['gpu']
            else:
                bad['Config']['Entrypoint'] = ['other']
            with self.subTest(field=field), self.assertRaises((n.Refused, n.p5.Refused)):
                n.boundary(bad, prof, mounts, '/bin/sleep', ['infinity'])

    def test_memory_volume_inspect_is_mandatory(self):
        docker = n.NativeDocker([], Path('.'), 10, 15, image())
        with patch.object(n.p5.Docker, 'volume') as created, patch.object(docker, 'ok', return_value=b'[]'):
            with self.assertRaisesRegex(n.Refused, 'runtime-volume'):
                docker.volume('unused', '16m')
            created.assert_called_once()

    def test_missing_empty_and_abend_scope(self):
        obs, _ = sample()
        actual = n.compared(obs, True)
        missing = n.compared(dict(obs, TRANSACT=None), True)
        self.assertNotEqual(actual, missing)
        self.assertEqual(n.compared(obs, False), n.compared(dict(obs, TRANSACT=None), False))

    def test_public_fixture_parity_and_adversarial_contract(self):
        self.public_run()

    def test_known_imperfect_fixture_must_match_recorded_arm64_output(self):
        with self.assertRaisesRegex(n.Refused, 'runtime-parity'):
            self.public_run(mismatch=True)

    def public_run(self, mismatch=False):
        jars = {name: archive(major=65-i) for i, name in enumerate(n.FIXTURES)}
        cases = [sample(files=k not in (9, 10, 11))[1] for k in range(16)]
        obs, _ = sample()
        imperfect = dict(obs, stdout=b'imperfect')
        parity = {k: n.compared(imperfect, v['compare_output_files']) for k, v in zip(n.key.CASE_IDS, cases)}
        if mismatch:
            parity['PC-07']['stdout'] = '9'*64
        data = c.canonical(dict(schema='arm64-public-parity/1', jar_sha256=c.sha(jars['imperfect']), cases=parity))
        cat = c.canonical(dict(schema='native-public-fixture-catalog/1', answer_key_sha256=n.KEY_HASH,
                  arm64_observations_sha256=c.sha(data), fixtures={k: dict(jar_sha256=c.sha(v),
                  arm64_build_receipt_sha256='1'*64) for k, v in jars.items()}))
        rows = [obs, imperfect, dict(obs, timed_out=True), dict(obs, output_capped=True),
                dict(obs, stdout=b'boundary-probe-passed\n')]
        runtimes = [Mock(run_case=Mock(return_value=x)) for x in rows]
        with patch.object(n, '_Runtime', side_effect=runtimes), patch.object(n.key, 'load',
                return_value=(cases, {'manifest_sha256': n.KEY_HASH})):
            result = n.public_check(Mock(), image(), jars, cat, c.sha(cat), data, None, None,
                                    Mock(manifest_sha256=n.KEY_HASH))
        self.assertEqual([r.run_case.call_count for r in runtimes], [16, 16, 1, 1, 1])
        self.assertEqual(result['adversarial_probes_passed'], 3)
        self.assertFalse(result['private_execution_authorized'])

    def test_container_sequence_and_case_mounts(self):
        docker = n.NativeDocker([], Path('.'), 1, 2, image())
        events = []
        docker.preflight_image = lambda: events.append('image')
        docker.volume = lambda *args: events.append('volume')
        docker.collector = lambda *args: events.append('collector') or 'reader'
        docker.verify_jre = lambda *args: events.append('java')
        docker.create = Mock(side_effect=lambda *args: events.append('create'))
        docker.inspect = Mock(return_value={'State': {'Running': False, 'Error': '', 'StartedAt': 't', 'ExitCode': 0}})
        def call(args, *caps, **kwargs):
            events.append(args[0])
            return dict(rc=0, timed_out=False, output_capped=False, stdout=b'', stderr=b'')
        docker.call = call
        docker.prefix_copy = Mock(return_value=(b'', False))
        result = docker.observe_case(Path('kept.jar'), Path('input'), '2026-01-01-00.00.00.000000', '2026010100')
        self.assertEqual(events[:6], ['image', 'volume', 'collector', 'java', 'create', 'start'])
        _, _, mounts, entry, argv = docker.create.call_args.args
        self.assertEqual(set(mounts), {'/candidate.jar', '/output'} |
                         {'/input/' + k + '.bin' for k in n.p5.INPUTS})
        self.assertTrue(all(not row[1] for k, row in mounts.items() if k != '/output'))
        self.assertEqual(entry, n.JAVA)
        self.assertIn('-Xmx256m', argv)
        self.assertEqual(result['TRANSACT'], b'')

    def test_cleanup_on_failure_and_cleanup_failure_is_terminal(self):
        runtime = object.__new__(n._Runtime)
        runtime.jar = Path('candidate.jar')
        runtime.jar_sha = c.sha(b'fake')
        inputs = {k: b'' for k in n.p5.INPUTS}
        first, second = Mock(), Mock()
        first.observe_case.side_effect = n.Refused('runtime-java')
        runtime._docker = Mock(side_effect=[first, second])
        with patch.object(n.p5, 'read', return_value=b'fake'), patch.object(n.p5, 'exclusive'), \
                patch.object(n, 'case_deadlines', return_value=(100, 105)), self.assertRaisesRegex(n.Refused, 'runtime-java'):
            runtime._case(inputs, Path('unused'), Path('ram'), 'stamp', 'date', 500)
        second.cleanup.assert_called_once()
        first.observe_case.side_effect = None
        runtime._docker.side_effect = [first, second]
        second.cleanup.side_effect = n.Refused('runtime-cleanup')
        with patch.object(n.p5, 'read', return_value=b'fake'), patch.object(n.p5, 'exclusive'), \
                patch.object(n, 'case_deadlines', return_value=(100, 105)), self.assertRaisesRegex(n.Refused, 'runtime-cleanup'):
            runtime._case(inputs, Path('unused'), Path('ram'), 'stamp', 'date', 500)
