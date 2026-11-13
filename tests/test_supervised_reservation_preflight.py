"""Offline preflight tests; mocked native replies grant no authority."""
import base64
import hashlib
import time
import unittest
from unittest.mock import Mock,patch
from lightyear_factory.contracts import ContractError
from tools.ci import supervised_reservation_preflight as pre
from tools.ci.supervised_session_reservation import LABEL,REPOSITORY

class ReservationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.workflow=b'public workflow fixture'
        self.binding=dict(label=LABEL,session_sha256='1'*64,packet_sha256='2'*64,
            source_sha='3'*40,workflow_sha256=hashlib.sha256(self.workflow).hexdigest(),
            workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
            workflow_id=11,run_id=12,run_attempt=1,sender_job_name='supervised-sender',
            round=1,request_sha256='5'*64,previous_receipt_sha256=None,
            continuation_sha256=None,qualification_evidence=False)
        self.run=dict(id=12,run_attempt=1,workflow_id=11,head_sha='3'*40,
            repository={'full_name':REPOSITORY},event='workflow_dispatch',
            path=self.binding['workflow_path'],status='in_progress')
        self.job=dict(id=9,run_id=12,run_attempt=1,head_sha='3'*40,
                      name='supervised-reservation',status='in_progress')
        self.content=dict(type='file',encoding='base64',path=self.binding['workflow_path'],
                          content=base64.b64encode(self.workflow).decode())
        self.reader=pre.ReservationPreflight(ca_pem=b'fixture',ca_sha256='0'*64,
                                            token='offline',deadline=time.monotonic()+30)
        self.kw=dict(binding=self.binding,packet_bytes=b'fixture',approved_packet_sha256='2'*64,
                     ca_pem=b'fixture',job_token='offline',deadline=time.monotonic()+30,
                     run_directory=None)

    def read(self, jobs=None, run=None, content=None):
        with patch.object(self.reader,'_get',side_effect=[
            self.run if run is None else run,self.content if content is None else content,
            {'total_count':len(jobs) if jobs is not None else 1,
             'jobs':[self.job] if jobs is None else jobs},self.run]):
            return self.reader.reservation_job(self.binding)

    def test_reservation_job_can_exist_before_sender_allocation(self):
        self.assertEqual(self.read(),9)

    def test_wrong_source_or_rerun_refuses(self):
        for change in ({'head_sha':'7'*40},{'run_attempt':2}):
            with self.subTest(change=change),self.assertRaisesRegex(ContractError,'run'):
                self.read(run=dict(self.run,**change))

    def test_no_unique_inprogress_reservation_role_refuses(self):
        for jobs in ([dict(self.job,name='other')],[dict(self.job,status='completed')],
                     [self.job,dict(self.job,id=10)]):
            with self.subTest(jobs=jobs),self.assertRaisesRegex(ContractError,'reservation-role'):
                self.read(jobs=jobs)

    def test_duplicate_job_id_refuses(self):
        with self.assertRaisesRegex(ContractError,'job-identity'):
            self.read(jobs=[self.job,dict(self.job,name='other')])

    def test_wrong_workflow_bytes_refuse(self):
        with self.assertRaisesRegex(ContractError,'workflow-pin'):
            self.read(content=dict(self.content,content=base64.b64encode(b'other').decode()))

    def test_native_failure_prevents_writer_construction(self):
        with patch.object(pre,'_packet',return_value={'public_ca_sha256':'0'*64}):
            with patch.object(pre.ReservationPreflight,'reservation_job',
                              side_effect=ContractError('native-refusal')):
                with patch.object(pre,'NativeReservationWriter') as writer:
                    with self.assertRaisesRegex(ContractError,'native-refusal'):
                        pre.reserve_from_native(**self.kw)
                    writer.assert_not_called()

    def test_unknown_create_never_emits_output(self):
        writer=Mock()
        writer.create_once.side_effect=ContractError('unknown-create')
        with patch.object(pre,'_packet',return_value={'public_ca_sha256':'0'*64}):
            with patch.object(pre.ReservationPreflight,'reservation_job',return_value=9):
                with patch.object(pre,'NativeReservationWriter',return_value=writer):
                    with patch.object(pre,'encode_completed_create') as encode:
                        with self.assertRaisesRegex(ContractError,'unknown-create'):
                            pre.reserve_from_native(**self.kw)
                        encode.assert_not_called()

    def test_output_occurs_only_after_native_preflight_and_create(self):
        order=[]
        writer=Mock()
        writer.create_once.side_effect=lambda *args:(order.append('create') or {'fixture':True})
        with patch.object(pre,'_packet',side_effect=lambda *args:(order.append('packet') or {'public_ca_sha256':'0'*64})):
            with patch.object(pre.ReservationPreflight,'reservation_job',
                              side_effect=lambda *args:(order.append('native') or 9)):
                with patch.object(pre,'NativeReservationWriter',return_value=writer):
                    with patch.object(pre,'encode_completed_create',
                            side_effect=lambda *args:(order.append('output') or {'fixture':True})):
                        pre.reserve_from_native(**self.kw)
        self.assertEqual(order,['packet','native','packet','create','output'])
