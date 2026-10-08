"""Offline review regressions; synthetic evidence, zero model calls."""
import copy,json,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from test_graph_memory_review import ReviewTests
from lightyear_control_tower.decisions import digest
from lightyear_factory.routing_policy import compile_policy,paired_interval
from lightyear_factory.revocations import refresh
from lightyear_toolkit.revocations import RevocationReader

class QualityTests(unittest.TestCase):
    def matrix(self,passes):
        cells=[]
        for model in ('a','b'):
            cells.append(dict(model=model,model_version=model,task_type='implement',workload='INTCALC',run_count=35,
                passed=passes,pair_ids=[str(i) for i in range(35)],runs=[model+str(i) for i in range(35)],
                paired_outcomes={str(i):i<passes for i in range(35)},false_acceptances=0,cost_per_verified_task=1))
        body=dict(cells=cells,false_acceptances=0);return dict(body,content_sha256=digest(body))
    def test_low_quality_tie_has_no_route_high_quality_tie_does(self):
        self.assertEqual(compile_policy(self.matrix(3),margin=.1)['routes'],{})
        self.assertIn('implement',compile_policy(self.matrix(34),margin=.1)['routes'])
    def test_pairs_not_only_marginal_totals(self):
        a=[True]*30+[False]*5;b=a[:];c=[False]*5+[True]*30
        self.assertNotEqual(paired_interval(a,b),paired_interval(a,c))
    def test_missing_outcomes_cannot_be_reconstructed_from_totals(self):
        m=self.matrix(35);m['cells'][0].pop('paired_outcomes');m['content_sha256']=digest({k:v for k,v in m.items() if k!='content_sha256'})
        with self.assertRaisesRegex(ValueError,'paired outcomes'):compile_policy(m,margin=.1)
    def test_environment_is_not_a_credential_broker(self):
        from lightyear_factory.additional_providers import AnthropicMessagesProvider
        with patch.dict('os.environ',{'ANTHROPIC_API_KEY':'synthetic-do-not-use'}):
            with self.assertRaisesRegex(ValueError,'credential'):AnthropicMessagesProvider('test',input_usd_per_million=1,output_usd_per_million=1)
    def test_numbered_gemini_response_is_bound(self):
        from lightyear_factory.model_versions import require_snapshot,verify_response
        from types import SimpleNamespace
        version='gemini-2.0-flash-001';self.assertEqual(require_snapshot(version),version)
        p=SimpleNamespace(model=version,provider_id='gemini-generate-content',require_snapshot_response=True)
        verify_response(p,{'modelVersion':version})
        with self.assertRaises(ValueError):verify_response(p,{'modelVersion':'gemini-2.0-flash-002'})
    def test_conformance_receipt_binds_current_policy(self):
        from pathlib import Path
        # Run the production conformance validator; no provider or network call.
        import subprocess,sys
        done=subprocess.run([sys.executable,'-m','lightyear_execution','validate'],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr+done.stdout)

class ExpiryTests(ReviewTests):
    def test_expiry_advances_same_ledger_sequence_and_heartbeat_survives(self):
        a=self.create();self.approve(a);_,reader,out=self.projection(a);reader.read()
        future=datetime.fromisoformat(self.expiry).replace(tzinfo=timezone.utc)+timedelta(seconds=1)
        n=len(self.ledger.events());refresh(self.ledger,self.signer,now=future)
        reader.clock=lambda:future
        self.assertIn(a['id'],reader.read());self.assertEqual(len(self.ledger.events()),n)
        refresh(self.ledger,self.signer,now=future+timedelta(minutes=5));reader.clock=lambda:future+timedelta(minutes=5)
        self.assertIn(a['id'],reader.read())
    def test_deleted_or_empty_watermark_never_reenrolls(self):
        a=self.create();self.approve(a);_,reader,_=self.projection(a);reader.read()
        reader.state_path.unlink()
        with self.assertRaisesRegex(ValueError,'state-missing'):reader.read()
        reader.state_path.write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'state-missing'):reader.read()
    def test_unspecified_state_directory_refused(self):
        with self.assertRaisesRegex(ValueError,'host-owned'):RevocationReader(self.root,{},'a'*64)

class MigrationTests(ReviewTests):
    def test_legacy_migration_never_carries_approval(self):
        from lightyear_factory.annotation_migration import propose
        a=self.create();self.approve(a)
        before=self.ledger.path.read_bytes();out=propose(before,self.signer.public)
        self.assertFalse(out['approval_transferred']);self.assertFalse(out['outcomes_transferred'])
        self.assertEqual(out['proposals'][0]['provenance'],'inferred')
        self.assertFalse(out['proposals'][0]['portable']);self.assertEqual(before,self.ledger.path.read_bytes())
        with self.assertRaises(ValueError):propose(before[:-2],self.signer.public)
