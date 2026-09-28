"""Adversarial tests for engine-side witnesses, not generated trace assertions."""
import copy
import hashlib
import unittest
from unittest.mock import patch
from lightyear_calibration.contracts import seal
from lightyear_calibration.transaction_observer import POLICY,VERSION,QUERIES,full_xid,assess,sample


def receipt(lane,n):
    return seal({'artifact_type':VERSION,'lane':lane,'policy':POLICY,'complete':True,'error':None,
                 'samples':n,'query_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in QUERIES[lane].items()}})


def samples(lane):
    result=[]
    for i in range(5):
        waiting=i<4
        if lane=='postgresql':
            rows=[{'pid':1,'backend_start':'a','xid':'100' if waiting else None,'full_xid':'100' if waiting else None,'wait_event_type':None,'blockers':[]},
                  {'pid':2,'backend_start':'b','xid':None,'wait_event_type':'Lock' if waiting else None,'blockers':[1] if waiting else []}]
            locks=[{'pid':p,'lock_type':'relation','object_schema':'adempiere','object_name':'c_bpartner','granted':True,'mode':'RowExclusiveLock'} for p in (1,2)]
            if waiting:locks += [{'pid':p,'lock_type':'transactionid','object_schema':None,'object_name':None,'granted':p==1,'mode':'ExclusiveLock' if p==1 else 'ShareLock','transaction_id':'100'} for p in (1,2)]
            statuses=[{'xid':'100','status':'in progress' if waiting else 'aborted'}]
        else:
            rows=[{'sid':1,'serial':10,'xid':'1.2.3' if waiting else None,'commits':0,'rollbacks':0 if waiting else 1,'undo_applied':0 if waiting else 4,'state':'ACTIVE','blocking_session_status':'NO HOLDER'},
                  {'sid':2,'serial':20,'xid':None,'commits':0,'rollbacks':0,'undo_applied':0,'state':'WAITING' if waiting else 'ACTIVE','blocking_session_status':'VALID' if waiting else 'NO HOLDER','blocking_session':1}]
            locks=[{'sid':p,'lock_type':'TM','object_schema':'ADEMPIERE','object_name':'C_BPARTNER','held_mode':3,'requested_mode':0,'id1':50,'id2':0} for p in (1,2)]
            if waiting:locks += [{'sid':p,'lock_type':'TX','object_schema':None,'object_name':None,'held_mode':6 if p==1 else 0,'requested_mode':0 if p==1 else 6,'id1':1,'id2':2} for p in (1,2)]
            statuses=[]
        result.append({'sequence':i,'started_ns':i*100_000_000,'finished_ns':i*100_000_000+1_000_000,
                       'results':{'identity':[{'observer_user':'ly_observer','next_xid':'200'}],'sessions':rows,'locks':locks},'transaction_status':statuses})
    return result


class ObserverTests(unittest.TestCase):
    def test_native_witnesses_on_both_engines(self):
        for lane in QUERIES:
            with self.subTest(lane=lane):
                value=assess(receipt(lane,5),samples(lane))
                self.assertTrue(value['passed']);self.assertFalse(value['generated_assertions_used'])
    def test_session_disappearance_is_not_rollback(self):
        for lane in QUERIES:
            rows=samples(lane);rows[-1]['results']['sessions']=[];rows[-1]['transaction_status']=[]
            self.assertFalse(assess(receipt(lane,5),rows)['rollback_observed'])
    def test_commit_is_not_rollback(self):
        for lane in QUERIES:
            rows=samples(lane)
            if lane=='oracle':rows[-1]['results']['sessions'][0]['commits']=1
            else:rows[-1]['transaction_status'][0]['status']='committed'
            self.assertFalse(assess(receipt(lane,5),rows)['rollback_observed'])
    def test_unrelated_table_cannot_qualify(self):
        for lane in QUERIES:
            rows=samples(lane)
            for sample in rows:
                for lock in sample['results']['locks']:lock['object_name']='unrelated'
            self.assertFalse(assess(receipt(lane,5),rows)['passed'])
    def test_counter_increment_without_undo_is_not_a_rollback_witness(self):
        rows=samples('oracle');rows[-1]['results']['sessions'][0]['undo_applied']=0
        self.assertFalse(assess(receipt('oracle',5),rows)['rollback_observed'])
    def test_reused_oracle_session_id_cannot_supply_counters(self):
        rows=samples('oracle');rows[-1]['results']['sessions'][0]['serial']=11
        self.assertFalse(assess(receipt('oracle',5),rows)['rollback_observed'])
    def test_generated_assertions_have_no_effect(self):
        for lane in QUERIES:
            rows=samples(lane)
            for row in rows:row['results']['locks']=[];row['assertions']={'waited':True,'rolled_back':True}
            self.assertFalse(assess(receipt(lane,5),rows)['passed'])
    def test_sampling_gaps_refuse_claim(self):
        rows=samples('oracle');rows[-1]['started_ns']+=2_000_000_000;rows[-1]['finished_ns']+=2_000_000_000
        with self.assertRaises(ValueError):assess(receipt('oracle',5),rows)
    def test_incomplete_or_modified_policy_refuses_claim(self):
        for field,value in [('complete',False),('policy',{}),('query_sha256',{})]:
            r=receipt('oracle',5);r[field]=value;r.pop('content_sha256');r=seal(r)
            with self.assertRaises(ValueError):assess(r,samples('oracle'))
    def test_short_wait_does_not_pass(self):
        rows=samples('oracle')
        for i,row in enumerate(rows):row['started_ns']=i*10_000_000;row['finished_ns']=i*10_000_000+1_000_000
        self.assertFalse(assess(receipt('oracle',5),rows)['lock_wait_observed'])
    def test_lock_disappearing_between_queries_retains_prior_transaction_binding(self):
        rows=samples('oracle');rows[-2]['results']['locks']=[]
        self.assertTrue(assess(receipt('oracle',5),rows)['rollback_observed'])

    def test_horizon_is_read_after_concurrently_allocated_xid(self):
        calls=[]
        def native_query(connection,sql):
            name=next(k for k,v in QUERIES['postgresql'].items() if v==sql) if sql in QUERIES['postgresql'].values() else 'statuses'
            calls.append(name)
            if name=='sessions':return [{'pid':1,'backend_start':'a','xid':'200'}]
            if name=='identity':return [{'observer_user':'ly_observer','next_xid':'201'}]
            if name=='statuses':return [{'xid':'200','status':'in progress'}]
            return []
        with patch('lightyear_calibration.transaction_observer.query',side_effect=native_query):
            result=sample(None,'postgresql',0,0,{})
        self.assertEqual(['sessions','locks','identity','statuses'],calls)
        self.assertEqual('200',result['results']['sessions'][0]['full_xid'])

    def test_xid_epoch_and_ambiguity(self):
        self.assertEqual(str(2**32-1),full_xid(str(2**32-1),str(2**32+3)))
        self.assertEqual('100',full_xid('100','200'))
        for xid,horizon in [('0','200'),('201','200'),('1 OR 1=1','200'),('3',str(2**31+4))]:
            with self.assertRaises((ValueError,TypeError)):full_xid(xid,horizon)


if __name__=='__main__':unittest.main()
