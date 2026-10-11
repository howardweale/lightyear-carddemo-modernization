import unittest
from tools.ci_push_latency import summarize,preserve_history
class TimingTests(unittest.TestCase):
    def test_no_author_date_or_proxy_as_push(self):
        pr=dict(number=1,head=dict(sha='new',ref='branch'))
        r=dict(id=2,head_sha='new',event='pull_request',pull_requests=[dict(number=1)],path='.github/workflows/required-ci.yml',status='completed',conclusion='success',created_at='2026-10-11T00:01:00Z',updated_at='2026-10-11T00:03:00Z')
        result=summarize(pr,[r],[]);self.assertIsNone(result['push_to_green_seconds']);self.assertEqual(120,result['workflow_creation_to_green_seconds'])
        event=dict(type='PushEvent',created_at='2026-10-11T00:00:00Z',payload=dict(head='new',ref='refs/heads/branch'))
        self.assertEqual(180,summarize(pr,[r],[event])['push_to_green_seconds'])
        for c in ('failure','cancelled','skipped'):
            self.assertFalse(summarize(pr,[dict(r,conclusion=c)],[event])['green'])
    def test_retention_and_changed_heads_do_not_rewrite_observations(self):
        old=dict(pr=311,head='a',push_at='2026-10-11T00:00:00Z',green=False)
        result=dict(prs=[dict(pr=311,head='a',push_at=None,all_workflows_green_at='2026-10-11T00:03:00Z',green=True)])
        previous=dict(prs=[old],delivered_notifications=['once'])
        updated=preserve_history(result,previous)
        self.assertEqual(180,updated['prs'][0]['push_to_green_seconds'])
        self.assertEqual(['once'],updated['delivered_notifications'])
        new=dict(prs=[dict(pr=311,head='b',push_at=None,all_workflows_green_at=None,green=False)])
        updated2=preserve_history(new,updated)
        self.assertEqual('a',updated2['head_history'][0]['head'])
        self.assertTrue(updated2['head_history'][0]['green'])
        self.assertIsNone(updated2['prs'][0]['push_at'])
