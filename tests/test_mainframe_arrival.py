from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from lightyear_mainframe.arrival import dry_run
from lightyear_mainframe.records import DecodeError
from lightyear_runtime.zosmf import ZosmfError

ROOT = Path(__file__).resolve().parents[1]


class ArrivalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = dry_run(ROOT/'spec/mainframe/arrival-kit.json')

    def test_published_dry_run_reproduces_exactly(self):
        published = json.loads((ROOT/'docs/mainframe/arrival-dry-run.json').read_text())
        self.assertEqual(published, json.loads(json.dumps(self.receipt)))

    def test_entire_batch_pack_runs_in_both_lanes(self):
        r = self.receipt
        self.assertEqual('invocation-and-decoding-passed',r['status'])
        self.assertEqual(['interest-calculation','transaction-posting'],[j['job'] for j in r['jobs']])
        self.assertEqual(['INTCALC','POSTTRAN'],[j['jobname'] for j in r['submissions']])
        self.assertEqual(6, sum(len(output['records']) for j in r['jobs'] for lane in j['lanes'].values() for output in lane['decoded_outputs'].values()))
        self.assertEqual([],r['plan']['source_submits'])
        self.assertFalse(r['source_has_submit_capability'])
        self.assertEqual({'GET'}, {q['method'] for q in r['requests']})
        self.assertTrue(all(not q['authorization_present'] for q in r['requests']))

    def test_deliberate_balance_difference_never_becomes_equivalence(self):
        r = self.receipt
        self.assertEqual('simulated',r['evidence_class'])
        self.assertFalse(r['mainframe_equivalent'])
        self.assertIsNone(r['runtime_branch_coverage'])
        self.assertEqual([],r['normalization_rules_applied'])
        for job in r['jobs']:
            self.assertFalse(job['raw_output_equal']['CARDDEMO.ACCTFILE'])
            self.assertEqual('not-assessed',job['equivalence_verdict'])
            balances=[]
            for name in ('source','target'):
                lane=job['lanes'][name]
                self.assertEqual('simulated',lane['evidence_class'])
                self.assertEqual(name=='target',lane['submitted_by_us'])
                output=lane['decoded_outputs']['CARDDEMO.ACCTFILE']
                self.assertEqual('HEXOUT',output['binding']['procstep'])
                self.assertEqual('EXPORT',output['binding']['stepname'])
                balances.append(next(f['value'] for f in output['records'][0]['fields'] if f['path'].endswith('.ACCT-CURR-BAL')))
                self.assertTrue(all(o['evidence_class']=='simulated' for o in lane['evidence']['observations']))
            self.assertEqual(['100.25','100.26'],balances)

    def test_comp3_probe_is_exercised_with_golden_bytes(self):
        fields=self.receipt['packed_probe'][0]['fields']
        self.assertEqual('-123.45',next(f['value'] for f in fields if f['path'].endswith('.AMOUNT')))
        self.assertEqual('12.34',next(f['value'] for f in fields if f['path'].endswith('.RATE')))

    def mutated(self, update):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            shutil.copytree(ROOT/'spec/mainframe',root/'mainframe')
            shutil.copytree(ROOT/'spec/batch-packs',root/'batch-packs')
            update(root/'mainframe')
            return dry_run(root/'mainframe/arrival-kit.json')

    def test_wrong_procstep_is_refused(self):
        def update(root):
            p=root/'arrival-kit.json';c=json.loads(p.read_text())
            c['jobs']['INTCALC']['bindings']['CARDDEMO.ACCTFILE']['procstep']='WRONG'
            p.write_text(json.dumps(c))
        with self.assertRaises(ZosmfError):self.mutated(update)

    def test_corrupt_retained_export_is_refused(self):
        def update(root):
            p=root/'mock/intcalc-source.json';c=json.loads(p.read_text())
            spool=next(f for f in c['files'] if f['ddname']=='TRANHEX')
            e=json.loads(c['records'][str(spool['id'])]);e['record_count']=2
            c['records'][str(spool['id'])]=json.dumps(e)
            p.write_text(json.dumps(c))
        with self.assertRaises(DecodeError):self.mutated(update)

    def test_missing_job_binding_and_native_label_are_refused(self):
        for change in ['job','label']:
            def update(root):
                p=root/'arrival-kit.json';c=json.loads(p.read_text())
                if change=='job':c['jobs'].pop('POSTTRAN')
                else:c['evidence_class']='zos_observed'
                p.write_text(json.dumps(c))
            with self.subTest(change=change),self.assertRaises(ValueError):self.mutated(update)
