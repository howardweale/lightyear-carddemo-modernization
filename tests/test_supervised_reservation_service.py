"""Offline reservation writer tests; no live service, credential or model."""
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from lightyear_factory.contracts import ContractError
from tools.ci import supervised_reservation_service as service
from tools.ci.supervised_session_reservation import canonical_record,reservation_ref,LABEL

class ReservationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name).resolve()
        self.binding=dict(label=LABEL,session_sha256='1'*64,packet_sha256='2'*64,
            source_sha='3'*40,workflow_sha256='4'*64,
            workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
            workflow_id=11,run_id=12,run_attempt=1,sender_job_name='supervised-sender',
            round=1,request_sha256='5'*64,previous_receipt_sha256=None,
            continuation_sha256=None,qualification_evidence=False)
        self.writer=service.NativeReservationWriter(ca_pem=b'public fixture',ca_sha256='0'*64,
                            token='offline',deadline=time.monotonic()+30)
        self.record=canonical_record(self.binding)
        self.blob=service.object_id('blob',self.record)
        self.tree=service.object_id('tree',b'100644 reservation.json\0'+bytes.fromhex(self.blob))
        self.commit='6'*40
        self.message=LABEL+'\n'+hashlib.sha256(self.record).hexdigest()
        self.replies=[{'sha':self.blob},{'sha':self.tree},
            {'sha':self.commit,'tree':{'sha':self.tree},
             'parents':[{'sha':self.binding['source_sha']}],'message':self.message},
            {'ref':reservation_ref(self.binding),'object':{'type':'commit','sha':self.commit}}]

    def test_exact_four_posts_after_exclusive_intent(self):
        def reply(route,payload):
            self.assertEqual((self.directory/'round-1.reservation-intent.json').read_bytes(),self.record)
            return self.replies.pop(0)
        with patch.object(self.writer,'_post',side_effect=reply) as post:
            result=self.writer.create_once(self.binding,self.directory)
        self.assertEqual([c.args[0] for c in post.call_args_list],
                         [service.BASE+'/git/'+s for s in ('blobs','trees','commits','refs')])
        self.assertEqual(post.call_args_list[-1].args[1],
                         {'ref':reservation_ref(self.binding),'sha':self.commit})
        self.assertFalse(result['qualification_evidence'])
        self.assertTrue((self.directory/'round-1.reservation-ack.json').exists())

    def test_wrong_object_or_binding_stops_before_ref(self):
        for stage,key in ((0,'blob-pin'),(1,'tree-pin'),(2,'commit-pin')):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as tmp:
                writer=service.NativeReservationWriter(ca_pem=b'fixture',ca_sha256='0'*64,
                                     token='offline',deadline=time.monotonic()+30)
                replies=[dict(v) for v in self.replies]
                replies[stage]['sha']='invalid'
                with patch.object(writer,'_post',side_effect=replies) as post:
                    with self.assertRaisesRegex(ContractError,key):
                        writer.create_once(self.binding,Path(tmp).resolve())
                self.assertEqual(post.call_count,stage+1)

    def test_unknown_ref_outcome_never_adopted_or_retried(self):
        with patch.object(self.writer,'_post',
                side_effect=self.replies[:3]+[ContractError('unknown')]) as post:
            with self.assertRaisesRegex(ContractError,'unknown'):
                self.writer.create_once(self.binding,self.directory)
            with self.assertRaisesRegex(ContractError,'writer-reused'):
                self.writer.create_once(self.binding,self.directory)
        self.assertEqual(post.call_count,4)
        self.assertTrue((self.directory/'round-1.reservation-intent.json').exists())
        self.assertFalse((self.directory/'round-1.reservation-ack.json').exists())

    def test_existing_local_intent_refuses_before_post(self):
        (self.directory/'round-1.reservation-intent.json').write_bytes(b'partial')
        with patch.object(self.writer,'_post') as post:
            with self.assertRaisesRegex(ContractError,'persistence-refused'):
                self.writer.create_once(self.binding,self.directory)
            post.assert_not_called()

    def test_third_round_refuses_before_post(self):
        with patch.object(self.writer,'_post') as post:
            with self.assertRaisesRegex(ContractError,'round'):
                self.writer.create_once(dict(self.binding,round=3),self.directory)
            post.assert_not_called()

    def test_wrong_ref_ack_refuses_and_leaves_intent(self):
        replies=self.replies[:3]+[dict(self.replies[3],ref='refs/heads/main')]
        with patch.object(self.writer,'_post',side_effect=replies):
            with self.assertRaisesRegex(ContractError,'create-ref'):
                self.writer.create_once(self.binding,self.directory)
        self.assertTrue((self.directory/'round-1.reservation-intent.json').exists())

    def test_independent_dispatch_uses_same_slot(self):
        other=dict(self.binding,run_id=99,request_sha256='7'*64)
        self.assertEqual(reservation_ref(self.binding),reservation_ref(other))
        self.assertNotEqual(canonical_record(self.binding),canonical_record(other))

    def test_post_refusal_status_has_no_retry(self):
        from unittest.mock import Mock
        connection=Mock()
        connection.getresponse.return_value=Mock(status=422)
        with patch.object(service,'_connection',return_value=connection):
            with self.assertRaisesRegex(ContractError,'http-refused'):
                self.writer._post(service.BASE+'/git/refs',
                    {'ref':reservation_ref(self.binding),'sha':self.commit})
        self.assertEqual(connection.request.call_count,1)
        connection.close.assert_called_once()
