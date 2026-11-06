"""Actual disposable controller context refusal and retained-evidence negatives."""
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
from tools.ci import p5_controller_context as probe
from tools.ci.p5_context_evidence import CASES, validate


class ControllerContextTests(unittest.TestCase):
    def test_real_context_assembly_refusal_retention_and_corruption(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'), 'true')
        retained = []
        with tempfile.TemporaryDirectory(prefix='p5-context-ci-') as temp:
            for case in CASES:
                row = probe.observe_case(Path(temp)/case, Path(__file__).resolve().parents[1], case)
                retained.append(row)
                self.assertEqual(row['transport_calls'], 2 if case == 'clean' else 0)
                self.assertIs(row['controller_refused'], case != 'clean')
                directory = Path(temp)/case/'runs'/row['run_id']
                payload = row['clean_control'] if case == 'clean' else row
                for kind, filename in (('receipt', 'receipt.json'), ('identity', 'attempt-identity.json')):
                    self.assertEqual(payload[kind+'_utf8'].encode('utf-8'), (directory/filename).read_bytes())
                if case != 'clean':
                    self.assertEqual(row['ledger_utf8'].encode('utf-8'), (directory/'events.jsonl').read_bytes())
                    self.assertEqual(row['scanner_observations'][-1]['outcome'], 'isolation-breach')
                    self.assertEqual(row['scanner_observations'][-1]['surface'], 'controller-context')
                # Public observations contain hashes, never the planted context text.
                value = json.loads((Path(temp)/case/'synthetic-expected-values.json').read_bytes())['values'][0]
                encoded = json.dumps(row)
                self.assertNotIn(value, encoded)
                self.assertNotIn(' '.join(value.upper()), encoded)
        # Exact bytes remain independently checkable after temporary runs disappear.
        for row in retained:
            args = dict(case=row['case'], work_order_sha256=row['work_order_sha256'])
            self.assertTrue(validate(row, **args))
            mutations = ('calls', 'surface', 'reason', 'assembly', 'initial-scan', 'source-change')
            for mutation in mutations:
                bad = copy.deepcopy(row)
                if mutation == 'calls': bad['transport_calls'] += 1
                elif mutation == 'assembly': bad['assembly']['context_sha256'] = '0'*64
                elif mutation == 'source-change': bad['assembly']['source_after_sha256'] = '0'*64
                elif mutation == 'initial-scan':
                    bad['scanner_observations'] = [r for r in bad['scanner_observations'] if r['surface'] != 'initial-workspace-file']
                else:
                    target = next(r for r in bad['scanner_observations'] if r['surface'] == 'controller-context')
                    target['surface' if mutation == 'surface' else 'outcome'] = 'wrong-boundary'
                with self.subTest(case=row['case'], mutation=mutation), self.assertRaises(ValueError):
                    validate(bad, **args)
            if row['case'] == 'clean': continue
            for kind in ('receipt', 'identity', 'ledger'):
                bad = copy.deepcopy(row); bad[kind+'_utf8'] += ' '
                with self.subTest(case=row['case'], bytes=kind), self.assertRaises(ValueError):
                    validate(bad, **args)
            for mutation in ('qualification', 'status', 'tokens', 'usage', 'identity-run', 'ledger-chain'):
                bad = copy.deepcopy(row)
                kind = 'identity' if mutation == 'identity-run' else 'receipt'
                if mutation == 'ledger-chain':
                    events = [json.loads(line) for line in bad['ledger_utf8'].splitlines()]
                    events[-1]['previous_sha256'] = '0'*64
                    events[-1]['event_sha256'] = canonical_hash(events[-1], {'event_sha256'})
                    bad['ledger_utf8'] = ''.join(json.dumps(e, sort_keys=True)+'\n' for e in events)
                    bad['ledger_sha256'] = hashlib.sha256(bad['ledger_utf8'].encode()).hexdigest()
                    changed = json.loads(bad['receipt_utf8'])
                    changed['ledger_head_sha256'] = events[-1]['event_sha256']
                else:
                    changed = json.loads(bad[kind+'_utf8'])
                    if mutation == 'qualification': changed['qualifies_for_factory_receipt'] = True
                    elif mutation == 'status': changed['status'] = 'passed'
                    elif mutation == 'tokens': changed['failure_accounting']['input_tokens'] = 1
                    elif mutation == 'usage': changed['failure_accounting']['in_flight_final_usage'] = 'unknown'
                    else: changed['attempt_id'] = 'another-run'
                changed['content_sha256'] = canonical_hash(changed, {'content_sha256'})
                bad[kind+'_utf8'] = json.dumps(changed, sort_keys=True)
                bad[kind+'_sha256'] = hashlib.sha256(bad[kind+'_utf8'].encode()).hexdigest()
                with self.subTest(case=row['case'], forged=mutation), self.assertRaises(ValueError):
                    validate(bad, **args)

    def test_unrelated_scanner_error_cannot_count_as_fragment_refusal(self):
        # Negative control deliberately injects a different error; it must fail observation.
        real_scan = probe.isolation_scan.scan
        def wrong_reason(artifacts, canaries, values):
            artifacts = list(artifacts)
            if any(name == 'controller-context' for name, raw in artifacts):
                raise ContractError('isolation-scan-limit')
            return real_scan(artifacts, canaries, values)
        with tempfile.TemporaryDirectory() as temp, patch.object(probe.isolation_scan, 'scan', wrong_reason):
            with self.assertRaisesRegex(ValueError, '^p5-context-evidence-invalid$'):
                probe.observe_case(Path(temp)/'negative', Path(__file__).resolve().parents[1], 'normalized')

    def test_answer_row_requires_complete_ordered_controller_cases(self):
        # Keep the original standalone scanner real; stub only this wiring dependency.
        rows = [dict(case=case, controller_refused=case != 'clean',
                     transport_calls=2 if case == 'clean' else 0) for case in CASES]
        stub = type('Stub', (), {'calls': 0})()
        bad_flag = copy.deepcopy(rows); bad_flag[1]['controller_refused'] = False
        bad_call = copy.deepcopy(rows); bad_call[1]['transport_calls'] = 1
        variants = [rows, [], rows[:-1], [rows[0]]*4, list(reversed(rows)), bad_flag, bad_call]
        for index, candidate in enumerate(variants):
            with self.subTest(variant=index), patch.object(probe, 'observe', return_value=candidate), \
                    patch.object(drills, 'wrapped', return_value=(stub, None)):
                observed, matched, gaps = drills.answer_fragment(object())
                self.assertEqual(observed['controller_context'], candidate)
                self.assertEqual(matched, index == 0)
                self.assertTrue(gaps)

    def test_collector_retains_context_bytes_and_still_refuses_qualification(self):
        # Serialization control only; the integration test above uses real controller/scanner.
        class FakeFixture:
            def __init__(self, parent, repository):
                self.envelope = {'signature': {'value': 'fixture'}}
                self.service = type('Service', (), {'public_key': b'fixture-not-a-key'})()
            def verify_order(self, envelope):
                raise drills.ExecutionContractError('synthetic corrupt signature')
            def signed_observation(self, body): return body
            def close(self): pass
        evidence = {'receipt_utf8': 'exact receipt\n', 'ledger_utf8': 'exact ledger\n'}
        def measured(fixture):
            return {'controller_context': [evidence]}, True, ['unmeasured deployed path']
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}):
            root = Path(temp)/'output'
            with patch.object(drills, 'Fixture', FakeFixture), patch.object(drills, 'FUNCTIONS',
                    {name: measured for name in drills.DRILLS}):
                self.assertTrue(drills.collect(Path(__file__).resolve().parents[1], root))
            receipt = json.loads((root/'answer-fragment.json').read_bytes())
            self.assertEqual(receipt['observed']['controller_context'], [evidence])
            self.assertFalse(receipt['production_controller_receipt'])
            self.assertEqual(receipt['gaps'], ['unmeasured deployed path'])
            for path in ('tools/ci/p5_controller_context.py', 'tools/ci/p5_context_evidence.py',
                         'tests/test_p5_controller_context.py', 'src/lightyear_factory/context.py',
                         'src/lightyear_factory/ledger.py', 'src/lightyear_factory/workspace.py'):
                self.assertEqual(receipt['source_sha256'][path], hashlib.sha256((Path(__file__).resolve().parents[1]/path).read_bytes()).hexdigest())
            with patch.object(drills, 'verify_envelope', return_value=True):
                self.assertFalse(drills.qualify(root))
