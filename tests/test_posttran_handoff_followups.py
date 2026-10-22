"""CI-only fixtures: no real Tower, application, reservation or signing key."""
import copy
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.check_posttran_handoff import check, check_amendment, READINESS
from tools.check_posttran_deadline import main, upsert_issue, MARKER
from tools.posttran_phase2_authorization import verify_signed, REQUEST, PROOF, PLAN, PUBLIC_KEY
from tests import test_phase2_authorization as phase2_fixture

ROOT = Path(__file__).resolve().parents[1]

class HandoffFollowups(unittest.TestCase):
    def test_publication_ref_and_key_match_readiness(self):
        ready = check(ROOT)
        raw = subprocess.check_output(['git','show',ready['request_publication_commit']+':'+ready['request_path']],cwd=ROOT)
        self.assertEqual(ready['request_file_sha256'],sha256(raw).hexdigest())
        self.assertEqual(ready['public_key_sha256'],sha256((ROOT/PUBLIC_KEY).read_bytes()).hexdigest())
        self.assertNotIn('signing_deadline',ready)

    def test_pinned_plan_inventory_and_current_drift(self):
        from tools.check_posttran_retained_plan import inspect
        result = inspect(ROOT)
        self.assertEqual(check(ROOT)['executable_commit'], result['retained_commit'])
        self.assertGreater(result['validated_files'], 0)
        self.assertFalse(result['execution_authorized'])
        self.assertIn('.github/workflows/posttran-phase2.yml', result['changed_bound_files'])

    def test_clock_at_warning_boundary_exits_nonzero_without_issue_side_effect(self):
        with patch('tools.check_posttran_deadline.upsert_issue') as issue:
            self.assertEqual(0,main(['--root',str(ROOT)],now=datetime(2026,10,24,14,45,59,tzinfo=timezone.utc)))
            self.assertEqual(1,main(['--root',str(ROOT)],now=datetime(2026,10,24,14,46,tzinfo=timezone.utc)))
            issue.assert_not_called()

    def test_undeclared_amendment_refuses(self):
        amendment=json.loads((ROOT/'docs/factory/posttran-phase2-plan-amendment-2026-10-17.json').read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('original_path','amended_path'):
                p=root/amendment[name];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/amendment[name]).read_bytes())
            amendment['amended_fields']=[]
            with self.assertRaisesRegex(ValueError,'undeclared-plan-amendment'):check_amendment(root,amendment)

    def test_one_existing_deadline_issue_is_updated(self):
        calls=[]
        def run(args,**kwargs):
            calls.append((args,kwargs))
            if '--method' not in args:return json.dumps([dict(number=41,body=MARKER,state='closed')]).encode()
            return b'{"number":41}'
        self.assertEqual(41,upsert_issue('owner/repo','new warning',run=run)['number'])
        self.assertIn('repos/owner/repo/issues/41',calls[-1][0])
        self.assertIn('PATCH',calls[-1][0])

    def test_retention_checks_later_manifests_after_first_failure(self):
        from tools.verify_public_retention import verify_all
        with tempfile.TemporaryDirectory() as folder, patch('tools.verify_public_retention.subprocess.check_output',return_value='docs/factory/evidence-retention-a.json\ndocs/factory/evidence-retention-b.json\n'), patch('tools.verify_public_retention.verify',side_effect=[ValueError('first missing'),ValueError('second changed')]) as verify:
            with self.assertRaisesRegex(ValueError,'first missing.*second changed'):verify_all(folder,Path(folder)/'output')
            self.assertEqual(2,verify.call_count)
            self.assertEqual(2,len(json.loads((Path(folder)/'output/summary.json').read_bytes())['failures']))

class LaunchWindowTests(phase2_fixture.Phase2SignedProofTests):
    def signed_fixture(self, executable=None):
        plan,env,_=self.fixture()
        contract=json.loads((self.root/REQUEST).read_bytes())
        contract['details']['window']={'start':'2026-10-17T00:00:00+00:00','end':'2026-10-29T14:46:00+00:00'}
        if executable:
            contract['details']['executable_commit']=executable
            for source in contract['sources']:source['commit']=executable
        proof,_,_=self.decide(contract)
        (self.root/REQUEST).write_text(json.dumps(contract))
        (self.root/PROOF).write_text(json.dumps(proof))
        env['POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD']=proof['journal']['journal_head_sha256']
        return plan,env

    def test_exclusive_launch_deadline(self):
        plan,env=self.signed_fixture()
        with patch('tools.posttran_phase2_authorization.subprocess.run'),patch('tools.posttran_phase2_authorization.subprocess.check_output',return_value=PROOF+'\n'):
            verify_signed(self.root,plan,'b'*40,env,now=datetime(2026,10,29,14,45,59,tzinfo=timezone.utc))
            with self.assertRaisesRegex(ValueError,'phase2-authorization-window'):
                verify_signed(self.root,plan,'b'*40,env,now=datetime(2026,10,29,14,46,tzinfo=timezone.utc))

    def test_main_advancing_does_not_change_execution_ancestry(self):
        self.fixture()
        def git(*args):return subprocess.check_output(['git',*args],cwd=self.root,text=True).strip()
        git('init','-q');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid');git('config','commit.gpgsign','false')
        git('add',PLAN,PUBLIC_KEY,'docs/factory/public.json');git('commit','-qm','signed executable fixture')
        executable=git('rev-parse','HEAD')
        # Rebind the existing synthetic proof to the real fixture commit.
        plan=json.loads((self.root/PLAN).read_bytes());contract=json.loads((self.root/REQUEST).read_bytes())
        contract['details']['executable_commit']=executable
        contract['details']['window']={'start':'2026-10-17T00:00:00+00:00','end':'2026-10-29T14:46:00+00:00'}
        for source in contract['sources']:source['commit']=executable
        proof,_,_=self.decide(contract)
        (self.root/REQUEST).write_text(json.dumps(contract));(self.root/PROOF).write_text(json.dumps(proof))
        git('checkout','-qb','execution');git('add',REQUEST,PROOF);git('commit','-qm','request and proof only');head=git('rev-parse','HEAD')
        git('checkout','-qb','advanced-main',executable);(self.root/'changed-on-main.txt').write_text('unrelated later main change');git('add','changed-on-main.txt');git('commit','-qm','main moved')
        git('checkout','-q','execution')
        result=verify_signed(self.root,plan,head,{'POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD':proof['journal']['journal_head_sha256']},now=datetime(2026,10,29,14,45,59,tzinfo=timezone.utc))
        self.assertEqual(executable,result['details']['executable_commit'])
