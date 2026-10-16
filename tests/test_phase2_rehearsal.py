"""Throwaway Tower authority; the tag transport is intercepted, never contacted."""
from contextlib import ExitStack
from datetime import timedelta
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

from tests.test_phase2_authorization import Phase2SignedProofTests
from tools.posttran_phase2_authorization import REQUEST, PROOF, verify_signed
from tools.prepare_posttran_phase2 import digest
from tools.run_posttran_phase2 import authorize, reserve
from tools.finalize_posttran_phase2 import expiry_status


class RehearsalTests(Phase2SignedProofTests):
    def exercise(self, fault=None):
        plan, env, at = self.fixture()
        plan.update(generation_attempt=1, model_calls=0, preparation_run=122)
        plan['content_sha256'] = digest({k:v for k,v in plan.items() if k!='content_sha256'})
        from tools.posttran_phase2_authorization import PLAN
        from hashlib import sha256
        raw = json.dumps(plan).encode(); (self.root/PLAN).write_bytes(raw)
        contract = json.loads((self.root/REQUEST).read_bytes())
        contract['sources'][-1]['sha256'] = sha256(raw).hexdigest()
        contract['details']['request_seal'] = plan['content_sha256']
        proof, _, _ = self.decide(contract)
        (self.root/REQUEST).write_text(json.dumps(contract)); (self.root/PROOF).write_text(json.dumps(proof))
        env.update(GITHUB_ACTIONS='true', GITHUB_EVENT_NAME='pull_request', GITHUB_RUN_ATTEMPT='1',
            GITHUB_REPOSITORY='howardweale/lightyear-carddemo-modernization', GITHUB_RUN_ID='123',
            GITHUB_OUTPUT=str(self.root/'outputs'), GH_TOKEN='test-only-not-a-credential',
            POSTTRAN_PHASE2_APPROVED_HEAD='b'*40, POSTTRAN_PHASE2_APPROVED_PLAN=plan['content_sha256'],
            POSTTRAN_PHASE2_APPROVED_JOURNAL_HEAD=proof['journal']['journal_head_sha256'])
        if fault in ('head', 'plan', 'journal'):
            env['POSTTRAN_PHASE2_APPROVED_'+{'head':'HEAD','plan':'PLAN','journal':'JOURNAL_HEAD'}[fault]] = ''
        if fault == 'proof': (self.root/PROOF).unlink()
        if fault == 'request':
            contract['details']['caps']['runs']=2; (self.root/REQUEST).write_text(json.dumps(contract))
        def verify():
            authorize(plan, os.environ, 'b'*40)
            verify_signed(self.root, plan, 'b'*40, os.environ,
                          now=at+timedelta(days=2) if fault=='window' else at)
            return plan, 'b'*40
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, env))
            stack.enter_context(patch('tools.run_posttran_phase2.verify', side_effect=verify))
            stack.enter_context(patch('tools.posttran_phase2_authorization.subprocess.run'))
            stack.enter_context(patch('tools.posttran_phase2_authorization.subprocess.check_output', return_value=PROOF+'\n'))
            stack.enter_context(patch('tools.posttran_phase2_authorization.verify_image',
                side_effect=ValueError('bad-image') if fault=='image' else None,
                return_value=dict(verified_before_reservation=True)))
            transport = stack.enter_context(patch('tools.run_posttran_phase2.urllib.request.urlopen',
                return_value=io.BytesIO(json.dumps({'object':{'sha':'b'*40}}).encode())))
            if fault:
                with self.assertRaises(ValueError): reserve(self.root/'reservation')
                transport.assert_not_called()
            else:
                reserve(self.root/'reservation')
                transport.assert_called_once()
                body=json.loads(transport.call_args.args[0].data)
                self.assertEqual('refs/tags/posttran-phase2-consumed-'+plan['content_sha256'], body['ref'])
                self.assertTrue(json.loads((self.root/'reservation/reservation.json').read_bytes())['consumed_before_execution'])

    def test_sign_proof_variables_and_intercepted_reservation(self): self.exercise()
    def test_wrong_head(self): self.exercise('head')
    def test_wrong_plan(self): self.exercise('plan')
    def test_missing_journal(self): self.exercise('journal')
    def test_missing_proof(self): self.exercise('proof')
    def test_changed_request(self): self.exercise('request')
    def test_expired_window(self): self.exercise('window')
    def test_changed_image(self): self.exercise('image')

    def test_five_day_warning(self):
        from datetime import datetime, timezone
        at=datetime(2026,10,16,tzinfo=timezone.utc)
        self.assertIsNone(expiry_status((at+timedelta(days=6,seconds=1)).isoformat(),at)['warning'])
        self.assertIsNotNone(expiry_status((at+timedelta(days=6)).isoformat(),at)['warning'])
