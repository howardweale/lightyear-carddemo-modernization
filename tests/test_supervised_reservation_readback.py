"""Offline object readback tests; mocked responses are not service evidence."""
import base64
import copy
import hashlib
import time
import unittest
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from tools.ci import supervised_reservation_readback as rb
from tools.ci.supervised_session_reservation import LABEL,canonical_record,reservation_ref

class ReservationReadbackTests(unittest.TestCase):
    def setUp(self):
        self.binding=dict(label=LABEL,session_sha256='1'*64,packet_sha256='2'*64,
            source_sha='3'*40,workflow_sha256='4'*64,
            workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
            workflow_id=11,run_id=12,run_attempt=1,sender_job_name='supervised-sender',
            round=1,request_sha256='5'*64,previous_receipt_sha256=None,
            continuation_sha256=None,qualification_evidence=False)
        self.record=canonical_record(self.binding)
        self.blob=rb.object_id('blob',self.record)
        self.tree=rb.object_id('tree',b'100644 reservation.json\0'+bytes.fromhex(self.blob))
        self.commit='6'*40
        ref={'ref':reservation_ref(self.binding),'object':{'type':'commit','sha':self.commit}}
        self.replies=[ref,
            {'sha':self.commit,'tree':{'sha':self.tree},
             'parents':[{'sha':self.binding['source_sha']}],
             'message':LABEL+'\n'+hashlib.sha256(self.record).hexdigest()},
            {'sha':self.tree,'truncated':False,'tree':[
                {'path':'reservation.json','mode':'100644','type':'blob','sha':self.blob}]},
            {'sha':self.blob,'encoding':'base64','size':len(self.record),
             'content':base64.b64encode(self.record).decode()},copy.deepcopy(ref)]
        self.handoff={'all_jobs':{'jobs':[{'id':9,'name':'supervised-reservation',
                                  'status':'completed','conclusion':'success'}]}}
        self.reader=rb.ReservationReadback(ca_pem=b'fixture',ca_sha256='0'*64,
                                         token='offline',deadline=time.monotonic()+30)

    def read(self):
        with patch.object(self.reader,'_get',side_effect=self.replies) as get:
            with patch.object(rb.NativeObservations,'sender_handoff',
                              return_value=self.handoff):
                result=self.reader.read_reserved_objects(self.binding,self.commit)
        return result,get.call_args_list

    def test_exact_objects_and_successful_job_do_not_authenticate_create_ack(self):
        result,calls=self.read()
        self.assertEqual(result['stored_record'],self.record)
        self.assertEqual(result['reservation_job_id'],9)
        self.assertFalse(result['original_create_ack_authenticated'])
        self.assertFalse(result['qualification_evidence'])
        self.assertEqual(calls[0],calls[-1])
        self.assertEqual(len(calls),5)

    def test_ref_replacement_during_readback_refuses(self):
        self.replies[-1]['object']['sha']='7'*40
        with self.assertRaisesRegex(ContractError,'reservation-ref'):
            self.read()

    def test_wrong_source_parent_refuses(self):
        self.replies[1]['parents']=[{'sha':'7'*40}]
        with self.assertRaisesRegex(ContractError,'commit-binding'):
            self.read()

    def test_extra_tree_entry_refuses(self):
        self.replies[2]['tree'].append(dict(self.replies[2]['tree'][0],path='extra'))
        with self.assertRaisesRegex(ContractError,'reservation-tree'):
            self.read()

    def test_noncanonical_record_refuses(self):
        self.replies[3]['content']=base64.b64encode(b' '+self.record).decode()
        with self.assertRaisesRegex(ContractError,'reservation-record'):
            self.read()

    def test_failed_missing_or_ambiguous_reservation_job_refuses(self):
        good=self.handoff['all_jobs']['jobs'][0]
        for jobs in ([],[dict(good,conclusion='failure')],[good,dict(good,id=10)]):
            with self.subTest(jobs=jobs):
                self.handoff={'all_jobs':{'jobs':jobs}}
                with self.assertRaisesRegex(ContractError,'reservation-job'):
                    self.read()

    def test_truncated_tree_refuses(self):
        self.replies[2]['truncated']=True
        with self.assertRaisesRegex(ContractError,'reservation-tree'):
            self.read()

    def test_routes_exclude_other_refs_and_mutations(self):
        with patch.object(rb,'_connection') as connect:
            for route in (rb.BASE+'/git/ref/heads/main',
                          rb.BASE+'/git/refs',rb.BASE+'/git/ref/tags/other'):
                with self.subTest(route=route),self.assertRaisesRegex(ContractError,'route'):
                    self.reader._get(route)
            connect.assert_not_called()
