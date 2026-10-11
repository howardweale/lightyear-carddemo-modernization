import unittest
from tools.ci_push_latency import summarize
class TimingTests(unittest.TestCase):
    def test_no_author_date_or_proxy_as_push(self):
        pr=dict(number=1,head=dict(sha='new',ref='branch'))
        r=dict(id=2,head_sha='new',event='pull_request',pull_requests=[dict(number=1)],path='.github/workflows/required-ci.yml',status='completed',conclusion='success',created_at='2026-10-11T00:01:00Z',updated_at='2026-10-11T00:03:00Z')
        result=summarize(pr,[r],[]);self.assertIsNone(result['push_to_green_seconds']);self.assertEqual(120,result['workflow_creation_to_green_seconds'])
        event=dict(type='PushEvent',created_at='2026-10-11T00:00:00Z',payload=dict(head='new',ref='refs/heads/branch'))
        self.assertEqual(180,summarize(pr,[r],[event])['push_to_green_seconds'])
        for c in ('failure','cancelled','skipped'):
            self.assertFalse(summarize(pr,[dict(r,conclusion=c)],[event])['green'])
