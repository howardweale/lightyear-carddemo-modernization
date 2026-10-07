"""Offline regression checks for the failed r9 equipment; no Docker or models."""
import copy
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from lightyear_calibration.contracts import canonical, read_json, seal
from tools.ms94_b06_bytecode_policy import POLICY, JDWP, validate_jvm
from tools.ms94_b06_observed_worker import maven_arguments
from tools.ms94_b06_posting_broker import PostingBroker
from tools.ms94_b06_private_assembly import required, seal_inputs, verify_assembly
from tools.ms94_b06_register_inputs import register_path, validate, admit

ROOT = Path(__file__).resolve().parents[1]
DATE = '2026-10-06'


class SmokeBindingTests(unittest.TestCase):
    def setUp(self):
        self.inventory = read_json(ROOT/'docs/calibration/idempiere-boundaries/mappings.json')
        self.j1 = read_json(ROOT/register_path('J1'))
        self.purchasing = read_json(ROOT/register_path('J2'))
        self.spec = {'bytecode_policy': POLICY, 'java_binary_sha256': 'a'*64}
        self.owner = {'java_binary_sha256': 'a'*64, 'arguments': ['java', JDWP, '-jar', 'launcher.jar'],
                      'jvm_option_environment_present': []}

    def test_exact_inherited_journey_registers_validate_without_relabeling(self):
        validate('J1', self.j1, self.inventory, DATE, self.j1['content_sha256'])
        for journey in ('J2', 'J3'):
            validate(journey, self.purchasing, self.inventory, DATE, self.purchasing['content_sha256'])
        with self.assertRaisesRegex(ValueError, 'inventory/version differs'):
            validate('J1', self.purchasing, self.inventory, DATE)
        with self.assertRaisesRegex(ValueError, 'comparison-register-changed'):
            validate('J1', self.j1, self.inventory, DATE, '0'*64)

    def test_register_full_validation_rejects_expiry_inventory_and_rule_scope(self):
        with self.assertRaisesRegex(ValueError, 'not current'):
            validate('J1', self.j1, self.inventory, '2099-01-01')
        for change in ('inventory', 'scope'):
            r = copy.deepcopy(self.j1); r.pop('content_sha256')
            if change == 'inventory': r['inventory_sha256'] = '0'*64
            else: r['entries'][0]['columns'] = []
            with self.assertRaises(ValueError): validate('J1', seal(r), self.inventory, DATE)

    def test_wrong_register_refused_before_private_copy_and_again_on_readmission(self):
        files = {n: canonical(seal({'fixture': True})) for n in required('J1')}
        files['operations.java'] = b'public synthetic candidate fixture'
        files['datatype-inventory.json'] = canonical(self.inventory)
        files['comparison-register.json'] = canonical(self.purchasing)
        slot = {'id': 'slot-001', 'control': 'retained-reference',
                'source': {'sha256': hashlib.sha256(files['operations.java']).hexdigest()}}
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)/'inputs'
            with self.assertRaisesRegex(ValueError, 'inventory/version differs'):
                seal_inputs(dest, 'J1', [slot], {slot['id']: files}, assessed_on=DATE)
            self.assertFalse(dest.exists())
            files['comparison-register.json'] = canonical(self.j1)
            record = seal_inputs(dest, 'J1', [slot], {slot['id']: files}, assessed_on=DATE)
            self.assertTrue(verify_assembly(dest, record))
            # Recomputed blob/manifest hashes cannot launder the wrong register.
            bad = copy.deepcopy(record); bad.pop('content_sha256')
            raw = canonical(self.purchasing); sha = hashlib.sha256(raw).hexdigest()
            (dest/'blobs'/sha).write_bytes(raw)
            bad['slots'][slot['id']]['inputs_sha256']['comparison-register.json'] = sha
            with self.assertRaisesRegex(ValueError, 'inventory/version differs'):
                verify_assembly(dest, seal(bad))
            run = Path(tmp)/'run'; (run/'inputs').mkdir(parents=True)
            (run/'inputs/comparison-register.json').write_bytes(raw)
            (run/'inputs/datatype-inventory.json').write_bytes(canonical(self.inventory))
            with self.assertRaisesRegex(ValueError, 'inventory/version differs'):
                admit(run, {'journey': 'J1', 'assessed_on': DATE,
                            'comparison_register_sha256': self.purchasing['content_sha256']})

    def test_maven_keeps_tests_and_suspended_observer_but_disables_coverage(self):
        args = maven_arguments()
        self.assertIn('verify', args)
        self.assertIn('-DskipTests=false', args)
        self.assertIn('-Djacoco.skip=true', args)
        self.assertIn('-Dtycho.testArgLine=', args)
        self.assertIn(JDWP, next(a for a in args if a.startswith('-Dp1=')))

    def test_actual_jvm_and_offline_receipt_guard_reject_agents_not_just_jacoco(self):
        self.assertTrue(validate_jvm(self.owner, self.spec))
        for extra in ('-javaagent:/root/.m2/org.jacoco.agent-0.8.10-runtime.jar=destfile=x',
                      '-javaagent:/other.jar', '-agentpath:/transformer.so', '-Xrunother',
                      '-agentlib:other', JDWP, '@hidden-arguments'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_jvm({**self.owner, 'arguments': self.owner['arguments']+[extra]}, self.spec)
        with self.assertRaisesRegex(ValueError, 'java-changed'):
            validate_jvm({**self.owner, 'java_binary_sha256': 'b'*64}, self.spec)
        with self.assertRaisesRegex(ValueError, 'policy-missing'):
            validate_jvm(self.owner, {'java_binary_sha256': 'a'*64})
        for names in (None, ['JAVA_TOOL_OPTIONS'], ['_JAVA_OPTIONS'], ['JDK_JAVA_OPTIONS']):
            with self.assertRaisesRegex(ValueError, 'jvm-option-environment'):
                validate_jvm({**self.owner, 'jvm_option_environment_present': names}, self.spec)

    def test_live_broker_rejects_agent_before_attaching_or_releasing_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = SimpleNamespace(root=ROOT, owner='journey-'+'a'*32, run=Path(tmp),
                plan={'posting_observer': self.spec, 'content_sha256': 'b'*64,
                      'implementation_sha256': {'tools/ms94_b06_posting_listener.py': 'c'*64}},
                check_cancel=lambda: None)
            broker = PostingBroker(runner, 'oracle', 'app', None)
            owner = {**self.owner, 'arguments': self.owner['arguments']+['-javaagent:/jacoco.jar']}
            import json
            with patch('tools.ms94_b06_posting_broker.bound_file', return_value=Path(__file__)), \
                 patch('tools.ms94_b06_posting_broker.docker', return_value=SimpleNamespace(stdout=json.dumps([owner]))), \
                 patch('tools.ms94_b06_posting_broker.subprocess.Popen') as launch, \
                 patch('tools.ms94_b06_posting_broker.sign_once') as failure:
                broker._collect()
            launch.assert_not_called()
            failure.assert_called_once()
            self.assertIn('observer-unapproved-bytecode-agent', broker.failure)
            self.assertFalse(broker.ready.is_set())
            self.assertTrue(broker.done.is_set())

    def test_replay_context_requires_bound_public_files_and_exact_public_key(self):
        from lightyear_calibration.journey_order import RUNS
        from tools.ms94_b06_qualification_driver import replay_context, J1_REPLAY_CONTEXT
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source'; run=root/RUNS/'journey-fixture'; run.mkdir(parents=True)
            (run/'plan.json').write_bytes(canonical(seal({'journey':'J1'})))
            hashes={}
            for name in J1_REPLAY_CONTEXT:
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'PUBLIC KEY FIXTURE' if name.endswith('.pem') else b'public contract fixture')
                hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (root/'b06-executable-snapshot.json').write_bytes(canonical(seal({'files_sha256':hashes})))
            parent=replay_context(root,Path(tmp)/'valid',run,b'PUBLIC KEY FIXTURE')
            self.assertEqual(parent,Path(tmp)/'valid'/RUNS)
            with self.assertRaisesRegex(ValueError,'key-differs'):
                replay_context(root,Path(tmp)/'wrong-key',run,b'OTHER KEY')
            (root/J1_REPLAY_CONTEXT[0]).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'bound-file-changed'):
                replay_context(root,Path(tmp)/'tampered',run,b'PUBLIC KEY FIXTURE')

    def test_new_hash_only_assemblies_keep_candidates_and_nonregister_inputs(self):
        docs=ROOT/'docs/calibration/idempiere-ms94/stage-b-06/preparation'
        old=read_json(docs/'execution-r6/j1-private-inputs.json')
        new=read_json(docs/'smoke-bindings-r10/j1-private-inputs.json')
        self.assertEqual(set(old['slots']),set(new['slots']))
        self.assertEqual(55,len(new['slots']))
        self.assertEqual('ms94-b06-private-input-assembly/2',new['artifact_type'])
        for slot,row in old['slots'].items():
            self.assertNotEqual(row['inputs_sha256']['comparison-register.json'],
                                new['slots'][slot]['inputs_sha256']['comparison-register.json'])
            for name,sha in row['inputs_sha256'].items():
                if name!='comparison-register.json':
                    self.assertEqual(sha,new['slots'][slot]['inputs_sha256'][name])


if __name__ == '__main__': unittest.main()
