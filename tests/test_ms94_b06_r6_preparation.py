"""Offline preparation tests; no native or Docker execution."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from lightyear_calibration.contracts import canonical,read_json,seal
from tools.ms94_b06_private_assembly import required,seal_inputs,verify_assembly
from tools.ms94_b06_revision_r6 import apply_revisions,APPLIES_TO


class PreparationTests(unittest.TestCase):
    def test_seal_complete_inputs_rejects_missing_or_tampered_files_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'inputs'
            files={n:canonical(seal({'fixture':True})) for n in required('J1')}
            files['operations.java']=b'public synthetic fixture'
            slot={'id':'smoke-001','source':{'sha256':hashlib.sha256(files['operations.java']).hexdigest()},'control':'retained-reference'}
            with self.assertRaisesRegex(ValueError,'incomplete'):
                seal_inputs(root,'J1',[slot],{slot['id']:{k:v for k,v in files.items() if k!='checkpoint.json'}})
            self.assertFalse(root.exists())
            record=seal_inputs(root,'J1',[slot],{slot['id']:files})
            self.assertTrue(verify_assembly(root,record))
            with self.assertRaisesRegex(ValueError,'no-replacement'):seal_inputs(root,'J1',[slot],{slot['id']:files})
            (root/'blobs'/slot['source']['sha256']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bound-file-changed'):verify_assembly(root,record)

    def test_explicit_control_selects_correction_regardless_of_reason_text(self):
        revisions=[{'original_sha256':str(n)*64,'revised_sha256':sha,'reason':'duplicate-trace invented editorial text'}
                   for n,sha in enumerate(APPLIES_TO,1)]
        schedule=[];sources={}
        for revision in revisions:
            old,new=revision['original_sha256'],revision['revised_sha256']
            for label in ('retained-reference',APPLIES_TO[new]):
                schedule.append({'id':str(len(schedule)),'control':label,'source':{'sha256':old},'expected':{}})
            for sha in (old,new):sources[sha]={'catalog':seal({'source_sha256':sha,'compilation_record_sha256':'c'*64})}
        changed,records=apply_revisions(schedule,revisions,{'sources':sources})
        self.assertEqual(4,len(records))
        self.assertTrue(all(r['applies_to_control'] in APPLIES_TO.values() for r in records))
        for old,new in zip(schedule,changed):
            self.assertEqual(old['control']=='retained-reference',old['source']['sha256']==new['source']['sha256'])
        other=copy.deepcopy(revisions)
        for r in other:r['reason']='No words related to the implementation'
        self.assertEqual(changed,apply_revisions(schedule,other,{'sources':sources})[0])

    def test_saved_private_manifests_bind_all_135_slots_and_four_corrected_sources(self):
        area=Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-ms94/stage-b-06/preparation/execution-r6'
        seen=set()
        for j,count in [('j1',55),('j2',41),('j3',39)]:
            d=read_json(area/(j+'-assembly-v6.json'));m=read_json(area/(j+'-private-inputs.json'))
            self.assertEqual(count,len(d['schedule']));self.assertEqual(m['content_sha256'],d['private_assembly_sha256'])
            self.assertEqual({s['id'] for s in d['schedule']},set(m['slots']))
            for s in d['schedule']:
                self.assertEqual(s['source']['sha256'],m['slots'][s['id']]['inputs_sha256']['operations.java'])
                self.assertTrue(required(j.upper())<=set(m['slots'][s['id']]['inputs_sha256']))
                seen.add(s['source']['sha256'])
        self.assertTrue(set(APPLIES_TO)<=seen)
