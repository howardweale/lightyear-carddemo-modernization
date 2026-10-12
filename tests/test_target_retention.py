import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from lightyear_mainframe.target_retention import Retention,paired_case,verify_retention
from tools.check_equivalence_followup import targeted_outcome
from tools.aggregate_equivalence_shards import validate_shards


def fake(target,name,folder):
    (folder/'logs').mkdir(parents=True);(folder/'after').mkdir()
    (folder/'logs/program.stdout').write_bytes(b'fixed stdout')
    (folder/'logs/program.stderr').write_bytes(b'')
    (folder/'logs/program.json').write_text(json.dumps({'returncode':0}))
    (folder/'after/ACCTFILE').write_bytes(str(target).encode())
    return dict(status='executed',returncode=0,outputs={'ACCTFILE':str(target)},stdout_sha256='stdout',stderr_sha256='stderr')


class RetentionTests(unittest.TestCase):
    def test_no_kill_leaves_only_hashes_and_no_case_directory(self):
        with tempfile.TemporaryDirectory() as d:
            r=Retention(Path(d)/'retention')
            result=paired_case(r,'same','same','case',1,False,fake,targeted_outcome)
            self.assertEqual('survived',result['status'])
            self.assertFalse(result['actual']['retained'])
            self.assertTrue(result['actual']['files']['after/ACCTFILE']['sha256'])
            self.assertEqual([],list(r.cas.iterdir()))
            self.assertEqual(2,len(list(r.root.glob('run-*.json'))))
            self.assertEqual([],list(r.root.glob('case-*')))

    def test_first_kill_retains_witness_bytes_once_compressed(self):
        with tempfile.TemporaryDirectory() as d:
            r=Retention(Path(d)/'retention')
            result=paired_case(r,'original','mutant','case',1,False,fake,targeted_outcome)
            self.assertEqual('killed-divergent',result['status'])
            blob=result['actual']['files']['after/ACCTFILE']['blob']
            self.assertEqual(b'mutant',gzip.decompress((r.root/blob).read_bytes()))
            stdout=result['actual']['files']['logs/program.stdout']['blob']
            self.assertEqual(stdout,result['baseline']['files']['logs/program.stdout']['blob'])
            count=len(list(r.cas.iterdir()))
            later=paired_case(r,'original','mutant','case2',2,True,fake,targeted_outcome)
            self.assertFalse(later['actual']['retained']);self.assertEqual(count,len(list(r.cas.iterdir())))
            r.seal('a'*40);verify_retention(r.root,'a'*40)
            with self.assertRaisesRegex(ValueError,'head-mismatch'):verify_retention(r.root,'b'*40)
            (r.root/blob).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'inventory-mismatch'):verify_retention(r.root,'a'*40)

    def test_both_fixed_samples_and_every_refusal_retained(self):
        with tempfile.TemporaryDirectory() as d:
            r=Retention(Path(d)/'retention')
            for index in (0,199):
                result=paired_case(r,'same','same','case',index,False,fake,targeted_outcome)
                self.assertIn('fixed-sample',result['actual']['retention_reasons'])
            def refused(target,name,folder):
                fake(target,name,folder)
                return {'status':'execution-refusal','error_type':'TimeoutExpired'}
            result=paired_case(r,'base','mutant','case',3,False,refused,targeted_outcome)
            self.assertEqual('baseline-refusal',result['status'])
            self.assertTrue(result['actual']['retained']);self.assertTrue(result['baseline']['retained'])
            self.assertEqual([],list(r.root.glob('case-*')))
            with self.assertRaises(FileExistsError):Retention(r.root)

    def test_shards_require_exact_cover_and_same_head(self):
        def record(index):
            ids=['a','b'][index::2]
            return dict(head='h',job='INTCALC',shard=index,shards=2,population=['a','b'],selected=ids,
                        results=[dict(id=i,targeted_cases=200) for i in ids],fresh=[],diversity={},current={'after_faults':{}},census={})
        records=[record(0),record(1)]
        with patch('tools.aggregate_equivalence_shards.population',return_value={'a':{},'b':{}}):
            self.assertEqual(2,len(validate_shards(records,'INTCALC','h',2)))
            for bad in ([records[0]], [records[0],records[0]]):
                with self.assertRaisesRegex(ValueError,'missing-or-duplicate'):validate_shards(bad,'INTCALC','h',2)
            records[1]['head']='old'
            with self.assertRaisesRegex(ValueError,'binding'):validate_shards(records,'INTCALC','h',2)
            records[1]['head']='h';records[1]['results'][0]['targeted_cases']=199
            with self.assertRaisesRegex(ValueError,'incomplete'):validate_shards(records,'INTCALC','h',2)


class MarginTests(unittest.TestCase):
    def test_live_disk_check_refuses_before_campaign_and_records_measurement(self):
        from tools.check_retention_margin import check
        from collections import namedtuple
        import io
        from contextlib import redirect_stdout
        disk=namedtuple('disk','total used free')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'/'preflight.json'
            with patch('tools.check_retention_margin.current_binding',return_value={'head':'h'}),patch('tools.check_retention_margin.shutil.disk_usage',return_value=disk(100,99,1)),redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,'below-twofold'):check('POSTTRAN',out)
            self.assertEqual(1,json.loads(out.read_text())['free_disk_bytes'])
            with patch('tools.check_retention_margin.current_binding',return_value={'head':'h'}),patch('tools.check_retention_margin.shutil.disk_usage',return_value=disk(10**12,0,10**12)),redirect_stdout(io.StringIO()):check('POSTTRAN',out)
            self.assertGreaterEqual(json.loads(out.read_text())['disk_headroom'],2)

    def test_final_phase_inventory_is_separate(self):
        from tools.measure_campaign_resources import measure
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'campaign';root.mkdir();(root/'fresh').write_bytes(b'12345')
            target=root/'equivalence-followup';target.mkdir();(target/'target').write_bytes(b'123')
            out=Path(d)/'resources.json'
            with redirect_stdout(io.StringIO()):measure(root,out)
            result=json.loads(out.read_text())
            self.assertEqual((5,3,8),(result['fresh_compiled_bytes'],result['targeted_bytes'],result['total_bytes']))
