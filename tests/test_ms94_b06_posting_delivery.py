"""Public synthetic rows and streams; no native qualification credit."""
import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from lightyear_calibration.contracts import read_json, canonical, seal
from lightyear_calibration.journey_order import file_hash
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_admission import EvidenceFailure
from tools.ms94_b06_posting_delivery import native_label, project
from tools.ms94_b06_runtime_delivery import POLICY, record_zero_model_delivery, replay_delivery
from tests import test_ms94_b06_posting_controls as controls
from tests.test_ms94_b06_runtime_delivery import runtime_fixture, SOURCE
from tools.ms94_b06_posting_replay import SUPPORT


class PostingDeliveryTests(unittest.TestCase):
    def test_cross_engine_document_disagreement_is_suspect_without_feedback(self):
        policy=read_json(Path(__file__).resolve().parents[1]/POLICY)
        fixture=controls.PostingControls()
        causes={lane:fixture.replay(lane,'prior-lock') for lane in ('oracle','postgresql')}
        self.assertEqual(([],True),project(causes,{'oracle':'invoice','postgresql':'credit'},policy))

    def test_native_cause_projection_is_recorded_consumed_and_replayed(self):
        # Admission/capture seams are synthetic; cause derivation, projection,
        # signatures, inbox consumption and independent delivery replay execute.
        fixture=controls.PostingControls()
        policy_bytes=(Path(__file__).resolve().parents[1]/POLICY).read_bytes()
        for kind in ('prior-lock','support-origin','outside-origin','wrong-document','genuine-equipment-fault','label-mismatch'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); run=root/'j1'; (run/'inputs').mkdir(parents=True)
                (run/'inputs/operations.java').write_text(SOURCE,encoding='utf-8')
                policy=root/POLICY; policy.parent.mkdir(parents=True); policy.write_bytes(policy_bytes)
                plan=seal({'journey':'J1','slot_kind':'posting-origin','model_calls':0,'qualification_only':True,
                    'harness_sha256':file_hash(run/'inputs/operations.java'),'runtime_delivery':{
                    'policy_sha256':file_hash(policy),'consumer':'zero-model-preflight-inbox/1'}})
                (run/'plan.json').write_bytes(canonical(plan))
                causes={lane:fixture.replay(lane,'prior-lock' if kind=='label-mismatch' else kind) for lane in ('oracle','postgresql')}
                for lane in causes:
                    folder=run/'cases/operations/1/execution'/lane; folder.mkdir(parents=True)
                    (folder/'execution.json').write_bytes(canonical(seal({'exit_code':1})))
                event,terminal=runtime_fixture(SUPPORT)
                stream={'collection_complete':True,'exceptions':[event],'terminals':[terminal],
                        'entry_sha256':'a'*64,'clock':{},'receipt_sha256':'b'*64}
                before={lane:{'c_invoice':[]} for lane in causes}
                after={lane:{'c_invoice':[{'c_invoice_id':123,'c_doctype_id':7}],
                             'c_doctype':[{'c_doctype_id':7,'docbasetype':'ARI'}]} for lane in causes}
                if kind=='label-mismatch':after['postgresql']['c_doctype'][0]['docbasetype']='ARC'
                signer=test_signer()
                with patch('tools.ms94_b06_runtime_delivery.replay',return_value=stream), \
                     patch('tools.ms94_b06_posting_cause.replay_cause',side_effect=lambda r,u,l,k:causes[l]), \
                     patch('tools.ms94_b06_admission.native_pair_tables',return_value=(before,after,{})):
                    delivery=record_zero_model_delivery(root,run,signer)
                    replayed=replay_delivery(root,run,signer.public)
                    self.assertTrue(replayed['delivery_replayed'])
                    self.assertEqual(kind=='prior-lock',delivery['delivered'])
                    self.assertEqual(kind!='prior-lock',delivery['equipment_suspect'])
                    if kind=='prior-lock':
                        inbox=read_json(run/'zero-model-builder-inbox.json')
                        self.assertEqual('candidate-posting-sequence-misuse',inbox['diagnostics'][0]['category'])
                        causes['oracle']=fixture.replay('oracle','wrong-document')
                        with self.assertRaisesRegex(EvidenceFailure,'projection-replay-differs'):
                            replay_delivery(root,run,signer.public)
                    else: self.assertFalse((run/'zero-model-builder-inbox.json').exists())

    def test_labels_require_new_native_document_and_unambiguous_type(self):
        before={'c_invoice':[]}
        after={'c_invoice':[{'c_invoice_id':123,'c_doctype_id':7}],
               'c_doctype':[{'c_doctype_id':7,'docbasetype':'ARI'}]}
        self.assertEqual('invoice',native_label('J1',[318,123],before,after))
        for mutation in ('old','missing','duplicate','wrong-type'):
            b,a=copy.deepcopy(before),copy.deepcopy(after)
            if mutation=='old': b['c_invoice']=copy.deepcopy(a['c_invoice'])
            elif mutation=='missing': a['c_invoice']=[]
            elif mutation=='duplicate': a['c_doctype']*=2
            else: a['c_doctype'][0]['docbasetype']='API'
            with self.subTest(mutation=mutation),self.assertRaises(EvidenceFailure): native_label('J1',[318,123],b,a)

    def test_native_integer_and_exact_decimal_quantities_and_invalid_values(self):
        b={'m_inventory':[]}
        a={'m_inventory':[{'m_inventory_id':123,'c_doctype_id':7}],
           'c_doctype':[{'c_doctype_id':7,'docbasetype':'MMI','docsubtypeinv':'PI'}],
           'm_inventoryline':[{'m_inventory_id':123,'qtybook':0,'qtycount':{'decimal':'1.25'}}]}
        self.assertEqual('openingInventory',native_label('J3',[321,123],b,a))
        a['m_inventoryline'][0]['qtybook']={'decimal':'2.25'}
        self.assertEqual('physicalCount',native_label('J3',[321,123],b,a))
        for invalid in ('NaN','Infinity',{'hex':'00'},'private-value'):
            a['m_inventoryline'][0]['qtybook']=invalid
            with self.subTest(invalid=invalid),self.assertRaisesRegex(EvidenceFailure,'quantity-invalid'):
                native_label('J3',[321,123],b,a)
        a['c_doctype'][0]['docsubtypeinv']='IU'
        self.assertEqual('internalUse',native_label('J3',[321,123],b,a))

    def test_both_engine_cause_replays_feed_only_closed_projection(self):
        policy=read_json(Path(__file__).resolve().parents[1]/POLICY)
        fixture=controls.PostingControls()
        for kind in ('prior-lock','prior-post','support-origin','outside-origin','wrong-document','genuine-equipment-fault'):
            causes={lane:fixture.replay(lane,kind) for lane in ('oracle','postgresql')}
            values,suspect=project(causes,{'oracle':'invoice','postgresql':'invoice'},policy)
            self.assertEqual(kind not in ('prior-lock','prior-post'),suspect)
            if kind=='prior-lock':
                self.assertEqual(1,len(values))
                self.assertEqual(set(policy['attribution']['closed_fields']),set(values[0]))
                self.assertEqual('both',values[0]['lanes'])
                self.assertNotIn(b'123',canonical(values))
                self.assertNotIn(b'private localized reason',canonical(values))
                causes['postgresql']=fixture.replay('postgresql','wrong-document')
                self.assertEqual(([],True),project(causes,{'oracle':'invoice','postgresql':'invoice'},policy))
            else: self.assertEqual([],values)


if __name__=='__main__': unittest.main()
