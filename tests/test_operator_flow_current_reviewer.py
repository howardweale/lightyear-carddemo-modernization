"""CI-only untrusted reviewer records; no API, signing or admission."""
from copy import deepcopy
import os,unittest
from pathlib import Path
from tools.ci.operator_flow_publication_review import (
    _reviewer_relationships,_review_current_identity,REVIEW_WORKFLOW,REVIEW_JOB,REVIEW_LABEL,REPOSITORY)

class ReviewerIdentityRelations(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')
        self.e='a'*40;self.m='b'*40;self.base='c'*40
        self.pr=dict(number=7,state='open',merge_commit_sha=self.m,
            head=dict(sha=self.e,repo=dict(full_name=REPOSITORY)),
            base=dict(sha=self.base,ref='main',repo=dict(full_name=REPOSITORY)))
        self.event=dict(action='labeled',label=dict(name=REVIEW_LABEL),number=7,
            repository=dict(full_name=REPOSITORY),pull_request=deepcopy(self.pr))
        self.run=dict(id=12,event='pull_request',status='in_progress',run_attempt=1,
            repository=dict(full_name=REPOSITORY),head_repository=dict(full_name=REPOSITORY),workflow_id=8,head_sha=self.e)
        self.workflow=dict(id=8,path=REVIEW_WORKFLOW)
        self.listing=dict(total_count=1,jobs=[dict(id=13,run_id=12,name=REVIEW_JOB,status='in_progress',head_sha=self.e)])
    def check(self):return _reviewer_relationships(self.event,self.run,self.workflow,self.listing,self.pr,self.e,12,self.m)
    def test_matching_untrusted_records_return_identity_only(self):
        self.assertEqual(self.check(),dict(pr=7,run=12,job=13,workflow=8,executable=self.e,tested_merge=self.m,base=self.base))
    def test_wrong_action_label_and_boolean_number_refuse(self):
        for key,value in (('action','opened'),('label',dict(name='other')),('number',True)):
            original=deepcopy(self.event);self.event[key]=value
            with self.assertRaises(ValueError):self.check()
            self.event=original
    def test_changed_live_head_base_merge_and_fork_refuse(self):
        for field,value in (('head',dict(sha='d'*40,repo=dict(full_name=REPOSITORY))),
            ('base',dict(sha='d'*40,ref='main',repo=dict(full_name=REPOSITORY))),
            ('merge_commit_sha','d'*40),('state','closed'),
            ('head',dict(sha=self.e,repo=dict(full_name='other/repo')))):
            original=deepcopy(self.pr);self.pr[field]=value
            with self.assertRaises(ValueError):self.check()
            self.pr=original
    def test_wrong_run_event_attempt_head_repository_refuse(self):
        for key,value in (('event','workflow_dispatch'),('run_attempt',True),('run_attempt',2),
            ('status','completed'),('head_sha',self.m),('repository',dict(full_name='other/repo'))):
            original=deepcopy(self.run);self.run[key]=value
            with self.assertRaises(ValueError):self.check()
            self.run=original
    def test_wrong_workflow_path_id_type_refuse(self):
        for key,value in (('path','.github/workflows/other.yml'),('id',9),('id',True)):
            original=deepcopy(self.workflow);self.workflow[key]=value
            with self.assertRaises(ValueError):self.check()
            self.workflow=original
    def test_incomplete_duplicate_or_boolean_job_listing_refuses(self):
        for listing in (dict(total_count=2,jobs=self.listing['jobs']),dict(total_count=True,jobs=self.listing['jobs']),
            dict(total_count=2,jobs=self.listing['jobs']*2),dict(total_count=0,jobs=[])):
            original=self.listing;self.listing=listing
            with self.assertRaises(ValueError):self.check()
            self.listing=original
    def test_wrong_job_identity_head_status_attempt_refuse(self):
        for key,value in (('id',True),('run_id',True),('run_id',11),('name','other'),('status','completed'),('head_sha',self.m),('run_attempt',2)):
            original=deepcopy(self.listing);self.listing['jobs'][0][key]=value
            with self.assertRaises(ValueError):self.check()
            self.listing=original
    def test_scratch_job_cannot_enter_live_reviewer(self):
        with self.assertRaisesRegex(ValueError,'reviewer-ci-only'):
            _review_current_identity(Path(__file__).resolve().parents[1],self.e)
