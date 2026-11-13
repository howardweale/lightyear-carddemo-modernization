"""CI-only untrusted record refusals; no API, fixture key or passed context."""
from copy import deepcopy
import unittest
from tools.ci.operator_flow_pr_observation import relationships,REPOSITORY,JOB,LABEL
class PRObservationRecords(unittest.TestCase):
    def setUp(self):
        self.head='a'*40
        self.pr={'number':7,'state':'open','head':{'sha':self.head,'repo':{'full_name':REPOSITORY}},
            'base':{'repo':{'full_name':REPOSITORY}}}
        self.event={'action':'labeled','label':{'name':LABEL},'number':7,
            'repository':{'full_name':REPOSITORY},'pull_request':deepcopy(self.pr)}
        self.run={'id':12,'event':'pull_request','status':'in_progress','run_attempt':1,
            'head_repository':{'full_name':REPOSITORY},'workflow_id':8,'head_sha':self.head}
        self.job={'id':13,'run_id':12,'name':JOB,'status':'in_progress','head_sha':self.head}
    def check(self):return relationships(self.event,self.run,self.job,self.pr,self.head,12)
    def test_matching_records_return_number_only(self):self.assertEqual(self.check(),7)
    def test_wrong_action_and_label_refuse(self):
        self.event['action']='opened'
        with self.assertRaises(ValueError):self.check()
        self.event['action']='labeled';self.event['label']['name']='unrelated'
        with self.assertRaises(ValueError):self.check()
    def test_fork_refuses(self):
        self.pr['head']['repo']['full_name']='other/repo'
        with self.assertRaises(ValueError):self.check()
    def test_live_head_movement_refuses(self):
        self.pr['head']['sha']='b'*40
        with self.assertRaises(ValueError):self.check()
    def test_merge_sha_is_not_normalized_to_head(self):
        for record in (self.run,self.job):
            record['head_sha']='b'*40
            with self.assertRaises(ValueError):self.check()
            record['head_sha']=self.head
    def test_wrong_run_event_status_or_attempt_refuses(self):
        for key,value in [('event','workflow_dispatch'),('status','completed'),('run_attempt',2),('run_attempt',True)]:
            before=deepcopy(self.run);self.run[key]=value
            with self.assertRaises(ValueError):self.check()
            self.run=before
    def test_wrong_job_identity_or_attempt_refuses(self):
        for key,value in [('run_id',11),('name','other'),('status','completed'),('run_attempt',2)]:
            before=deepcopy(self.job);self.job[key]=value
            with self.assertRaises(ValueError):self.check()
            self.job=before
    def test_boolean_number_and_closed_pr_refuse(self):
        self.event['number']=True
        with self.assertRaises(ValueError):self.check()
        self.event['number']=7;self.pr['state']='closed'
        with self.assertRaises(ValueError):self.check()
