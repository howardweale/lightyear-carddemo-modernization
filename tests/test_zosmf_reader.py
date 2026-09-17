"""MS77 bindings are mock-tested, never evidence of a real mainframe run."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from lightyear_runtime.mock_zosmf import RunningMockZosmf, load_mock_fixture
from lightyear_runtime.zosmf import HttpClientTransport, ZosmfClient, ZosmfConfig, ZosmfCredentials, ZosmfError
from lightyear_workflow.batch_pack import SourceLane, TargetLane, PackError, load, plan
from lightyear_workflow.zosmf_reader import ZosmfReader
from tests.test_zosmf_adapter import StubTransport, MAPPING, FIXTURE, ROOT


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mapping = Path(self.temp.name) / 'mapping.json'
        self.mapping_data = json.loads(MAPPING.read_text())
        self.datasets = {
            'CARDDEMO.TRANFILE': {'ddname': 'TRANSACT', 'stepname': 'STEP15'},
            'CARDDEMO.ACCTFILE': {'ddname': 'ACCTFILE', 'stepname': 'STEP15'},
        }
        self.mapping.write_text(json.dumps(self.mapping_data))
        self.fixture = load_mock_fixture(FIXTURE)
        for identifier, ddname in [(8, 'TRANSACT'), (9, 'ACCTFILE')]:
            self.fixture['files'].append({'id': identifier, 'ddname': ddname,
                'stepname': 'STEP15', 'procstep': None, 'jobname': 'INTCALC',
                'jobid': 'JOB00001', 'record-count': 1})
            self.fixture['records'][str(identifier)] = f'{ddname} retained fixture\n'
        self.pack = load(ROOT / 'spec/batch-packs/carddemo-intcalc.pack.json')
        self.transport = StubTransport(self.fixture)
        self.config = ZosmfConfig('https://zosmf.example.test', 'mock-unit-test')

    def reader(self, *, attest=False):
        return ZosmfReader(ZosmfClient(self.transport, ZosmfCredentials()), self.config,
                           self.mapping, attest_real_zos=attest, datasets=self.datasets)

    def test_loopback_pack_observation_remains_simulated_and_only_gets(self):
        with RunningMockZosmf(self.fixture) as mock:
            config = ZosmfConfig(mock.base_url, 'mock', allow_loopback_http=True)
            reader = ZosmfReader(ZosmfClient(HttpClientTransport(config), ZosmfCredentials()), config,
                                 self.mapping, datasets=self.datasets)
            receipt = SourceLane(reader).observe(self.pack.jobs[0])
        self.assertEqual('simulated', receipt['evidence_class'])
        self.assertEqual({'simulated'}, {o['evidence_class'] for o in receipt['evidence']['observations']})
        self.assertEqual(b'TRANSACT retained fixture\n', receipt['outputs']['CARDDEMO.TRANFILE'])
        self.assertFalse(receipt['submitted_by_us'])
        self.assertEqual({'GET'}, {r['method'] for r in mock.server.requests})
        self.assertFalse(hasattr(reader, 'submit'))

    def test_https_alone_does_not_upgrade_simulated_evidence(self):
        self.assertEqual('simulated', self.reader().job('INTCALC')['evidence_class'])

    def test_explicit_attestation_preserves_adapter_class_in_mock_contract_test(self):
        # A stub tests propagation only; this is not a real z/OS baseline.
        receipt = SourceLane(self.reader(attest=True)).observe(self.pack.jobs[0])
        self.assertEqual('zos_observed', receipt['evidence_class'])
        self.assertEqual({'zos_observed'}, {o['evidence_class'] for o in receipt['evidence']['observations']})

    def test_loopback_and_non_boolean_attestation_are_rejected(self):
        self.config = ZosmfConfig('http://127.0.0.1:1234', 'mock', allow_loopback_http=True)
        for value in [True, 'true', 1]:
            with self.subTest(value=value), self.assertRaises(ZosmfError):
                self.reader(attest=value)

    def test_latest_selection_uses_completion_time_not_listing_order(self):
        client = ZosmfClient(self.transport, ZosmfCredentials())
        newer = copy.deepcopy(self.fixture['job'])
        older = {**newer, 'jobid': 'JOB99999', 'exec-ended': '2021-01-01T00:00:00Z'}
        active = {**newer, 'jobid': 'JOB12345', 'status': 'ACTIVE', 'exec-ended': None}
        client.list_jobs = lambda *a, **k: [newer, active, older]
        reader = ZosmfReader(client, self.config, self.mapping)
        self.assertEqual('JOB00001', reader.job('INTCALC')['jobid'])

    def test_ambiguous_or_incomplete_listing_is_refused(self):
        job = self.fixture['job']
        cases = [[], [job, {**job, 'jobid': 'JOB00002'}],
                 [{**job, 'exec-ended': None}], [{**job, 'exec-ended': '2026-01-01T00:00:00'}],
                 [{**job, 'status': 'ACTIVE'}], [job] * 1000]
        for jobs in cases:
            with self.subTest(count=len(jobs)), self.assertRaises(ZosmfError):
                client = ZosmfClient(self.transport, ZosmfCredentials())
                client.list_jobs = lambda *a, **k: jobs
                ZosmfReader(client, self.config, self.mapping).job('INTCALC')

    def test_explicit_job_id_uses_collector_without_list_lookup(self):
        self.assertEqual('JOB00001', self.reader().job('INTCALC', 'JOB00001')['jobid'])
        self.assertNotIn('/zosmf/restjobs/jobs', [r[0] for r in self.transport.requests])

    def test_job_identity_and_completion_remain_checked(self):
        for change in [{'jobname': 'OTHER'}, {'jobid': 'JOB00002'}, {'status': 'ACTIVE'}]:
            original = copy.deepcopy(self.fixture['job'])
            self.fixture['job'].update(change)
            with self.subTest(change=change), self.assertRaises(ZosmfError):
                self.reader().job('INTCALC', 'JOB00001')
            self.fixture['job'] = original

    def test_failed_selection_does_not_leave_previous_job_readable(self):
        reader = self.reader()
        reader.job('INTCALC')
        with self.assertRaises(ZosmfError): reader.job('POSTTRAN')
        with self.assertRaises(ZosmfError): reader.dataset('CARDDEMO.TRANFILE')

    def test_outputs_require_explicit_unambiguous_complete_spool_binding(self):
        reader = self.reader()
        with self.assertRaises(ZosmfError): reader.dataset('CARDDEMO.TRANFILE')
        reader.job('INTCALC')
        for name in ['../../etc/passwd', 'CARDDEMO.MISSING']:
            with self.subTest(name=name), self.assertRaises(ZosmfError): reader.dataset(name)
        original = copy.deepcopy(self.fixture['files'])
        for change in [{'jobid': 'JOB00002'}, {'id': True}, {'record-count': 5001}, {'record-count': None}]:
            self.fixture['files'] = copy.deepcopy(original)
            self.fixture['files'][-2].update(change)
            with self.subTest(change=change), self.assertRaises(ZosmfError): reader.dataset('CARDDEMO.TRANFILE')
        self.fixture['files'] = original + [copy.deepcopy(original[-2])]
        with self.assertRaises(ZosmfError): reader.dataset('CARDDEMO.TRANFILE')

    def test_nonzero_completion_is_preserved_not_relabelled_success(self):
        self.fixture['job']['retcode'] = 'ABEND S0C7'
        self.assertEqual('ABEND S0C7', self.reader().job('INTCALC')['retcode'])


class PackBindingTests(unittest.TestCase):
    def setUp(self):
        self.pack = load(ROOT / 'spec/batch-packs/carddemo-intcalc.pack.json')

    def test_simulation_propagates_through_target_receipt_in_either_lane(self):
        from tests.test_batch_pack import FakeReader
        for source_class, target_class in [('simulated', 'zos_observed'), ('zos_observed', 'simulated'),
                                           ('simulated', 'simulated')]:
            with self.subTest(source=source_class, target=target_class):
                reader = FakeReader({})
                reader.job = lambda *a: {'jobid': 'JOB1', 'retcode': 'CC 0000', 'evidence_class': target_class}
                receipt = TargetLane(reader, lambda *a: 'JOB1').replay(self.pack.jobs[0],
                    {'run': 'SOURCE', 'evidence_class': source_class})
                self.assertEqual('simulated', receipt['evidence_class'])
                self.assertEqual(source_class, receipt['source_evidence_class'])
                self.assertEqual(target_class, receipt['target_evidence_class'])

    def test_missing_class_defaults_to_simulated_and_unknown_is_refused(self):
        from tests.test_batch_pack import FakeReader
        reader = FakeReader({})
        self.assertEqual('simulated', SourceLane(reader).observe(self.pack.jobs[0])['evidence_class'])
        reader.job = lambda *a: {'evidence_class': 'observed'}
        with self.assertRaises(PackError): SourceLane(reader).observe(self.pack.jobs[0])

    def test_plan_revalidates_mutated_source_and_derives_target_submissions(self):
        self.pack.source['verbs'].append('submit')
        with self.assertRaises(PackError): plan(self.pack)
        self.pack.source['verbs'].remove('submit')
        self.pack.target['verbs'].remove('submit')
        self.assertEqual([], plan(self.pack)['target_submits'])
        self.assertEqual([], plan(self.pack)['source_submits'])

    def test_reference_normalizations_exist_without_granting_approval(self):
        ledger = json.loads((ROOT / 'spec/comparison-normalizations.json').read_text())
        self.assertLessEqual(set(plan(self.pack)['normalization_referenced']),
                             {r['id'] for r in ledger['rules']})
