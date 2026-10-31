"""Offline composition tests only; stubbed observations are not authorization."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from lightyear_factory.contracts import ContractError
from tools.ci import supervised_intcalc_boundary as boundary
from tools.ci import supervised_send_kernel as sender
from tools.ci import supervised_session_reservation as reservation


class SupervisedSendKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        cls.candidate=subprocess.check_output(
            ['git','-C',str(root),'show','HEAD:'+boundary.PATH]).replace(
                b'MONTHS_PERCENT = 1200',b'MONTHS_PERCENT = 100')

    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name).resolve()
        self.workflow=b'public workflow fixture, not run authorization'
        now=datetime.datetime.now(datetime.timezone.utc)
        utc=lambda value:value.isoformat().replace('+00:00','Z')
        self.packet=dict(label=boundary.LABEL,session_sha256='1'*64,source_sha='3'*40,
            workflow_sha256=hashlib.sha256(self.workflow).hexdigest(),
            public_ca_sha256=hashlib.sha256(b'public CA fixture').hexdigest(),
            call_limit=2,budget_usd='25.00',model=boundary.MODEL,
            endpoint='https://api.openai.com/v1/responses',
            not_before_utc=utc(now-datetime.timedelta(minutes=1)),
            expires_utc=utc(now+datetime.timedelta(minutes=30)),
            qualification_evidence=False)
        binding=dict(label=boundary.LABEL,session_sha256='1'*64,packet_sha256='2'*64,
            source_sha='3'*40,workflow_sha256=self.packet['workflow_sha256'],
            workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
            workflow_id=11,run_id=12,run_attempt=1,sender_job_name='supervised-sender',
            round=1,request_sha256=hashlib.sha256(boundary.generation_request(self.candidate)).hexdigest(),
            previous_receipt_sha256=None,continuation_sha256=None,qualification_evidence=False)
        run=dict(id=12,run_attempt=1,workflow_id=11,head_sha='3'*40,
            repository={'full_name':reservation.REPOSITORY},event='workflow_dispatch',
            path=binding['workflow_path'],status='in_progress')
        job=dict(id=13,run_id=12,run_attempt=1,head_sha='3'*40,
                 name='supervised-sender',status='in_progress')
        self.args=dict(binding=binding,stored_record=b'',native_run=run,native_job=job,
            all_jobs={'total_count':1,'jobs':[dict(job)]},workflow_bytes=self.workflow,
            packet_bytes=b'',approved_packet_sha256='',reservation_commit='a'*40,
            create_status=201,create_response={'ref':reservation.reservation_ref(binding),
                'object':{'type':'commit','sha':'a'*40}},
            candidate=self.candidate,ca_pem=b'public CA fixture',
            authorization='Bearer offline-fixture',deadline=time.monotonic()+60.0,
            run_directory=self.root)
        self.repin()
        self.proposal=dict(summary='offline fixture',blocked_reason=None,
            edits=[dict(path=boundary.PATH,find='MONTHS_PERCENT = 100',
                replace='MONTHS_PERCENT = 1200',rationale='public monthly rule')])
        self.raw=json.dumps(dict(model=boundary.MODEL,service_tier='flex',
            status='completed',usage=dict(input_tokens=1000,output_tokens=100),
            output=[dict(type='message',role='assistant',status='completed',
                content=[dict(type='output_text',text=json.dumps(self.proposal))])])).encode()
        self.connection=Mock()
        self.factory=patch.object(sender,'_fixed_provider_connection',return_value=self.connection).start()
        self.exchange=patch.object(sender,'_exchange_once',return_value=(self.raw,
            dict(label=boundary.LABEL,physical_requests_attempted=1,
                 qualification_evidence=False))).start()
        self.addCleanup(patch.stopall)

    def repin(self):
        raw=json.dumps(self.packet).encode()
        digest=hashlib.sha256(raw).hexdigest()
        self.args['packet_bytes']=raw
        self.args['approved_packet_sha256']=digest
        self.args['binding']['packet_sha256']=digest
        self.args['stored_record']=reservation.canonical_record(self.args['binding'])

    def call(self):
        return sender.send_once_kernel(**self.args)

    def test_intent_precedes_only_exchange_and_local_receipts(self):
        def observed(*args):
            self.assertTrue((self.root/'round-1.send-intent.json').exists())
            return self.raw,dict(label=boundary.LABEL,physical_requests_attempted=1,
                                 qualification_evidence=False)
        self.exchange.side_effect=observed
        proposal,receipt=self.call()
        self.assertEqual(proposal,self.proposal)
        self.assertEqual(receipt['stage'],'RESPONSE_VALIDATED')
        self.assertFalse(receipt['qualification_evidence'])
        self.assertEqual((self.root/'round-1.response.bin').read_bytes(),self.raw)
        self.assertEqual(self.exchange.call_count,1)
        self.connection.close.assert_called_once()

    def test_existing_intent_blocks_second_send(self):
        self.call()
        with self.assertRaisesRegex(ContractError,'persistence-refused'):
            self.call()
        self.assertEqual(self.exchange.call_count,1)

    def test_unknown_exchange_retains_intent_and_never_retries(self):
        self.exchange.side_effect=ContractError('offline unknown')
        with self.assertRaises(ContractError):
            self.call()
        self.assertTrue((self.root/'round-1.send-intent.json').exists())
        with self.assertRaisesRegex(ContractError,'persistence-refused'):
            self.call()
        self.assertEqual(self.exchange.call_count,1)

    def test_failed_intent_fsync_prevents_exchange(self):
        with patch.object(sender.os,'fsync',side_effect=OSError('offline fixture')):
            with self.assertRaisesRegex(ContractError,'persistence-refused'):
                self.call()
        self.exchange.assert_not_called()
        self.assertTrue((self.root/'round-1.send-intent.json').exists())

    def test_response_retention_failure_has_no_second_send_or_receipt(self):
        (self.root/'round-1.response.bin').write_bytes(b'existing')
        with self.assertRaisesRegex(ContractError,'persistence-refused'):
            self.call()
        self.assertEqual(self.exchange.call_count,1)
        self.assertFalse((self.root/'round-1.sender-receipt.json').exists())
        with self.assertRaises(ContractError):
            self.call()
        self.assertEqual(self.exchange.call_count,1)

    def test_malformed_response_is_retained_but_not_accepted(self):
        self.exchange.return_value=(b'invalid JSON',{})
        with self.assertRaises(ContractError):
            self.call()
        self.assertEqual((self.root/'round-1.response.bin').read_bytes(),b'invalid JSON')
        self.assertFalse((self.root/'round-1.sender-receipt.json').exists())
        self.assertEqual(self.exchange.call_count,1)

    def test_packet_mutation_refuses_before_intent(self):
        self.args['packet_bytes']+=b' '
        with self.assertRaisesRegex(ContractError,'packet-pin'):
            self.call()
        self.factory.assert_not_called()
        self.exchange.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_wrong_request_digest_refuses_before_intent(self):
        self.args['binding']['request_sha256']='f'*64
        self.args['stored_record']=reservation.canonical_record(self.args['binding'])
        with self.assertRaisesRegex(ContractError,'request-pin'):
            self.call()
        self.exchange.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_expired_packet_refuses_even_when_hash_matches(self):
        old=datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=1)
        self.packet['not_before_utc']=(old-datetime.timedelta(minutes=30)).isoformat().replace('+00:00','Z')
        self.packet['expires_utc']=old.isoformat().replace('+00:00','Z')
        self.repin()
        with self.assertRaisesRegex(ContractError,'packet-window'):
            self.call()
        self.exchange.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])

    def test_substituted_native_sender_refuses_before_intent(self):
        self.args['native_job']=dict(self.args['native_job'],id=99)
        with self.assertRaisesRegex(ContractError,'sender-unique'):
            self.call()
        self.exchange.assert_not_called()
        self.assertEqual(list(self.root.iterdir()),[])
