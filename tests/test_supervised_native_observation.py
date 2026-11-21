"""Offline native-reader contracts; mocked replies are not authenticated evidence."""
import base64
import hashlib
import json
import time
import unittest
from unittest.mock import Mock,patch

from lightyear_factory.contracts import ContractError
from tools.ci import supervised_native_observation as native
from tools.ci import supervised_session_reservation as reservation


class SupervisedNativeObservationTests(unittest.TestCase):
    def setUp(self):
        self.workflow=b'public workflow fixture'
        self.value=dict(label=reservation.LABEL,session_sha256='1'*64,
            packet_sha256='2'*64,source_sha='3'*40,
            workflow_sha256=hashlib.sha256(self.workflow).hexdigest(),
            workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
            workflow_id=11,run_id=12,run_attempt=1,sender_job_name='supervised-sender',
            round=1,request_sha256='4'*64,previous_receipt_sha256=None,
            continuation_sha256=None,qualification_evidence=False)
        self.record=reservation.canonical_record(self.value)
        self.run=dict(id=12,run_attempt=1,workflow_id=11,head_sha='3'*40,
            repository={'full_name':reservation.REPOSITORY},event='workflow_dispatch',
            path=self.value['workflow_path'],status='in_progress')
        self.job=dict(id=13,run_id=12,run_attempt=1,head_sha='3'*40,
                      name='supervised-sender',status='in_progress')
        self.content=dict(type='file',encoding='base64',path=self.value['workflow_path'],
                          content=base64.b64encode(self.workflow).decode())
        self.client=native.NativeObservations(ca_pem=b'fixture',ca_sha256='0'*64,
                         token='offline-fixture',deadline=time.monotonic()+60.0)
        self.runpath=native.BASE+'/actions/runs/12'

    def read(self,replies):
        with patch.object(self.client,'_get',side_effect=replies) as get:
            result=self.client.sender_handoff(self.value,self.record)
            return result,get.call_args_list

    def test_exact_routes_and_late_native_job_binding(self):
        result,calls=self.read([self.run,self.content,
                               {'total_count':1,'jobs':[self.job]},self.run])
        self.assertEqual(result['observed']['sender_job_id'],13)
        self.assertFalse(result['observed']['qualification_evidence'])
        self.assertEqual([c.args[0] for c in calls],[
            self.runpath,native.BASE+'/contents/'+self.value['workflow_path']+
            '?ref='+self.value['source_sha'],
            self.runpath+'/attempts/1/jobs?per_page=100&page=1',self.runpath])

    def test_every_page_required_before_handoff(self):
        others=[dict(self.job,id=100+i,name='other-'+str(i)) for i in range(100)]
        result,calls=self.read([self.run,self.content,
            {'total_count':101,'jobs':others},{'total_count':101,'jobs':[self.job]},self.run])
        self.assertEqual(len(result['all_jobs']['jobs']),101)
        self.assertEqual(calls[-2].args[0],self.runpath+'/attempts/1/jobs?per_page=100&page=2')

    def test_changing_page_total_refuses(self):
        rows=[dict(self.job,id=100+i,name='other-'+str(i)) for i in range(100)]
        with self.assertRaisesRegex(ContractError,'pagination-drift'):
            self.read([self.run,self.content,{'total_count':101,'jobs':rows},
                       {'total_count':102,'jobs':[self.job]}])

    def test_short_page_cannot_claim_complete_inventory(self):
        with self.assertRaisesRegex(ContractError,'pagination-short'):
            self.read([self.run,self.content,{'total_count':2,'jobs':[self.job]}])

    def test_duplicate_native_job_ids_refuse(self):
        other=dict(self.job,name='other')
        with self.assertRaisesRegex(ContractError,'job-list-identity'):
            self.read([self.run,self.content,{'total_count':2,'jobs':[self.job,other]}])

    def test_workflow_substitution_refuses(self):
        content=dict(self.content,content=base64.b64encode(b'other').decode())
        with self.assertRaisesRegex(ContractError,'workflow-pin'):
            self.read([self.run,content])

    def test_run_changes_during_pagination_refuse(self):
        with self.assertRaisesRegex(ContractError,'native-run'):
            self.read([self.run,self.content,{'total_count':1,'jobs':[self.job]},
                       dict(self.run,run_attempt=2)])

    def test_ambiguous_sender_role_refuses(self):
        with self.assertRaisesRegex(ContractError,'sender-unique'):
            self.read([self.run,self.content,
                       {'total_count':2,'jobs':[self.job,dict(self.job,id=14)]}])

    def test_redirect_is_not_followed_or_retried(self):
        connection=Mock()
        response=Mock(status=302)
        connection.getresponse.return_value=response
        with patch.object(native,'_connection',return_value=connection) as factory:
            with self.assertRaisesRegex(ContractError,'http-refused'):
                self.client._get(self.runpath)
        self.assertEqual(factory.call_count,1)
        self.assertEqual(connection.request.call_count,1)
        connection.close.assert_called_once()

    def test_transport_error_is_redacted_and_not_retried(self):
        connection=Mock()
        connection.request.side_effect=OSError('offline-fixture credential-like text')
        with patch.object(native,'_connection',return_value=connection):
            with self.assertRaisesRegex(ContractError,'^supervised-native-outcome-unknown$'):
                self.client._get(self.runpath)
        self.assertEqual(connection.request.call_count,1)
        connection.close.assert_called_once()

    def test_unlisted_routes_refuse_before_any_connection(self):
        with patch.object(native,'_connection') as connection:
            for route in ('https://example.invalid',native.BASE+'/git/refs',
                          self.runpath+'?redirect=other',native.BASE+'/actions/runs/12/attempts/2'):
                with self.subTest(route=route),self.assertRaisesRegex(ContractError,'route'):
                    self.client._get(route)
            connection.assert_not_called()

    def test_token_header_injection_refuses_before_read(self):
        for token in ('','bad\r\nHeader: value',' space ',None):
            with self.subTest(token=token),self.assertRaisesRegex(ContractError,'token-format'):
                native.NativeObservations(ca_pem=b'fixture',ca_sha256='0'*64,
                    token=token,deadline=time.monotonic()+60.0)



    def test_existing_rerun_refuses_before_workflow_or_jobs(self):
        with patch.object(self.client,'_get',return_value=dict(self.run,run_attempt=2)) as get:
            with self.assertRaisesRegex(ContractError,'current-attempt'):
                self.client.sender_handoff(self.value,self.record)
        self.assertEqual([c.args[0] for c in get.call_args_list],[self.runpath])

    def test_historical_attempt_endpoint_is_not_allowlisted(self):
        with patch.object(native,'_connection') as connect:
            with self.assertRaisesRegex(ContractError,'route'):
                self.client._get(self.runpath+'/attempts/1')
            connect.assert_not_called()

