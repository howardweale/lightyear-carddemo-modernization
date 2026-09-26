"""Offline replay of the retained native application and row-effect evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from lightyear_calibration.application_effects import admit
from lightyear_calibration.application_journey import compare_lanes, read_trace, verify_lane
from lightyear_calibration.contracts import canonical, digest, seal, verify

ROOT = Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-application'


class ApplicationPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = zipfile.ZipFile(ROOT/'evidence.zip'); cls.addClassCleanup(cls.archive.close)
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.workspace = Path(cls.temp.name)

    @classmethod
    def read(cls, name): return json.loads(cls.archive.read('evidence/'+name))

    @classmethod
    def snapshot(cls, label, lane):
        manifest = cls.read(f'states/{label}-{lane}.json'); verify(manifest)
        tables = {}
        for table, item in manifest['tables'].items():
            multiset = cls.read(f"states/blobs/{item['row_multiset_sha256']}.json")
            if digest(multiset) != item['row_multiset_sha256']: raise AssertionError('Changed row-hash multiset')
            tables[table] = dict(item['header'], row_multiset=multiset)
        native = seal(dict(manifest['header'], tables=tables))
        if native['content_sha256'] != manifest['native_state_sha256']: raise AssertionError('Changed native state')
        folder = cls.workspace/label/lane; folder.mkdir(parents=True, exist_ok=True)
        (folder/'state.json').write_bytes(canonical(native))
        prefix = f'evidence/rows/{label}/{lane}/'
        for name in cls.archive.namelist():
            if name.startswith(prefix):
                target = (folder/name[len(prefix):]).resolve()
                if not target.is_relative_to(folder.resolve()): raise AssertionError('Unsafe archive path')
                target.write_bytes(cls.archive.read(name))
        return folder

    def test_archive_bindings_and_bounded_claim(self):
        receipt = json.loads((ROOT/'receipt.json').read_text()); verify(receipt)
        self.assertEqual(receipt['evidence_archive']['sha256'], hashlib.sha256((ROOT/'evidence.zip').read_bytes()).hexdigest())
        self.assertEqual(set(receipt['evidence_files']), set(self.archive.namelist()))
        for name, expected in receipt['evidence_files'].items():
            self.assertEqual(expected, hashlib.sha256(self.archive.read(name)).hexdigest(), name)
        self.assertTrue(receipt['bounded_journey_equivalence'])
        for claim in ('schema_equivalence','application_equivalence','platform_qualification','independently_attested'):
            self.assertFalse(receipt[claim])
        cleanup = json.loads((ROOT/'cleanup.json').read_text()); verify(cleanup)
        self.assertEqual(receipt['cleanup_sha256'], cleanup['content_sha256'])
        self.assertTrue(cleanup['all_experiment_containers_stopped'])
        self.assertEqual(4, len(cleanup['containers']))
        self.assertTrue(all(not x['running'] and x['data_retained'] for x in cleanup['containers']))
        effect = self.read('final/effect-checkpoint.json'); verify(effect)
        self.assertEqual(305, effect['new_application_allowed_count'])
        self.assertEqual(5540, effect['retained_prior_allowed_count'])
        self.assertEqual(5, len(effect['base_rules_newly_allowed_differences']))
        self.assertEqual(300, len(effect['application_allowed_differences']))
        self.assertFalse(effect['unresolved_differences'])

    def test_native_business_readbacks_and_all_application_rules_recompute(self):
        lanes = ('oracle','postgresql')
        folders = {lane:self.snapshot('after',lane) for lane in lanes}
        before = {lane:self.snapshot('before',lane) for lane in lanes}
        executions = {lane:self.read(f'attempt-3/{lane}/execution.json') for lane in lanes}
        effects = admit(self.read('final/base-checkpoint.json'),folders,before,self.read('final/primary-keys.json'),executions,
                        prior_checkpoint=self.read('baseline/ms84-checkpoint.json'))
        self.assertEqual(self.read('final/effect-checkpoint.json'),effects)
        results = {}
        for lane in lanes:
            trace = self.workspace/(lane+'.xml'); trace.write_bytes(self.archive.read(f'evidence/attempt-3/{lane}/journey.xml'))
            result = verify_lane(folders[lane],trace,executions[lane],(ROOT/'LightyearJourneyTest.java').read_bytes())
            self.assertEqual(self.read(f'final/{lane}-verified-journey.json'),result)
            self.assertEqual(12,result['accounting_entries_verified'])
            self.assertEqual(6,result['balanced_accounting_groups'])
            results[lane]=result
        self.assertEqual(json.loads((ROOT/'comparison.json').read_text()),compare_lanes(results,effects))

    def test_earlier_setup_failures_and_warnings_are_not_relabelled_as_final_success(self):
        for lane in ('oracle','postgresql'):
            for attempt in (1,2,3):
                execution=self.read(f'attempt-{attempt}/{lane}/execution.json');verify(execution)
                self.assertEqual(execution['harness_sha256'],hashlib.sha256(self.archive.read(f'evidence/attempt-{attempt}/{lane}/harness.java')).hexdigest())
            self.assertEqual(1,self.read(f'attempt-1/{lane}/execution.json')['exit_code'])
            issues=self.read(f'attempt-2/{lane}/observed-issues.json');verify(issues)
            self.assertEqual(2,len(issues['observed_rows']))
            path=self.workspace/(lane+'-final.xml');path.write_bytes(self.archive.read(f'evidence/attempt-3/{lane}/journey.xml'))
            trace,_=read_trace(path)
            self.assertEqual('0',trace['newIssueCount'])
            self.assertEqual('completed-and-committed',trace['status'])


if __name__ == '__main__': unittest.main()
