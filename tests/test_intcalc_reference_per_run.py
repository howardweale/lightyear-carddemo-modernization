"""Synthetic contract tests; no Docker, compiler, network or seed."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import intcalc_reference_per_run as q

ROOT=Path(__file__).resolve().parents[1]
H='a'*64


class QualificationTests(unittest.TestCase):
    def fixtures(self):
        spec=dict(id='probe',exit_code=0,stdout_hex='6162',stderr_hex='')
        probe=q.provisional.probe_result(spec,0,b'ab',b'',[])
        case=dict(id='PC-01',hand_exit=0,hand_outputs={},python_findings=[])
        pairs=[]
        for name in ('reference-hand','reference-python','hand-python'):
            channels={c:dict(status='MATCH') for c in ('ACCTFILE','TRANSACT','stdout','stderr','exit','success_class')}
            if name=='reference-hand':channels['success_class']=dict(status='NOT_COMPARED')
            else:
                for c in ('stdout','stderr','exit'):channels[c]=dict(status='NOT_MODELLED')
            pairs.append(dict(pair=name,channels=channels))
        report=dict(request_sha256=H,public_suite_sha256=H,package_library_sha256=H,
                    probes=[probe],cases=[dict(id='PC-01',compare_output_files=True,comparisons=pairs)])
        row=dict(public_suite_sha256=H,package_library_sha256=H)
        return report,row,dict(cases=[case]),[spec],dict(reference_findings=[])

    def attested(self,items):
        report,row,suite,probes,source=items
        return q.attest(report,row,H,suite,probes,source)

    def test_pinned_binding_joins_real_public_sources(self):
        with patch.dict(os.environ,GITHUB_ACTIONS='true'):
            row,digest,req,suite,probes,source=q.load_binding()
        self.assertEqual(len(suite['cases']),16)
        self.assertEqual(len(probes),9)
        self.assertIn(q.BUILD_LIMIT,row['named_limits'])
        self.assertFalse(row['image_publication'])
        self.assertFalse(row['hidden_freeze'])

    def test_complete_synthetic_criterion(self):
        self.assertTrue(self.attested(self.fixtures()))

    def test_source_join_tamper_refuses(self):
        items=self.fixtures();items[0]['request_sha256']='b'*64
        with self.assertRaisesRegex(q.ref.Refused,'qualification-join'):self.attested(items)

    def test_missing_case_and_duplicate_probe_refuse(self):
        for key in ('cases','probes'):
            items=self.fixtures();items[0][key]=[]
            with self.subTest(key=key),self.assertRaises(q.ref.Refused):self.attested(items)

    def test_false_summary_cannot_hide_reference_difference(self):
        items=self.fixtures();items[0]['comparison_criterion_met']=True
        items[0]['cases'][0]['comparisons'][0]['channels']['stdout']['status']='DIFFERENT'
        self.assertFalse(self.attested(items))

    def test_python_difference_blocks_without_exact_registration(self):
        items=self.fixtures();items[0]['cases'][0]['comparisons'][1]['channels']['ACCTFILE']['status']='DIFFERENT'
        self.assertFalse(self.attested(items))

    def test_registered_python_difference_is_not_a_raw_match(self):
        items=self.fixtures();diff={'left_success':True,'right_success':False};digest=q.ref.sha(q.ref.canonical(diff))
        items[0]['cases'][0]['comparisons'][1]['channels']['success_class']=dict(status='PREREGISTERED_FINDING',difference=diff,difference_sha256=digest,findings=['O4'])
        items[2]['cases'][0]['python_findings']=[dict(finding='O4',pair='reference-python',channel='success_class',difference_sha256=digest)]
        self.assertTrue(self.attested(items))
        items[0]['cases'][0]['comparisons'][1]['channels']['success_class']['difference']['right_success']=True
        with self.assertRaisesRegex(q.ref.Refused,'qualification-python-finding'):self.attested(items)

    def test_reference_hand_cannot_be_waived(self):
        items=self.fixtures();items[0]['cases'][0]['comparisons'][0]['channels']['ACCTFILE']['status']='PREREGISTERED_FINDING'
        with self.assertRaisesRegex(q.ref.Refused,'qualification-reference-hand'):self.attested(items)

    def test_python_stdout_is_not_modelled(self):
        items=self.fixtures();items[0]['cases'][0]['comparisons'][1]['channels']['stdout']['status']='MATCH'
        with self.assertRaisesRegex(q.ref.Refused,'qualification-python-policy'):self.attested(items)

    def test_probe_summary_tamper_refuses(self):
        items=self.fixtures();items[0]['probes'][0]['stdout_hex']='6364'
        with self.assertRaisesRegex(q.ref.Refused,'qualification-probe-readback'):self.attested(items)

    def test_changed_probe_output_is_discrepancy(self):
        items=self.fixtures();items[0]['probes'][0]=q.provisional.probe_result(items[3][0],0,b'cd',b'',[])
        self.assertFalse(self.attested(items))

    def approval(self):
        r=dict(source_commit='1'*40,source_tree='2'*40,binding_sha256=H)
        a=dict(schema='reference-adoption-and-public-freeze/1',authority='Howard',source_commit=r['source_commit'],source_tree=r['source_tree'],binding_sha256=H,qualification_sha256=H,adopt_reference=True,authorize_public_freeze=True,scope='PC-01..PC-16 only; no hidden set')
        return r,a

    def test_freeze_needs_exact_separate_operator_approval(self):
        r,a=self.approval();raw=q.ref.canonical(a)
        q.approve(r,H,H,a,q.ref.sha(raw),raw)
        with self.assertRaisesRegex(q.ref.Refused,'freeze-approval-hash'):q.approve(r,H,H,a,'0'*64,raw)

    def test_adoption_alone_is_not_freeze_authority(self):
        r,a=self.approval();a['authorize_public_freeze']=False;raw=q.ref.canonical(a)
        with self.assertRaisesRegex(q.ref.Refused,'freeze-approval-join'):q.approve(r,H,H,a,q.ref.sha(raw),raw)

    def test_different_source_or_receipt_invalidates_approval(self):
        for key in ('source_commit','source_tree','qualification_sha256','binding_sha256'):
            r,a=self.approval();a[key]='b'*len(a[key]);raw=q.ref.canonical(a)
            with self.subTest(key=key),self.assertRaises(q.ref.Refused):q.approve(r,H,H,a,q.ref.sha(raw),raw)

    def test_no_local_execution_or_automatic_freeze(self):
        with patch.dict(os.environ,GITHUB_ACTIONS='false'),patch.object(q.container,'execute') as run:
            with self.assertRaisesRegex(q.ref.Refused,'qualification-main-ci-only'):q.qualify('sha256:'+H,Path('unused'))
            with self.assertRaisesRegex(q.ref.Refused,'freeze-main-ci-only'):q.freeze(Path('unused'),Path('unused'),Path('unused'),H)
            run.assert_not_called()

    def test_observation_inventory_requires_every_fixed_public_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for name in ('report.json','inventory.json','container-cleanup.json'):(p/name).write_bytes(b'{}')
            rows=q.observation_inventory(p,dict(cases=[]),[])
            self.assertEqual(len(rows),3)
            with self.assertRaisesRegex(q.ref.Refused,'qualification-file'):q.observation_inventory(p,dict(cases=[]),[dict(id='probe')])

    def test_missing_file_refuses_without_paths(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(q.ref.Refused,'^qualification-file$'):q.read(Path(td)/'private-sentinel')


    def freeze_fixture(self,root):
        report,row,suite,probes,source=self.fixtures()
        evidence=root/'evidence';evidence.mkdir()
        case=suite['cases'][0]
        case['hand_outputs']={c:dict(path=c,sha256=q.ref.sha(b'')) for c in ('ACCTFILE','TRANSACT','stdout','stderr')}
        for name,value in [('report.json',report),('inventory.json',{}),('container-cleanup.json',dict(removed_and_absent=True))]:
            (evidence/name).write_bytes(q.ref.canonical(value))
        for label in ('reference','python','hand'):
            folder=evidence/'public/PC-01/observations'/label;folder.mkdir(parents=True)
            for c in case['hand_outputs']:(folder/c).write_bytes(b'')
        (evidence/'public/PC-01/observations/reference/stderr.raw').write_bytes(b'')
        folder=evidence/'public/probe-probe/observations';folder.mkdir(parents=True)
        (folder/'stdout').write_bytes(b'ab');(folder/'stderr').write_bytes(b'')
        receipt,approval=self.approval()
        receipt.update(schema='intcalc-reference-qualification/1',comparison_criterion_met=True,status='CRITERION_MET',named_limits=q.LIMITS,observations=q.observation_inventory(evidence,suite,probes))
        raw=q.ref.canonical(receipt);(evidence/'qualification.json').write_bytes(raw)
        approval['qualification_sha256']=q.ref.sha(raw);araw=q.ref.canonical(approval)
        ap=root/'approval.json';ap.write_bytes(araw)
        row['request']=dict(sha256=H)
        loaded=(row,H,dict(suite=dict(path='unused/SUITE.json')),suite,probes,source)
        return evidence,ap,q.ref.sha(araw),loaded

    def test_public_freeze_writes_verified_manifest_last(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);evidence,approval,digest,loaded=self.freeze_fixture(root)
            with patch.dict(os.environ,GITHUB_ACTIONS='true',GITHUB_REF='refs/heads/main'),patch.object(q,'load_binding',return_value=loaded),patch.object(q,'identity',return_value=('1'*40,'2'*40)),patch.object(q.provisional,'inventory_digest',return_value=H),patch.object(q.ref,'joined',return_value=b''):
                self.assertEqual(q.freeze(evidence,root/'frozen',approval,digest),0)
                manifest=json.loads((root/'frozen/MANIFEST.json').read_bytes())
                self.assertEqual(manifest['visibility'],'public');self.assertEqual(len(manifest['files']),5)
                for entry in manifest['files']:self.assertEqual(q.ref.sha((root/'frozen'/entry['path']).read_bytes()),entry['sha256'])
                with self.assertRaisesRegex(q.ref.Refused,'fresh-destination'):q.freeze(evidence,root/'frozen',approval,digest)

    def test_changed_observation_refuses_before_freeze_write(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);evidence,approval,digest,loaded=self.freeze_fixture(root)
            (evidence/'public/PC-01/observations/reference/ACCTFILE').write_bytes(b'changed')
            with patch.dict(os.environ,GITHUB_ACTIONS='true',GITHUB_REF='refs/heads/main'),patch.object(q,'load_binding',return_value=loaded),patch.object(q,'identity',return_value=('1'*40,'2'*40)):
                with self.assertRaisesRegex(q.ref.Refused,'freeze-observations'):q.freeze(evidence,root/'frozen',approval,digest)
            self.assertFalse((root/'frozen').exists())


if __name__=='__main__':unittest.main()
