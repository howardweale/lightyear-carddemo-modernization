"""Offline acknowledgement codec tests; values are not native authority."""
import base64
import hashlib
import json
import unittest
from lightyear_factory.contracts import ContractError
from tools.ci import supervised_reservation_handoff as codec
from tools.ci.supervised_session_reservation import (
    LABEL,canonical_record,checked_create_ack,reservation_ref)

class ReservationHandoffTests(unittest.TestCase):
    def setUp(self):
        self.binding=dict(label=LABEL,session_sha256='1'*64,packet_sha256='2'*64,
            source_sha='3'*40,workflow_sha256='4'*64,
            workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
            workflow_id=11,run_id=12,run_attempt=1,sender_job_name='supervised-sender',
            round=1,request_sha256='5'*64,previous_receipt_sha256=None,
            continuation_sha256=None,qualification_evidence=False)
        self.commit='6'*40
        response={'ref':reservation_ref(self.binding),'object':{'type':'commit','sha':self.commit}}
        self.result=dict(label=LABEL,binding=self.binding,reservation_commit=self.commit,
            create_status=201,create_response=response,qualification_evidence=False,
            ack=checked_create_ack(self.binding,self.commit,201,response))
        self.output=codec.encode_completed_create(self.result,9)
        self.readback=dict(label=LABEL,qualification_evidence=False,
            stored_record=canonical_record(self.binding),reservation_commit=self.commit,
            reservation_job_id=9)

    def decode(self, output=None, readback=None, binding=None):
        o=self.output if output is None else output
        return codec.bind_job_output(o['receipt_base64'],o['receipt_sha256'],
                    self.binding if binding is None else binding,
                    self.readback if readback is None else readback)

    def test_exact_join_still_requires_reviewed_workflow_origin(self):
        result=self.decode()
        self.assertFalse(result['original_create_ack_authenticated'])
        self.assertTrue(result['requires_reviewed_needs_origin'])
        self.assertFalse(result['qualification_evidence'])

    def test_wrong_native_reservation_job_refuses(self):
        with self.assertRaisesRegex(ContractError,'readback'):
            self.decode(readback=dict(self.readback,reservation_job_id=10))

    def test_cross_dispatch_binding_refuses(self):
        with self.assertRaisesRegex(ContractError,'binding'):
            self.decode(binding=dict(self.binding,run_id=99))

    def test_modified_bytes_refuse(self):
        changed=dict(self.output,receipt_base64=base64.b64encode(b'{}').decode())
        with self.assertRaisesRegex(ContractError,'digest'):
            self.decode(output=changed)

    def test_duplicate_json_refuses_even_with_matching_digest(self):
        raw=b'{"label":"one","label":"two"}'
        with self.assertRaisesRegex(ContractError,'duplicate'):
            self.decode(output={'receipt_base64':base64.b64encode(raw).decode(),
                                'receipt_sha256':hashlib.sha256(raw).hexdigest()})

    def test_failed_create_cannot_emit_output(self):
        with self.assertRaisesRegex(ContractError,'create-not-confirmed'):
            codec.encode_completed_create(dict(self.result,create_status=422),9)