class NativeHTTPFramingTests(unittest.TestCase):
    """Real HTTPResponse parser over inert bytes; no socket/network or model."""
    def read_wire(self, headers, body):
        import io
        class Socket:
            def __init__(self, data):
                self.stream=io.BytesIO(data)
            def makefile(self, mode):
                return self.stream
            def settimeout(self, value):
                if self.stream.closed:
                    raise OSError('descriptor already closed')
        wire=b'HTTP/1.1 200 OK\r\n'+headers+b'\r\n'+body
        sock=Socket(wire)
        response=native.http.client.HTTPResponse(sock)
        response.begin()
        connection=Mock()
        connection.sock=sock
        connection.getresponse.return_value=response
        client=native.NativeObservations(ca_pem=b'fixture',ca_sha256='0'*64,
                        token='offline',deadline=time.monotonic()+30)
        try:
            with patch.object(native,'_connection',return_value=connection):
                return client._get(native.BASE+'/actions/runs/12')
        finally:
            self.assertEqual(connection.request.call_count,1)
            connection.close.assert_called_once()

    def test_content_length_completion_without_closed_socket_reuse(self):
        self.assertEqual(self.read_wire(b'Content-Length: 2\r\n',b'{}'),{})

    def test_chunked_completion_consumes_terminal_chunk(self):
        self.assertEqual(self.read_wire(b'Transfer-Encoding: chunked\r\n',
                                      b'2\r\n{}\r\n0\r\n\r\n'),{})

    def test_close_delimited_completion(self):
        self.assertEqual(self.read_wire(b'Connection: close\r\n',b'{}'),{})

    def test_conflicting_length_and_transfer_refused(self):
        with self.assertRaisesRegex(ContractError,'framing'):
            self.read_wire(b'Content-Length: 2\r\nTransfer-Encoding: chunked\r\n',
                           b'2\r\n{}\r\n0\r\n\r\n')

    def test_unsupported_transfer_refused(self):
        with self.assertRaisesRegex(ContractError,'framing'):
            self.read_wire(b'Transfer-Encoding: gzip\r\n',b'{}')

    def test_duplicate_transfer_refused(self):
        with self.assertRaisesRegex(ContractError,'framing'):
            self.read_wire(b'Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n',
                           b'2\r\n{}\r\n0\r\n\r\n')

    def test_truncated_content_length_refused(self):
        with self.assertRaisesRegex(ContractError,'truncated'):
            self.read_wire(b'Content-Length: 3\r\n',b'{}')

    def test_truncated_chunk_refused(self):
        with self.assertRaisesRegex(ContractError,'outcome-unknown'):
            self.read_wire(b'Transfer-Encoding: chunked\r\n',b'3\r\n{}')
