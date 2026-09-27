"""Read projections must reject copied keys, changed receipts and cross-run journals."""
import tempfile
import unittest
from pathlib import Path
from lightyear_calibration.contracts import seal
from lightyear_calibration.journey_order import save, RUNS
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_knowledge_graph import journey_view as view
from lightyear_workflow.run_store import RunStore
from lightyear_workflow.campaign_journals import signed_append

class JourneyViewTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.run_id='journey-'+'a'*32
        self.run=self.root/RUNS/self.run_id;self.run.mkdir(parents=True)
        self.signer=JourneySigner(self.root);self.plan=seal({'declaration_sha256':'b'*64})
        save(self.run/'plan.json',self.plan)
        self.auth=self.signer.sign({'run_id':self.run_id,'plan':{'plan_sha256':self.plan['content_sha256']}})
        save(self.run/'authorization.json',self.auth)
        store=RunStore(self.run/'journal')
        try:signed_append(store,self.signer,self.auth,'started',{'model_calls':0},'journey')
        finally:store.close()

    def test_verified_live_journal_and_run_list(self):
        r=view.selected(self.root,self.run_id)
        self.assertEqual('running',r['status']);self.assertTrue(r['signature_verified'])
        self.assertFalse(r['independently_attested'])
        self.assertEqual(self.run_id,view.read_runs(self.root)['runs'][0]['run_id'])
        self.assertEqual(r,view.selected(self.root))

    def test_cross_run_authorization_rejected(self):
        altered=self.signer.sign({'run_id':'journey-'+'c'*32,'plan':self.auth['plan']})
        save(self.run/'authorization.json',altered)
        self.assertEqual('invalid',view.selected(self.root,self.run_id)['status'])

    def test_supplied_key_cannot_replace_local_trust_anchor(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        impostor=JourneySigner(Path(tmp.name))
        (self.run/'authority.public.pem').write_bytes(impostor.public)
        save(self.run/'authorization.json',impostor.sign({'run_id':self.run_id,'plan':self.auth['plan']}))
        self.assertEqual('invalid',view.selected(self.root,self.run_id)['status'])

    def test_terminal_receipt_cannot_precede_halt(self):
        save(self.run/'receipt.json',self.signer.sign({'run_id':self.run_id,'plan_sha256':self.plan['content_sha256'],'status':'reproduced-with-known-findings'}))
        self.assertEqual('invalid',view.selected(self.root,self.run_id)['status'])

    def test_directory_traversal_refused(self):
        self.assertEqual('invalid',view.selected(self.root,'../../operator')['status'])

    def test_current_timestamp_decision_does_not_rewrite_historical_journal(self):
        from lightyear_calibration.journey_contracts import record_timestamp_acceptance
        evidence=self.root/'docs/calibration/idempiere-boundaries/receipt.json'
        evidence.parent.mkdir(parents=True);evidence.write_text('{}')
        before=view.read_run(self.root,self.run_id)['events']
        record_timestamp_acceptance(self.root,'Howard Weale','2026-12-25')
        after=view.read_run(self.root,self.run_id)
        self.assertEqual(before,after['events'])
        self.assertEqual('Howard Weale',after['timestamp_contract']['owner'])
        self.assertEqual(['adempiere.m_inout.shipdate'],after['timestamp_contract']['scope']['columns'])

    def test_tampered_contract_invalidates_projection(self):
        from lightyear_calibration.journey_contracts import record_timestamp_acceptance,CONTRACT
        evidence=self.root/'docs/calibration/idempiere-boundaries/receipt.json'
        evidence.parent.mkdir(parents=True);evidence.write_text('{}')
        value=record_timestamp_acceptance(self.root,'Howard Weale','2026-12-25')
        value['owner']='Unapproved owner';save(self.root/CONTRACT,value)
        self.assertEqual('invalid',view.read_run(self.root,self.run_id)['status'])

    def test_old_attempt_discloses_later_controller_revisions(self):
        directory=self.root/'work/campaign';directory.mkdir(parents=True)
        original=seal({'max_client_invocations':5})
        amended=seal({'max_client_invocations':10,'prior_plan_sha256':original['content_sha256'],
                      'controller_revision':[{'path':'filter.py'}]})
        save(directory/'history'/f"{original['content_sha256']}.json",original)
        save(directory/'plan.json',amended)
        save(directory/'authorization.json',self.signer.sign({'plan_sha256':amended['content_sha256']}))
        run_id='journey-'+'d'*32;run=self.root/RUNS/run_id
        plan=seal({'campaign_directory':'work/campaign','campaign_plan_sha256':original['content_sha256']})
        auth=self.signer.sign({'run_id':run_id,'plan':{'plan_sha256':plan['content_sha256']}})
        save(run/'plan.json',plan);save(run/'authorization.json',auth)
        store=RunStore(run/'journal')
        try:signed_append(store,self.signer,auth,'started',{'model_calls':0},'journey')
        finally:store.close()
        result=view.read_run(self.root,run_id)
        self.assertEqual('running',result['status'])
        self.assertEqual(1,result['campaign_controller_revisions'])
        self.assertEqual(10,result['campaign_progress']['call_limit'])
        save(directory/'history'/f"{original['content_sha256']}.json",seal({'max_client_invocations':99}))
        self.assertEqual('invalid',view.read_run(self.root,run_id)['status'])

if __name__=='__main__':unittest.main()
