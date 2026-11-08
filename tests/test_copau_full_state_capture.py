"""Complete original N1 oracle with PUBLIC synthetic input, in CI only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from lightyear_execution import copau_full_state_contract as stage
from tools import copau_full_state as capture
from tests import test_copau_full_state_contract as fixtures


class FullStateCaptureTests(unittest.TestCase):
    def test_complete_frozen_session_and_independent_initial_state(self):
        root = Path(__file__).resolve().parents[1]
        if os.environ.get('COPAU_FULL_STATE_EXACT_SYNTHETIC') != '1':
            # Exact Git bytes on Windows as well as POSIX, never relax hash seals
            # to accommodate checkout-only CRLF. This subprocess runs ONLY in CI.
            freeze_path = 'docs/factory/copau-factory-judge-freeze-2026-10-18.json'
            amendment_path = 'docs/factory/copau-factory-judge-freeze-amendment-2026-10-20.json'
            freeze = json.loads(subprocess.check_output(['git', 'show', 'HEAD:' + freeze_path], cwd=root))
            amendment = json.loads(subprocess.check_output(['git', 'show', 'HEAD:' + amendment_path], cwd=root))
            paths = {r['path'] for r in freeze['files']} | {r['path'] for r in amendment['files']}
            roots = ['src', 'tools', 'factory/carddemo-web', 'spec/modernization/carddemo-data',
                     'spec/modernization/carddemo-screens', freeze_path, amendment_path,
                     'tests/test_copau_full_state_contract.py', 'tests/test_copau_full_state_capture.py']
            roots += sorted(p for p in paths if not any(p == r or p.startswith(r + '/') for r in roots))
            with tempfile.TemporaryDirectory(prefix='n1-public-exact-') as temp:
                target = Path(temp)
                archive = target / 'source.tar'
                with archive.open('wb') as out:
                    subprocess.run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
                                    'archive', 'HEAD', *roots], cwd=root, stdout=out, check=True)
                with tarfile.open(archive) as package:
                    package.extractall(target, filter='data')
                # Ensure the namespace tests resolves to this exact extraction.
                (target / 'tests/__init__.py').write_text('')
                env = dict(os.environ, COPAU_FULL_STATE_EXACT_SYNTHETIC='1',
                    PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=os.pathsep.join([str(target / 'src'), str(target)]))
                result = subprocess.run([sys.executable, '-B', '-m', 'unittest',
                    'tests.test_copau_full_state_capture.FullStateCaptureTests.test_complete_frozen_session_and_independent_initial_state'],
                    cwd=target, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self.assertEqual(result.returncode, 0, result.stdout)
            return
        import psycopg
        producer, _ = capture.reference.verify_producer(root)
        store = fixtures.MemoryStore()
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')), \
             patch.object(psycopg, 'connect', side_effect=AssertionError('database forbidden')), \
             patch.object(producer, 'snapshot', side_effect=AssertionError('candidate baseline forbidden')), \
             patch.object(producer.Proof, '__init__', side_effect=AssertionError('constructor forbidden')):
            with patch.object(producer, 'Engine', side_effect=AssertionError('oracle before ACK')):
                commitment = capture.prepare_inputs(store, root, bytes(range(32)), context_sha256='a' * 64)
            with self.assertRaises(stage.Refused):
                capture.capture(store, root, acknowledgment_verifier=lambda _: commitment)
            self.assertNotIn('n1-consumed.json', store.files)
            stage.acknowledge(store, b'PUBLIC CI ACK DOUBLE', verifier=lambda _: commitment)
            report = capture.capture(store, root, acknowledgment_verifier=lambda _: commitment)
        self.assertEqual(report['interactions'], 15)
        self.assertFalse(report['qualified'])
        self.assertEqual(report['status'], 'ORACLE_CAPTURE_ONLY')
        artifact = stage.decoded(stage.get_blob(store, 'n1-oracle'))
        initial = stage.decoded(stage.get_blob(store, 'n1-initial'))
        states = {s['path']: stage.decoded(stage.get_blob(store, s['blob'])) for s in artifact['states']}
        self.assertEqual(artifact['session'], stage.SESSION)
        self.assertEqual(artifact['producer_bindings'], capture.bindings())
        self.assertIn('slice_fixture_identity', initial)
        self.assertTrue(any(t.startswith('quarantine_') for t in initial))
        self.assertEqual(len(initial['pautdtl1']), 7)
        previous = producer.digest(initial)
        fraud = []
        for row in artifact['rows']:
            self.assertEqual(row['before_sha256'], previous)
            state = states[row['database_file']['path']]
            self.assertEqual(set(state), set(initial))
            previous = producer.digest(state)
            self.assertEqual(row['after_sha256'], previous)
            expected = row['expected']
            self.assertIn('commarea', expected)
            self.assertEqual(set(expected['screen']['values']), set(expected['screen']['attributes']))
            if state['authfrds']:
                fraud.append(state['authfrds'][-1]['auth_fraud'])
        self.assertIn('F', fraud)
        self.assertIn('R', fraud)
        self.assertEqual(artifact['candidate_replay'], 'NOT_RUN')
        with self.assertRaises(stage.Refused):
            capture.capture(store, root, acknowledgment_verifier=lambda _: commitment)

    def test_oracle_fault_remains_consumed_with_no_private_exception(self):
        store = fixtures.MemoryStore()
        commitment = stage.stage_inputs(store, {'public': 'synthetic'},
            context_sha256='a' * 64, producer_bindings=capture.bindings())
        stage.acknowledge(store, b'PUBLIC', verifier=lambda _: commitment)
        with patch.object(capture.reference, 'verify_producer', side_effect=RuntimeError('PRIVATE SENTINEL')):
            with self.assertRaisesRegex(stage.Refused, '^oracle-capture-failed-consumed$'):
                capture.capture(store, Path.cwd(), acknowledgment_verifier=lambda _: commitment)
        self.assertIn('n1-consumed.json', store.files)
        self.assertNotIn('n1-complete.json', store.files)
        with self.assertRaises(stage.Refused):
            capture.capture(store, Path.cwd(), acknowledgment_verifier=lambda _: commitment)

    def test_private_state_path_and_payload_digest_are_bound(self):
        root = capture._PrivateBlobs()
        raw = b'{"public":[]}'
        path = root / ('expected-database/' + stage.sha(raw) + '.json')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        self.assertEqual(path.read_bytes(), raw)
        with self.assertRaises(stage.Refused):
            path.write_bytes(raw)
        for name in ('../escape.json', 'other.json', 'expected-database/' + 'a' * 64 + '.json'):
            with self.subTest(name=name), self.assertRaises(stage.Refused):
                target = root / name
                target.write_bytes(raw)
