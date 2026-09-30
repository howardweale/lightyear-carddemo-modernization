import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import CalibrationError, seal, read_json
from lightyear_calibration.journey_order import save, file_hash
from tools.ms94_invoice_type_v5 import check_rows, PUBLIC
from tools.ms94_controller_v5 import public_prompt
from tools.ms94_builder_mcp_v5 import RecordedTools
from tools.ms94_v5_gate import evaluate, VERSION
from tools.ms94_measure_v5 import decision, interval, prepare

ROOT=Path(__file__).resolve().parents[1]


class InvoiceTypeContract(unittest.TestCase):
    def test_host_authority_signs_without_snapshot_private_key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from tools.ms94_signer_v5 import JourneySigner
        from lightyear_control_tower.decisions import verify_envelope
        with tempfile.TemporaryDirectory() as tmp:
            host=Path(tmp).resolve();root=host/'work/ms94/execution-snapshots/test'
            authority=host/'work/ms87/operator';public=root/'work/ms87/operator'
            authority.mkdir(parents=True);public.mkdir(parents=True)
            key=Ed25519PrivateKey.generate()
            (authority/'authority.key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
            (authority/'authority.public.pem').write_bytes(pub);(public/'authority.public.pem').write_bytes(pub)
            save(root/'execution-snapshot.json',seal({'execution_root':str(root),'source_root_for_provenance_only':str(host)}))
            self.assertTrue(verify_envelope(JourneySigner(root).sign({'test':'in-place'}),pub))
            self.assertFalse((public/'authority.key.pem').exists())
            (public/'authority.key.pem').write_text('forbidden')
            with self.assertRaises(CalibrationError):JourneySigner(root)

    def test_relationship_not_fixture_id_and_both_fields_required(self):
        types=[{'c_doctype_id':801,'c_doctypeinvoice_id':904},{'c_doctype_id':904},{'c_doctype_id':905}]
        order={'c_doctype_id':801}
        self.assertEqual(check_rows(order,{'c_doctypetarget_id':904,'c_doctype_id':904},types),[])
        for target,actual,expected in [(905,904,['c_doctypetarget_id']),(904,905,['c_doctype_id']),
                                       (905,905,['c_doctypetarget_id','c_doctype_id'])]:
            self.assertEqual(check_rows(order,{'c_doctypetarget_id':target,'c_doctype_id':actual},types),expected)

    def test_missing_ambiguous_or_unconfigured_relationship_is_equipment_error(self):
        order={'c_doctype_id':1};invoice={'c_doctypetarget_id':2,'c_doctype_id':2}
        for types in [[],[{'c_doctype_id':1,'c_doctypeinvoice_id':0}],
                      [{'c_doctype_id':1,'c_doctypeinvoice_id':2}],
                      [{'c_doctype_id':1,'c_doctypeinvoice_id':2}]*2+[{'c_doctype_id':2}]]:
            with self.assertRaises(CalibrationError):check_rows(order,invoice,types)

    def test_prompt_and_tool_expose_same_new_rule_without_other_contract_changes(self):
        new=public_prompt(ROOT)['public_shapes'];old=read_json(ROOT/'factory/idempiere/qualification-ms94-v3/public/operations-shapes.json')
        self.assertEqual(new['requirements'][:-1],old['requirements'])
        self.assertIn('C_DocTypeInvoice_ID',new['requirements'][-1])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for folder in ['factory/idempiere/qualification-ms94-v3/public',str(PUBLIC)]:
                import shutil
                shutil.copytree(ROOT/folder,root/folder)
            save(root/'work/ms87/local-runtime.json',{'runner_image':'sha256:'+'1'*64})
            tools=RecordedTools(root,3,'unit-retention')
            self.assertEqual(tools.call('public_contract',{'scenario':'operations'})['shapes'],new)

    def test_old_declaration_is_not_rejudged(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);save(run/'plan.json',seal({'judge_version':'old','scenario':'operations'}))
            (run/'gate.json').write_text('preserve this outcome')
            with self.assertRaises(CalibrationError):evaluate(run)
            self.assertEqual((run/'gate.json').read_text(),'preserve this outcome')

    def test_extension_rejects_and_preserves_prior_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);save(run/'inputs/invoice-type-contract.json',seal({'version':'test'}))
            save(run/'plan.json',seal({'judge_version':VERSION,'scenario':'operations','inputs_sha256':{
                'invoice-type-contract.json':file_hash(run/'inputs/invoice-type-contract.json')}}))
            for status in ['passed','business-failure','execution-failure','judge-error','insufficient-evidence']:
                base=seal({'status':status,'passed':status=='passed','checks':{'combined':{}}})
                with patch('tools.ms94_v5_gate.base_evaluate',return_value=base),patch('tools.ms94_v5_gate.invoice_type',return_value={'passed':False}) as check:
                    got=evaluate(run)
                    self.assertEqual(got['status'],'business-failure' if status in ('passed','business-failure') else status)
                    self.assertEqual(check.called,status in ('passed','business-failure'))
            with patch('tools.ms94_v5_gate.base_evaluate',return_value=seal({'status':'passed','passed':True,'checks':{'combined':{}}})),patch('tools.ms94_v5_gate.invoice_type',side_effect=CalibrationError('bad evidence')):
                self.assertEqual(evaluate(run)['status'],'judge-error')

    def test_twenty_trial_schedule_budget_and_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);output=root/'campaign'
            def trial(root,path,executable,equipment):
                value=seal({'source_transfer':{'database_rows':False}});save(path/'plan.json',value);return value
            with patch('tools.ms94_measure_v5.controller.stage_a'),patch('tools.ms94_measure_v5.controller.prepare',side_effect=trial),patch('tools.ms94_measure_v5.JourneySigner') as signer:
                signer.return_value.sign.side_effect=lambda x:seal(x)
                plan=prepare(root,output,Path('exe'),Path('equipment'))
            self.assertEqual([s['phase'] for s in plan['slots']],['pilot']*3+['cohort']*20)
            self.assertEqual((plan['max_client_invocations'],plan['max_compilations'],plan['max_elapsed_seconds']),(115,69,26*3600))
            self.assertEqual(decision(2,10),'incomplete-no-rate')
            self.assertEqual(decision(20,20,True),'void-equipment-failure-no-rate')
            self.assertAlmostEqual(interval(4,20)['lower'],0.08065766,places=6)


if __name__=='__main__':unittest.main()
