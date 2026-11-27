"""Public-only synthetic four-case budget fixture, no evaluator process or provider."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from lightyear_factory import public_evaluator_adapter as adapter
from lightyear_factory import public_repair_answer_key as key
from lightyear_factory import public_repair_controller as ctl
from lightyear_factory import public_repair_provider as provider
from lightyear_factory import public_repair_staged as staged
from lightyear_factory import public_value_feedback as v
from lightyear_mainframe.records import load_copybook

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/reference-execution/public-cases'
CANDIDATE = ctl.sha(b'synthetic')
FAIL = ('PC-06', 'PC-09', 'PC-11', 'PC-12')


def fixture():
    # The 16 public hand fixtures are hash-joined to the published answer key by the loader.
    # These four fault sites are artificial, independent of the actual four failing IDs.
    suite = (FIXTURES / 'SUITE.json').read_bytes()
    assert hashlib.sha256(suite).hexdigest() == v.SUITE
    cases = adapter.public_suite(suite, FIXTURES)
    observations, receipts = [], []
    for index, case in enumerate(cases):
        case_id = v.IDS[index]
        expected = case['expected']
        actual = dict(expected)
        if case_id in FAIL:
            lines = actual['stdout'].splitlines(keepends=True)
            # Maximal encoded 256-byte prefixes. The binary representation prevents JSON
            # amplification. A redacted or incomplete sample cannot count as retained here.
            actual['stdout'] = b''.join([b'\x01' * 256 + b'\n'] * 3 + lines[3:])
            actual['stderr'] = (b'\x02' * 256 + b'\n') * (4 if case_id == FAIL[0] else 3)
        if case_id == 'PC-06' or case_id == 'PC-09':
            channel = 'ACCTFILE' if case_id == 'PC-06' else 'TRANSACT'
            width = v.WIDTH[channel]
            actual[channel] = expected[channel][:-width] + b'Q' * (width - 1)
        if case_id == 'PC-11':
            actual['exit'] = 1
        observations.append((expected, actual, case['compare_output_files'], False))
        receipts.append(dict(index=index, timed_out=False, output_capped=False))
    return cases, observations, receipts


def report(row):
    return dict(bytes=len(ctl.canonical(row)), sha256=ctl.digest(row), outcomes=row['outcomes'],
                exit_values=row['exits'], kept=[[x['case'], x['channel'], x['index']] for x in row['samples']],
                omitted=row['omitted'], truncated=row['truncated'])


def verify_published_route(root, reviewed):
    """Called by the existing public archive CI job after its authenticated unpack."""
    cases, observations, _ = fixture()
    class PublicWorker:
        def __init__(self):
            self.calls = 0

        def run_public(self, build, inputs, timestamp, date, deadline, limits):
            index = self.calls
            self.calls += 1
            assert inputs == cases[index]['inputs'] and set(inputs) == key.INPUT_NAMES
            actual = dict(ACCTFILE=b'', TRANSACT=b'')
            actual.update(observations[index][1])
            return dict(actual, cleanup=True, timed_out=False, output_capped=False,
                        receipt_sha256='c'*64, artifact_sha256=build['artifact_sha256'],
                        build_receipt_sha256=build['build_receipt_sha256'])

    worker = PublicWorker()
    port = key.ValuePublicAdapter(worker, root, FIXTURES, ROOT, reviewed, key.sha, clock=lambda: 1)
    built = dict(status='BUILT', artifact_sha256=CANDIDATE, build_receipt_sha256='b'*64)
    result = port.evaluate_public(built, v.SUITE, 601)
    expected = json.loads((ROOT/'tests/fixtures/public-feedback/round-five-budget.json').read_bytes())
    assert worker.calls == 16 and (result['match'], result['different']) == (12, 4)
    assert report(result['feedback']) == expected[str(v.CAP)]


class PublicValuesTests(unittest.TestCase):
    def setUp(self):
        self.cases, self.obs, self.receipts = fixture()

    def feedback(self):
        return v.envelope(CANDIDATE, self.cases, self.obs, self.receipts, v.SUITE, v.KEY)

    def test_round_five_profile_and_exact_budget_readback(self):
        layouts = {k: load_copybook(ROOT/'spec/mainframe/copybooks'/path) for k, (path, _) in adapter.LAYOUTS.items()}
        matched, tallies = adapter.tally(self.obs, layouts)
        self.assertEqual(matched, 12)
        for channel, total in [('ACCTFILE', 25), ('TRANSACT', 33)]:
            fields = {r['field']: (r['records_different'], r['records_compared']) for r in tallies
                      if r['channel'] == channel and r['field']}
            self.assertEqual(fields, {f: (1, total) for f in ctl.FIELDS[channel] if f})
        self.assertEqual({r['channel']: (r['records_different'], r['records_compared']) for r in tallies
                          if not r['field']}, {'ACCTFILE': (1, 13), 'TRANSACT': (1, 13),
                                              'stdout': (12, 85), 'stderr': (13, 13), 'exit': (1, 16)})
        # The historical r1 budget is measured on the identical synthetic observations.
        with patch.object(v, 'CAP', 4096):
            previous = self.feedback()
        rows = [(4096, previous), (8192, self.feedback())]
        expected = json.loads((ROOT/'tests/fixtures/public-feedback/round-five-budget.json').read_bytes())
        for budget, row in rows:
            observed = report(row)
            self.assertEqual(observed, expected[str(budget)])
            self.assertEqual(row['outcomes'].count('M'), matched)
            for item in row['samples']:
                for side in (item['expected'], item['actual']):
                    if side is not None:
                        self.assertFalse(side.get('clipped') or side.get('redacted'))
            print('public-feedback-budget', budget, json.dumps(observed, sort_keys=True))
        self.assertEqual(v.CAP, 8192)
        self.assertEqual((v.ROWS, v.LINE_BYTES, ctl.FEEDBACK_POLICY['bytes_max']), (32, 256, 4096))
        self.assertEqual(rows[1][1]['omitted'], dict(stdout=7, stderr=7, ACCTFILE=0, TRANSACT=0))

    def test_projection_and_real_wire_encoder(self):
        row = self.feedback()
        for role in ('analysis', 'repair'):
            req = staged.ValueStagedController.project(role, {'public': 'context'}, 'plan', 'synthetic',
                                                       'analysis', [], row)
            counted, generated, bound, _ = provider.requests(req)
            self.assertEqual(req['feedback'], row)
            self.assertLessEqual(max(len(counted), len(generated)), bound)
            self.assertLessEqual(bound, ctl.CAPS[role])
        with self.assertRaises(ctl.Refused):
            ctl.projection('repair', {'public': 'context'}, '', 'synthetic', '', [], row)

    def test_wrong_public_joins_and_channels_refuse(self):
        row = self.feedback()
        for name in ('answer_manifest_sha256', 'public_suite_sha256', 'candidate_sha256'):
            with self.subTest(name=name), self.assertRaises(ctl.Refused):
                v.validate(dict(row, **{name: '0' * 64}), CANDIDATE, v.SUITE, 'PUBLIC_DIVERGENCE')
        for name, value in [('case', 'H-01'), ('channel', 'hidden'), ('extra', 1)]:
            bad = copy.deepcopy(row)
            bad['samples'][0][name] = value
            with self.assertRaises(ctl.Refused):
                v.validate(bad, CANDIDATE, v.SUITE, 'PUBLIC_DIVERGENCE')
        port = object.__new__(key.ValuePublicAdapter)
        port.cases, port.suite, port.answer_key = self.cases, v.SUITE, {'manifest_sha256': '0' * 64}
        with self.assertRaises(ctl.Refused):
            port.public_feedback(CANDIDATE, [], self.obs, self.receipts)

    def test_missing_side_final_lf_limits_and_redaction(self):
        self.assertEqual(list(v.samples('PC-01', 'stdout', b'x\n', b'x')),
                         [('PC-01', 'stdout', 1, (b'x', True), (b'x', False))])
        self.assertIsNone(v.value(None, False, True))
        self.assertEqual(v.value(b'/home/example/file', True, True), {'bytes': 18, 'redacted': True})
        self.assertTrue(v.value(b'x' * 257, False, True)['clipped'])
        self.obs[0] = (*self.obs[0][:3], True)
        self.receipts[0]['timed_out'] = True
        self.assertEqual(self.feedback()['outcomes'][0], 'T')
        self.receipts[0]['output_capped'] = True
        self.assertEqual(self.feedback()['outcomes'][0], 'B')
