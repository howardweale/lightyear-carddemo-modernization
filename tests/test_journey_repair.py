"""Adversarial repair-boundary tests; fixtures are never native evidence."""
import copy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lightyear_calibration.journey_repair import compile_diagnostics,select_feedback,cost_report,check_client,invoke,diagnostics,public_api_matches,boolean_api_evidence,analyst_schema,analyst_prompt
from lightyear_calibration.journey_order import save
from lightyear_calibration.journey_campaign import check_hashes
from lightyear_calibration.journey_campaign import propose_resume,accept_resume
from lightyear_calibration.contracts import seal,read_json
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_calibration.journey_order import RUNS,file_hash
from lightyear_calibration.journey_contracts import CONTRACT,current_contract,record_timestamp_acceptance


class RepairBoundaryTests(unittest.TestCase):
    def test_tycho_compile_error_does_not_forward_source_or_expected_values(self):
        log='''[ERROR] /application/LightyearPartialInvoiceTest.java:[51]
[ERROR] String error = Doc.postImmediate(secretExpectedTotal("58.04"));
[ERROR]                    ^^^^^^^^^^^^^
[ERROR] The method postImmediate(MAcctSchema[], int, int, boolean, String) in the type Doc is not applicable for the arguments (Properties, int, int, int, boolean, String)
[ERROR] expected: <58.04> but was: <999.99>
'''
        result=compile_diagnostics(log)
        self.assertEqual('postImmediate',result[0]['symbol'])
        self.assertEqual(51,result[0]['line'])
        self.assertNotIn('58.04',json.dumps(result));self.assertNotIn('999.99',json.dumps(result))
        self.assertNotIn('secretExpectedTotal',json.dumps(result))

    def test_money_assertions_and_arbitrary_compiler_text_are_not_feedback(self):
        self.assertEqual([],compile_diagnostics('AssertionFailedError: expected: <58.04> but was: <999>'))
        self.assertEqual([],compile_diagnostics('LightyearPartialInvoiceTest.java:[6,9] EXPECTED_SECRET=42'))
        self.assertEqual([],compile_diagnostics('LightyearPartialInvoiceTest.java:[6,9] incompatible types: "SECRET42" cannot be converted to int'))

    def test_visibility_failure_remains_distinct_from_wrong_parameter_types(self):
        prefix='[ERROR] LightyearPartialInvoiceTest.java:[55]\n[ERROR] source deliberately omitted\n[ERROR] '
        hidden=compile_diagnostics(prefix+'The method postDocument(MAcctSchema[], int, int, boolean, boolean, boolean, String) from the type DocManager is not visible')
        self.assertEqual('method-not-visible',hidden[0]['code'])
        self.assertEqual('DocManager',hidden[0]['declaring_type'])
        self.assertEqual('MAcctSchema[]',hidden[0]['parameter_types'][0])
        mismatch=compile_diagnostics(prefix+'The method postImmediate(MAcctSchema[], int, int, boolean, String) in the type Doc is not applicable for the arguments (Properties, int, int, int, boolean, String)')
        self.assertEqual('Properties',mismatch[0]['argument_types'][0])
        missing=compile_diagnostics(prefix+'The method postImmediate(MAcctSchema[], int, int, boolean, String) is undefined for the type DocManager')
        self.assertEqual('method-undefined',missing[0]['code'])
        self.assertEqual('DocManager',missing[0]['declaring_type'])

    def test_api_declaration_lookup_uses_pinned_source_and_exports_no_method_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);path=root/'work/idempiere-upstream/org.adempiere.base/src/org/compiere/acct/Doc.java'
            path.parent.mkdir(parents=True);path.write_text('public static String postImmediate (MAcctSchema[] ass, int id) { return "PRIVATE_EXPECTATION_999"; }')
            matches=public_api_matches(root,'postImmediate',{'doc_sha256':file_hash(path)})
            self.assertEqual('org.compiere.acct.Doc',matches[0]['declaring_type'])
            self.assertEqual(['MAcctSchema[]','int'],matches[0]['parameter_types'])
            self.assertNotIn('PRIVATE_EXPECTATION',json.dumps(matches))
            path.write_text('changed')
            with self.assertRaises(ValueError):public_api_matches(root,'postImmediate',{'doc_sha256':'0'*64})

    def test_analyst_cannot_add_prose_new_diagnostics_or_values(self):
        observations=[{'id':'diagnostic-1','category':'outside-footprint','table':'t_fact_acct_history','call':'Doc.postImmediate'}]
        self.assertEqual(observations,select_feedback(observations,{'diagnostic_ids':['diagnostic-1']}))
        for proposal in ({'diagnostic_ids':['new-id']},{'diagnostic_ids':['diagnostic-1'],'hint':'total is 58.04'},
                         {'diagnostic_ids':['diagnostic-1','diagnostic-1']}):
            with self.assertRaises(ValueError):select_feedback(observations,proposal)

    def test_api_mismatch_and_footprint_expose_structure_not_observed_values(self):
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp);folder=run/'cases/partial-invoicing/1'
            log=folder/'execution/oracle/maven.log';log.parent.mkdir(parents=True)
            log.write_text('AssertionFailedError: expected <SECRET> but was <PRIVATE>\n at test.post(LightyearPartialInvoiceTest.java:1)')
            for path in (folder/'baseline/oracle/entry/state.json',folder/'after/oracle/state.json'):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
            code='assertEquals("Y", model.get_ValueAsString("Posted"));\nDoc.postImmediate(...);'
            def state(path,lane):
                return {'tables':{'t_fact_acct_history':{'row_multiset':{'before' if 'baseline' in path.parts else 'after':37}},
                    'unrecognized_table':{'row_multiset':{'before' if 'baseline' in path.parts else 'after':9001}}}}
            with patch('lightyear_calibration.native_reconciliation.state',side_effect=state),patch('lightyear_calibration.journey_repair.boolean_api_evidence',return_value={'fixture':'public API type only'}):
                result=diagnostics(run,code,{'po_sha256':'a'*64,'doc_sha256':'b'*64})
            self.assertEqual({'api-type-mismatch','outside-footprint'},{d['category'] for d in result})
            encoded=json.dumps(result)
            for secret in ('SECRET','PRIVATE','37','9001','unrecognized_table'):
                self.assertNotIn(secret,encoded)
            self.assertIn('Doc.deleteAcct',encoded)

    def test_reasoned_analyst_selection_is_complete_and_cannot_inject_a_patch(self):
        observations=[{'id':'diagnostic-1','category':'api-type-mismatch'}]
        decision={'diagnostic_id':'diagnostic-1','disposition':'forward','reason':'supported-structural-defect'}
        self.assertEqual(observations,select_feedback(observations,{'decisions':[decision]},True))
        rejection={**decision,'disposition':'reject','reason':'insufficient-type-evidence'}
        self.assertEqual([],select_feedback(observations,{'decisions':[rejection]},True))
        for invalid in ({'diagnostic_ids':[]},{'decisions':[]},{'decisions':[decision,decision]},
                        {'decisions':[{**decision,'patch':'PRIVATE_VALUE'}]},
                        {'decisions':[{**decision,'disposition':'reject'}]}):
            with self.assertRaises(ValueError):select_feedback(observations,invalid,True)
        self.assertEqual(['decisions'],analyst_schema(observations)['required'])
        self.assertEqual(2,analyst_prompt(observations,'candidate',{},None)['diagnostic_contract_version'])

    def test_boolean_proof_comes_from_pinned_source_not_a_type_assertion(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);po=root/'work/idempiere-upstream/org.adempiere.base/src/org/compiere/model/PO.java'
            po.parent.mkdir(parents=True)
            po.write_text('public String get_ValueAsString(int idx) {\n return value.toString();\n\t}\npublic boolean get_ValueAsBoolean(String columnName) {\n if (oo instanceof Boolean) return ((Boolean)oo).booleanValue();\n\t}\n')
            generated='public void setPosted (boolean Posted) {\n set_Value (COLUMNNAME_Posted, Boolean.valueOf(Posted));\n\t}\npublic boolean isPosted() {\n if (oo instanceof Boolean) return ((Boolean)oo).booleanValue();\n\t}\n'
            api={'po_sha256':file_hash(po),'source_commit':'a'*40}
            with patch('lightyear_calibration.journey_repair.subprocess.run',side_effect=[
                SimpleNamespace(stdout=b'public class MInvoice extends X_C_Invoice {}'),
                SimpleNamespace(stdout=generated.encode())]) as git:
                proof=boolean_api_evidence(root,'MInvoice invoice;',api)
                self.assertEqual('boolean',proof['models'][0]['java_type'])
                self.assertIn('value.toString()',proof['string_accessor_source'])
                self.assertIn('a'*40+':org.adempiere.base/src/org/compiere/model/X_C_Invoice.java',git.call_args.args[0])
            po.write_text('changed')
            with self.assertRaisesRegex(ValueError,'source changed'):boolean_api_evidence(root,'MInvoice invoice;',api)

    def test_type_diagnostic_points_to_accessor_and_retains_separate_failure_location(self):
        with tempfile.TemporaryDirectory() as temp:
            run=Path(temp);log=run/'cases/partial-invoicing/1/execution/oracle/maven.log'
            log.parent.mkdir(parents=True);log.write_text('expected <PRIVATE_AMOUNT> but was <SECRET_AMOUNT>\n at test.post(LightyearPartialInvoiceTest.java:4)')
            source='private void post(PO model) {\n if (!"Y".equals(model.get_ValueAsString("Posted"))) {\n int x=0;\n assertEquals(0,x);\n }\n}'
            with patch('lightyear_calibration.journey_repair.boolean_api_evidence',return_value={'fixture':'public types'}):
                result=diagnostics(run,source,{'po_sha256':'a'*64})
                self.assertEqual(2,result[0]['line']);self.assertEqual(4,result[0]['failure_frame_line'])
                self.assertEqual('String',result[0]['accessor_return_type'])
                self.assertNotIn('PRIVATE_AMOUNT',json.dumps(result));self.assertNotIn('SECRET_AMOUNT',json.dumps(result))
                log.write_text('at test.other(LightyearPartialInvoiceTest.java:8)')
                self.assertEqual([],diagnostics(run,source+'\nprivate void other() {\n assertTrue(false);\n}',{'po_sha256':'a'*64}))

    def test_hash_and_client_preconditions_refuse_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'judge.py').write_text('fixed')
            with self.assertRaises(ValueError):check_hashes(root,{'judge.py':'0'*64})
        with patch('lightyear_calibration.journey_repair.client_identity',return_value={'version':'changed','sha256':'a'}):
            with self.assertRaises(ValueError):check_client(Path('client'),{'version':'pinned','sha256':'b'})

    def test_accounting_includes_both_roles_and_failed_native_and_transport_attempts(self):
        calls=[{'role':'builder','usage':{'input_tokens':10,'output_tokens':4},'elapsed_seconds':2,'error':None},
               {'role':'analyst','usage':{'input_tokens':3,'output_tokens':1},'elapsed_seconds':1,'error':None},
               {'role':'builder','usage':None,'elapsed_seconds':7,'error':'timeout'}]
        cost=cost_report(calls,[{'passed':False,'elapsed_seconds':20},{'passed':True,'elapsed_seconds':30}],70)
        self.assertEqual(3,cost['client_invocations']);self.assertEqual(13,cost['input_tokens'])
        self.assertEqual(1,cost['failed_native_attempts']);self.assertEqual(1,cost['failed_client_invocations'])
        self.assertFalse(cost['usage_complete']);self.assertEqual(1,cost['calls_with_unknown_usage'])
        self.assertIsNone(cost['billed_usd']);self.assertEqual(50,cost['native_elapsed_seconds'])

    def test_failed_spawn_is_signed_and_charged_before_transport(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);campaign=root/'campaign';campaign.mkdir()
            save(campaign/'plan.json',{'builder_client':{},'content_sha256':'fixture','max_client_invocations':1,'client_timeout_seconds':1})
            with patch('lightyear_calibration.journey_repair.check_client'),patch('lightyear_calibration.journey_repair.subprocess.Popen',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):invoke(root,campaign,Path('missing'),'builder',{}, {})
                self.assertTrue((campaign/'calls/001-builder/invocation.json').exists())
                receipt=json.loads((campaign/'calls/001-builder/receipt.json').read_text())
                self.assertEqual('OSError',receipt['error']);self.assertIsNone(receipt['usage'])
                with self.assertRaisesRegex(ValueError,'budget exhausted'):invoke(root,campaign,Path('missing'),'builder',{}, {})

    def test_timestamp_acceptance_is_owned_scoped_expiring_and_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);e=root/'docs/calibration/idempiere-boundaries/receipt.json';e.parent.mkdir(parents=True);e.write_text('{}')
            value=record_timestamp_acceptance(root,'Howard Weale','2026-12-25')
            self.assertEqual(['adempiere.m_inout.shipdate'],value['scope']['columns'])
            self.assertTrue(current_contract(root,date(2026,9,27))['effective'])
            self.assertFalse(current_contract(root,date(2026,12,25))['effective'])
            with self.assertRaises(ValueError):record_timestamp_acceptance(root,'Howard Weale','2027-01-01')
            value['scope']['columns'].append('all.timestamps');save(root/CONTRACT,value)
            with self.assertRaises(ValueError):current_contract(root,date(2026,9,27))

    def test_resume_proposal_cannot_spend_budget_and_acceptance_preserves_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);campaign=root/'campaign';campaign.mkdir()
            gate=root/'judge.py';gate.write_text('immutable')
            source=root/'src/lightyear_calibration/journey_repair.py';source.parent.mkdir(parents=True);source.write_text('original')
            plan=seal({'builder_client':{},'max_client_invocations':5,'judge_sha256':{'judge.py':file_hash(gate)},
                'public_input_sha256':{},'implementation_sha256':{'judge.py':file_hash(gate),'src/lightyear_calibration/journey_repair.py':file_hash(source)}})
            save(campaign/'plan.json',plan);signer=JourneySigner(root)
            original=signer.sign({'plan_sha256':plan['content_sha256'],'status':'halted-nonrepairable',
                'attempts':[{'run_id':'journey-'+'a'*32,'builder_directory':'build'}]})
            save(campaign/'receipt.json',original);auth=signer.sign({'plan_sha256':plan['content_sha256']});save(campaign/'authorization.json',auth)
            candidate=root/'build/workspace/LightyearPartialInvoiceTest.java';candidate.parent.mkdir(parents=True);candidate.write_text('generated')
            save(root/'factory/idempiere/analyst-repair/api-provenance.json',{})
            source.write_text('structural filter update')
            with patch('lightyear_calibration.journey_campaign.check_client'),patch('lightyear_calibration.journey_campaign.diagnostics',return_value=[{'id':'diagnostic-1','category':'compile-error'}]):
                recheck=propose_resume(root,campaign,Path('fixture'),None,analyst_only=True)
                self.assertEqual(5,recheck['plan']['max_client_invocations'])
                self.assertTrue(recheck['analyst_only'])
                self.assertEqual(original,read_json(campaign/'receipt.json'))
                for number in range(5):save(campaign/f'calls/{number:03d}-fixture/invocation.json',{})
                with self.assertRaisesRegex(ValueError,'No approved call remains'):
                    propose_resume(root,campaign,Path('fixture'),None,analyst_only=True)
                proposal=propose_resume(root,campaign,Path('fixture'),6)
                self.assertEqual(5,read_json(campaign/'plan.json')['max_client_invocations'])
                self.assertEqual(original,read_json(campaign/'receipt.json'))
                with patch('lightyear_calibration.journey_campaign.run_campaign',return_value={'status':'fixture-only'}) as run:
                    accept_resume(root,campaign,Path('fixture'),proposal['content_sha256'])
                    self.assertEqual(1,run.call_count)
            self.assertEqual(6,read_json(campaign/'plan.json')['max_client_invocations'])
            self.assertEqual(original,read_json(campaign/'history'/(original['content_sha256']+'.json')))
            self.assertEqual(auth,read_json(campaign/'history'/(auth['content_sha256']+'.json')))
            self.assertEqual(plan,read_json(campaign/'history'/(plan['content_sha256']+'.json')))

    def test_analyst_only_recheck_cannot_launch_builder_or_native_execution(self):
        from lightyear_calibration.journey_campaign import run_campaign
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);campaign=root/'campaign';campaign.mkdir();signer=JourneySigner(root)
            plan=seal({'prior_receipt_sha256':'old','judge_sha256':{},'builder_client':{}})
            save(campaign/'plan.json',plan)
            save(campaign/'authorization.json',signer.sign({'plan_sha256':plan['content_sha256']}))
            save(campaign/'history/old.json',{'cost':{'total_elapsed_seconds':10}})
            save(root/RUNS/'journey-a/receipt.json',{'error':{'classification':'harness-exception'}})
            save(root/'factory/idempiere/analyst-repair/api-provenance.json',{})
            code=root/'build/workspace/LightyearPartialInvoiceTest.java';code.parent.mkdir(parents=True);code.write_text('generated')
            observations=[{'id':'diagnostic-1','category':'api-type-mismatch'}]
            selection={'decisions':[{'diagnostic_id':'diagnostic-1','disposition':'forward','reason':'supported-structural-defect'}]}
            with patch('lightyear_calibration.journey_campaign.diagnostics',return_value=observations), \
                 patch('lightyear_calibration.journey_campaign.public_prompt',return_value={'api_reference':{}}), \
                 patch('lightyear_calibration.journey_campaign.invoke',return_value=(Path('fixture'),selection)) as client, \
                 patch('lightyear_calibration.journey_campaign.execute_native') as native, \
                 patch('lightyear_calibration.journey_campaign.apply_candidate') as builder, \
                 patch('lightyear_calibration.journey_campaign.audit_repair_provenance',return_value={'human_authored_repair_bytes':0}):
                result=run_campaign(root,campaign,Path('client'),resume_attempts=[{'run_id':'journey-a','builder_directory':'build','passed':False,'elapsed_seconds':1}],analyst_only=True)
            self.assertEqual('repair-feedback-ready',result['status'])
            self.assertEqual(1,client.call_count);self.assertEqual('analyst',client.call_args.args[3])
            native.assert_not_called();builder.assert_not_called()


if __name__=='__main__':unittest.main()
