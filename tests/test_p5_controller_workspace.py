"""Real controller read-window mutation and independently retained refusal evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_factory.contracts import ContractError, canonical_hash
from tools.ci import p5_drills as drills
from tools.ci import p5_controller_workspace as probe
from tools.ci.p5_workspace_evidence import validate


class ControllerWorkspaceTests(unittest.TestCase):
    def test_real_read_window_mutation_retains_refusal_and_accounting(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        retained = []
        with tempfile.TemporaryDirectory(prefix='p5-workspace-ci-') as temp:
            for case in probe.CASES:
                row = probe.observe_case(Path(temp)/case, Path(__file__).resolve().parents[1], case)
                retained.append(row)
                self.assertEqual(row['transport_roles'], ['planner', 'builder'] if case == 'clean' else ['planner'])
                self.assertIs(row['controller_refused'], case != 'clean')
                directory = Path(temp)/case/'runs'/row['run_id']
                payload = row['clean_control'] if case == 'clean' else row
                for kind, filename in (('receipt', 'receipt.json'), ('identity', 'attempt-identity.json')):
                    self.assertEqual(payload[kind+'_utf8'].encode(), (directory/filename).read_bytes())
                if case != 'clean':
                    self.assertEqual(row['ledger_utf8'].encode(), (directory/'events.jsonl').read_bytes())
                    self.assertEqual(row['boundaries'][-1], dict(surface='builder-workspace', outcome='workspace-isolation-refused'))
                    self.assertEqual(len(row['injections']), 1)
        for row in retained:
            args = dict(case=row['case'], work_order_sha256=row['work_order_sha256'])
            self.assertTrue(validate(row, **args))
            for mutation in ('calls', 'role', 'boundary', 'source', 'read', 'injection'):
                bad = copy.deepcopy(row)
                if mutation == 'calls': bad['transport_calls'] += 1
                elif mutation == 'role': bad['transport_roles'][0] = 'builder'
                elif mutation == 'boundary': bad['boundaries'][1]['outcome'] = 'wrong-reason'
                elif mutation == 'source': bad['source_after_sha256'] = '0'*64
                elif mutation == 'read': bad['reads'] = []
                elif row['case'] == 'clean': bad['injections'] = [{}]
                else: bad['injections'] = []
                with self.subTest(case=row['case'], mutation=mutation), self.assertRaises(ValueError):
                    validate(bad, **args)
            if row['case'] == 'clean': continue
            for kind in ('receipt', 'identity', 'ledger', 'calls'):
                bad = copy.deepcopy(row); bad[kind+'_utf8'] += ' '
                with self.subTest(bytes=kind), self.assertRaises(ValueError): validate(bad, **args)
            for mutation in ('qualification', 'status', 'reason', 'tokens', 'billing', 'identity-run', 'call-sequence', 'ledger-chain'):
                bad = copy.deepcopy(row)
                kind = 'identity' if mutation == 'identity-run' else 'receipt'
                if mutation == 'call-sequence':
                    calls = json.loads(bad['calls_utf8']); calls[0]['call_sequence'] = 2
                    calls[0]['content_sha256'] = canonical_hash(calls[0], {'content_sha256'})
                    bad['calls_utf8'] = json.dumps(calls, sort_keys=True)
                    bad['calls_sha256'] = hashlib.sha256(bad['calls_utf8'].encode()).hexdigest()
                else:
                    changed = json.loads(bad[kind+'_utf8'])
                    if mutation == 'qualification': changed['qualifies_for_factory_receipt'] = True
                    elif mutation == 'status': changed['status'] = 'passed'
                    elif mutation == 'reason': changed['reason'] = 'unrelated-failure'
                    elif mutation == 'tokens': changed['failure_accounting']['input_tokens'] = 0
                    elif mutation == 'billing': changed['failure_accounting']['billing_final'] = True
                    elif mutation == 'identity-run': changed['attempt_id'] = 'another-run'
                    else:
                        events = [json.loads(line) for line in bad['ledger_utf8'].splitlines()]
                        events[-1]['previous_sha256'] = '0'*64
                        events[-1]['event_sha256'] = canonical_hash(events[-1], {'event_sha256'})
                        bad['ledger_utf8'] = ''.join(json.dumps(e, sort_keys=True)+'\n' for e in events)
                        bad['ledger_sha256'] = hashlib.sha256(bad['ledger_utf8'].encode()).hexdigest()
                        changed['ledger_head_sha256'] = events[-1]['event_sha256']
                    changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
                    bad[kind+'_utf8'] = json.dumps(changed, sort_keys=True)
                    bad[kind+'_sha256'] = hashlib.sha256(bad[kind+'_utf8'].encode()).hexdigest()
                with self.subTest(forged=mutation), self.assertRaises(ValueError): validate(bad, **args)

    def test_unrelated_boundary_failure_does_not_count_as_read_mutation(self):
        real_scan = probe.IsolatedWorkspace.scan_contents
        def wrong_reason(workspace, scanner, surface):
            if surface == 'builder-workspace': raise ContractError('unrelated-boundary-failure')
            return real_scan(workspace, scanner, surface)
        with tempfile.TemporaryDirectory() as temp, patch.object(probe.IsolatedWorkspace, 'scan_contents', wrong_reason):
            with self.assertRaisesRegex(ValueError, '^p5-workspace-evidence-invalid$'):
                probe.observe_case(Path(temp)/'negative', Path(__file__).resolve().parents[1], 'read-mutation')

    def test_workspace_row_requires_complete_ordered_controller_cases(self):
        rows = [dict(case=case, controller_refused=case != 'clean',
                     transport_calls=2 if case == 'clean' else 1) for case in probe.CASES]
        wrong = copy.deepcopy(rows); wrong[1]['transport_calls'] = 2
        variants = [rows, [], rows[:-1], [rows[0]]*2, list(reversed(rows)), wrong]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'worker.py').write_bytes(b'original\n')
            fixture = type('Fixture', (), {'root': root, 'runtime': lambda self: None})()
            stub = type('Stub', (), {'calls': 0})()
            def deny(provider): raise ContractError('synthetic admission refusal')
            for index, candidate in enumerate(variants):
                with self.subTest(variant=index), patch.object(probe, 'observe', return_value=candidate), \
                        patch.object(drills, 'wrapped', return_value=(stub, None)), patch.object(drills, 'call', deny):
                    observed, matched, gaps = drills.workspace_changed(fixture)
                    self.assertEqual(observed['controller_workspace'], candidate)
                    self.assertEqual(matched, index == 0)
                    self.assertTrue(gaps)
                    self.assertEqual((root/'worker.py').read_bytes(), b'original\n')

    def test_collector_retains_workspace_bytes_without_qualification(self):
        class FakeFixture:
            def __init__(self, parent, repository):
                self.envelope = {'signature': {'value': 'fixture'}}
                self.service = type('Service', (), {'public_key': b'fixture-not-a-key'})()
            def verify_order(self, envelope): raise drills.ExecutionContractError('synthetic signature refusal')
            def signed_observation(self, body): return body
            def close(self): pass
        evidence = {'receipt_utf8': 'exact receipt\n', 'ledger_utf8': 'exact ledger\n'}
        def measured(fixture): return {'controller_workspace': [evidence]}, True, ['unmeasured deployed race']
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}):
            root = Path(temp)/'output'
            with patch.object(drills, 'Fixture', FakeFixture), patch.object(drills, 'FUNCTIONS', {name: measured for name in drills.DRILLS}):
                self.assertTrue(drills.collect(Path(__file__).resolve().parents[1], root))
            receipt = json.loads((root/'workspace-changed.json').read_bytes())
            self.assertEqual(receipt['observed']['controller_workspace'], [evidence])
            self.assertFalse(receipt['production_controller_receipt'])
            self.assertEqual(receipt['gaps'], ['unmeasured deployed race'])
            for path in ('tools/ci/p5_controller_workspace.py', 'tools/ci/p5_workspace_evidence.py', 'tests/test_p5_controller_workspace.py'):
                self.assertEqual(receipt['source_sha256'][path], hashlib.sha256((Path(__file__).resolve().parents[1]/path).read_bytes()).hexdigest())
            with patch.object(drills, 'verify_envelope', return_value=True): self.assertFalse(drills.qualify(root))
