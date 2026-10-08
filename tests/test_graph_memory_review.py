import gzip
import json
from pathlib import Path
from unittest.mock import patch
import test_graph_memory as fixtures
from lightyear_factory.revocations import subscribe,binding
from lightyear_toolkit.revocations import RevocationReader
from lightyear_toolkit.guidance import guidance
from lightyear_factory.annotations import retrieve,outcome_summary,leak_certificate
from lightyear_control_tower.decisions import canonical,digest


class ReviewTests(fixtures.MemoryTests):
    def test_interrupted_publication_refuses_guidance_and_preserves_ledger_event(self):
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        before=len(self.ledger.events())
        with patch('lightyear_factory.revocations.publish',side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):self.outcome(a,1,'failed')
        self.assertEqual(len(self.ledger.events()),before+1)
        with self.assertRaisesRegex(ValueError,'head'):reader.read()

    def test_valid_signature_wrong_projection_refused(self):
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        path=out/'revocations/revocations.json';row=json.loads(path.read_bytes())
        body={k:v for k,v in row.items() if k not in {'content_sha256','signature'}}
        body['projection_sha256']='b'*64;path.write_bytes(canonical(self.signer.sign(body)))
        with self.assertRaises(ValueError):reader.read()

    def test_retirement_revokes_without_projection_rebuild(self):
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        cert=leak_certificate(a,(),self.judge,inventory_sha256='a'*64)
        proof=self.proof('graph-annotation',dict(annotation=a,leak_check=cert),'retired')
        payload=dict(id=a['id'],leak_check=cert,proof=proof,trusted_head=proof['journal']['journal_head_sha256'])
        self.ledger.append('retire',payload,self.signer,expected_head=payload['trusted_head'])
        self.assertEqual(guidance(p,['paragraph'],revocations=reader)['items'],[])
    def projection(self,a):
        rows=retrieve(self.ledger.replay(),['paragraph'],[],'public')['items']
        p=dict(customer_id='public',nodes=[dict(id='program'),dict(id='paragraph')],
            edges=[dict(source='program',target='paragraph',relation='CONTAINS')],annotations=rows,
            revocation_binding=binding(self.ledger))
        out=self.root/'projection';out.mkdir()
        raw=gzip.compress(canonical(p),mtime=0);(out/'projection.json.gz').write_bytes(raw)
        subscription=subscribe(self.ledger,self.signer,out)
        reader=RevocationReader(out/'revocations',p['revocation_binding'],subscription['projection_sha256'],state_directory=self.root/'reader-state')
        return p,reader,out

    def test_live_flag_removes_pitfall_from_unchanged_projection(self):
        a=self.create(type='pitfall');self.approve(a)
        p,reader,out=self.projection(a)
        self.assertEqual(len(guidance(p,['program'],revocations=reader)['items']),1)
        original=(out/'projection.json.gz').read_bytes()
        self.outcome(a,1,'failed',evaluation_class='customer-factory')
        self.assertEqual(len(guidance(p,['program'],revocations=reader)['items']),1)
        self.outcome(a,2,'failed',evaluation_class='customer-factory')
        self.assertEqual(guidance(p,['program'],revocations=reader)['items'],[])
        self.assertEqual(original,(out/'projection.json.gz').read_bytes())

    def test_missing_bad_signature_wrong_projection_and_head_fail_closed(self):
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        with self.assertRaises(ValueError):guidance(p,['paragraph'])
        reader.read();path=out/'revocations/revocations.json';old=path.read_bytes()
        self.outcome(a,1)
        path.write_bytes(old)
        with self.assertRaises(ValueError):guidance(p,['paragraph'],revocations=reader)
        row=json.loads(old);row['revoked']=[];row['projection_sha256']='b'*64
        path.write_bytes(canonical(row))
        with self.assertRaises(ValueError):reader.read()
        path.unlink()
        with self.assertRaises(OSError):reader.read()

    def test_customer_factory_still_requires_judge_and_replay(self):
        a=self.create();self.approve(a)
        self.outcome(a,1,evaluation_class='customer-factory')
        with self.assertRaises(ValueError):self.outcome(a,2,evaluation_class='customer-factory',independently_replayed=False)
        with self.assertRaises(ValueError):self.outcome(a,2,evaluation_class='sealed-holdout')

    def test_early_threshold_and_descendants_bound(self):
        a=self.create(type='pitfall');self.approve(a)
        edges=[dict(source='program',target='paragraph',relation='CONTAINS')]
        self.assertEqual(len(retrieve(self.ledger.replay(),['program'],edges,'public')['items']),1)
        for i in range(3):self.outcome(a,i)
        self.outcome(a,3,'failed');self.outcome(a,4,'failed')
        self.assertTrue(outcome_summary(self.ledger.replay()[a['id']])['flagged'])
        self.assertEqual(retrieve(self.ledger.replay(),['program'],edges,'public')['items'],[])

    def test_new_reader_refuses_rolled_back_signed_pair(self):
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        old={name:(out/'revocations'/name).read_bytes() for name in ('head.json','revocations.json')}
        reader.read();self.outcome(a,1,'failed');reader.read()
        for name,data in old.items():(out/'revocations'/name).write_bytes(data)
        new=RevocationReader(reader.directory,reader.binding,reader.projection,state_directory=reader.state_directory)
        with self.assertRaisesRegex(ValueError,'rollback'):new.read()

    def test_missing_subscription_refuses_append(self):
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        before=len(self.ledger.events())
        self.ledger.path.with_suffix('.revocation-subscriptions.json').unlink()
        with self.assertRaisesRegex(ValueError,'subscription'):self.outcome(a,1,'failed')
        self.assertEqual(len(self.ledger.events()),before)

    def test_expired_head_refuses_fresh_reader(self):
        from datetime import datetime,timezone,timedelta
        a=self.create();self.approve(a);p,reader,out=self.projection(a)
        new=RevocationReader(reader.directory,reader.binding,reader.projection,state_directory=reader.state_directory,
            now=lambda:datetime.now(timezone.utc)+timedelta(minutes=16))
        with self.assertRaisesRegex(ValueError,'expired'):new.read()
