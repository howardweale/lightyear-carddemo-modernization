"""Synthetic Tower signatures exercise the production consumer; no authorization credit."""
import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from lightyear_calibration.contracts import seal
from lightyear_control_tower.b06 import SCOPE
from lightyear_control_tower.decisions import ZERO
from lightyear_control_tower.requests import RequestInbox
from lightyear_control_tower.kinds import default_registry
from tests.test_ms94_a3_entry_v2 import test_signer
from tools.ms94_b06_group_decision import KIND, authorize, request, write_request


def proof_for(signer, bound, now, *, outcome='authorized', role='campaign-authorizer', actor_kind='human'):
    actor={'id':'howard-fixture','kind':actor_kind}
    payload={'schema':'tower-decision/1','kind':KIND,'kind_version':1,'scope':SCOPE,
             'bound':bound,'outcome':outcome,'channel':'control-tower','actor':actor,
             'session_id':'fixture-session','roles_held':[role], 'reason':'unit fixture only'}
    event=signer.sign({'sequence':1,'previous_sha256':ZERO,'kind':'tower_decision',
                       'payload':payload,'actor':actor,'session_id':'fixture-session'})
    journal=signer.sign({'record_type':'tower-journal-export/1','scope':SCOPE,'events':[event],
                        'journal_head_sha256':event['content_sha256'],'exported_at':now.isoformat()})
    return {'schema':'tower-decision-proof/1','journal':journal,'decision_sha256':event['content_sha256']}


class GroupDecisionTests(unittest.TestCase):
    def setUp(self):
        self.campaign=test_signer(); self.tower=test_signer()
        self.group=seal({'snapshot_sha256':'a'*64,'docker_run_window':{'not_before_utc':'fixture'},
                        'tower_public_key_sha256':hashlib.sha256(self.tower.public).hexdigest()})
        self.commit='b'*40;self.now=datetime.now(timezone.utc)
        self.reader=Mock(key=self.tower.public)
        self.reader.get.side_effect=lambda kind,bound,now:proof_for(self.tower,bound,now)

    def test_real_inbox_reads_exact_request_and_consumer_accepts_operator(self):
        with tempfile.TemporaryDirectory() as folder:
            name,bound=write_request(folder,self.group,self.commit)
            item=RequestInbox(folder,SCOPE,default_registry()).item(name)
            self.assertEqual(bound,item['bound'])
            proof=authorize(self.group,self.commit,self.reader,self.campaign.public,self.now)
            self.assertEqual(bound,proof['journal']['events'][0]['payload']['bound'])

    def test_campaign_signer_cannot_authorize_or_replace_tower_trust(self):
        self.reader.get.side_effect=lambda k,b,n:proof_for(self.campaign,b,n)
        with self.assertRaises(ValueError):authorize(self.group,self.commit,self.reader,self.campaign.public,self.now)
        self.reader.key=self.campaign.public
        group=seal({**{k:v for k,v in self.group.items() if k!='content_sha256'},
                    'tower_public_key_sha256':hashlib.sha256(self.campaign.public).hexdigest()})
        with self.assertRaisesRegex(ValueError,'trust-binding'):authorize(group,self.commit,self.reader,self.campaign.public,self.now)

    def test_refusal_agent_stale_commit_window_tamper_and_missing_decision_fail(self):
        for fault in ('rejected','agent','stale','commit','window','signature','missing'):
            with self.subTest(fault=fault):
                def get(k,b,n):
                    if fault=='missing':return None
                    if fault=='commit':b={**b,'public_commit':'c'*64}
                    if fault=='window':b={**b,'window':'c'*64}
                    p=proof_for(self.tower,b,n-timedelta(minutes=2) if fault=='stale' else n,
                                outcome='rejected' if fault=='rejected' else 'authorized',
                                actor_kind='agent' if fault=='agent' else 'human')
                    if fault=='signature':p['journal']['scope']='wrong'
                    return p
                self.reader.get.side_effect=get
                with self.assertRaises(ValueError):authorize(self.group,self.commit,self.reader,self.campaign.public,self.now)
