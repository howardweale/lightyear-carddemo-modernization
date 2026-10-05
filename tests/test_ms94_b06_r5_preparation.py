import copy
import unittest
from pathlib import Path
from lightyear_calibration.contracts import read_json, verify
from tools.ms94_b06_classpath_audit import CLASSES, inventory

PUBLIC = Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-ms94/stage-b-06/preparation'


class PreparationTests(unittest.TestCase):
    def test_alternative_copies_do_not_claim_runtime_resolution(self):
        rows=[]
        for name in CLASSES:
            member=name.replace('.','/')+'.class'
            rows.extend([{'member':member,'origin':'/application/x.jar','sha256':'a'*64},
                         {'member':member,'origin':'/root/.m2/same.jar','sha256':'a'*64},
                         {'member':member,'origin':'/root/.m2/different.jar','sha256':'b'*64}])
        result=inventory({'classes':rows})
        self.assertEqual(6,len(result))
        self.assertTrue(all(len(r['differing_m2_copies'])==1 and not r['loaded_copy_confirmed'] for r in result))
        rows.append({**rows[0],'sha256':'c'*64})
        with self.assertRaisesRegex(ValueError,'application-copy-ambiguous'): inventory({'classes':rows})

    def test_published_revisions_bind_four_sources_without_changing_retained_slots(self):
        revised=set()
        summary=read_json(PUBLIC/'offline-catalog-r4/preparation-summary.json')
        for journey,count in [('j1',55),('j2',41),('j3',39)]:
            old=read_json(PUBLIC/'execution-admission-r3'/f'{journey}-assembly-v3.json')
            new=read_json(PUBLIC/'execution-r5'/f'{journey}-assembly-v5.json');verify(new)
            self.assertEqual(old['content_sha256'],new['previous_assembly_sha256'])
            self.assertEqual(count,len(new['schedule']))
            self.assertIsNone(new['executable_snapshot_sha256'])
            self.assertFalse(new['docker_runs_authorized'])
            for before,after in zip(old['schedule'],new['schedule']):
                self.assertEqual(before['id'],after['id'])
                expected={**before['expected']}
                if before['control']=='duplicate-trace-key':
                    expected.update(equipment_suspect=True,delivery='empty')
                self.assertEqual(expected,after['expected'])
                if before['source']['sha256'] != after['source']['sha256']:
                    revised.add(after['source']['sha256'])
                self.assertTrue(after['source']['compiled'])
                if 'retained' in after['control']:
                    self.assertEqual(before['source']['sha256'],after['source']['sha256'])
        self.assertEqual({r['revised_sha256'] for r in summary['source_revisions']},revised)


if __name__=='__main__':unittest.main()
