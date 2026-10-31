"""Offline refusal tests; fixtures never grant approval or native admission."""
import copy
import hashlib
import json
import unittest

from lightyear_factory.contracts import ContractError
from tools.ci import supervised_session_reservation as session


class SupervisedSessionReservationTests(unittest.TestCase):
    def binding(self):
        return dict(label=session.LABEL, session_sha256='1'*64,
                    packet_sha256='2'*64, source_sha='3'*40,
                    workflow_sha256=hashlib.sha256(b'public workflow fixture').hexdigest(),
                    workflow_path='.github/workflows/supervised-intcalc-engineering.yml',
                    workflow_id=11, run_id=12, run_attempt=1, sender_job_name='supervised-sender',
                    round=1, request_sha256='5'*64, previous_receipt_sha256=None,
                    continuation_sha256=None, qualification_evidence=False)

    def observations(self, value):
        run = dict(id=value['run_id'], run_attempt=1,
                   workflow_id=value['workflow_id'], head_sha=value['source_sha'],
                   repository={'full_name':session.REPOSITORY},
                   event='workflow_dispatch', path=value['workflow_path'],
                   status='in_progress')
        job = dict(id=13, run_id=value['run_id'],
                   run_attempt=1, head_sha=value['source_sha'],
                   name='supervised-sender', status='in_progress')
        return run, job

    def handoff(self, value, record, run, job):
        _, original = self.observations(value)
        result = session.checked_sender_handoff(value,record,run,job,
            {'total_count':1,'jobs':[original]},b'public workflow fixture')
        self.assertEqual(result['sender_job_id'],13)
        self.assertFalse(result['qualification_evidence'])
        return result['binding']

    def second(self, outcome='FAIL'):
        value = self.binding()
        previous = json.dumps(dict(label=session.LABEL,
            session_sha256=value['session_sha256'], packet_sha256=value['packet_sha256'],
            source_sha=value['source_sha'], round=1, outcome=outcome,
            qualification_evidence=False)).encode()
        continuation = b'unsigned offline continuation fixture, not human approval'
        value.update(round=2, previous_receipt_sha256=hashlib.sha256(previous).hexdigest(),
                     continuation_sha256=hashlib.sha256(continuation).hexdigest())
        return value, previous, continuation

    def test_same_session_round_collides_across_dispatches(self):
        first = self.binding()
        other = dict(first, run_id=99, request_sha256='a'*64)
        self.assertEqual(session.reservation_ref(first), session.reservation_ref(other))
        self.assertNotEqual(session.canonical_record(first), session.canonical_record(other))

    def test_only_two_fixed_round_refs(self):
        value = self.binding()
        first = session.reservation_ref(value)
        second, _, _ = self.second()
        self.assertTrue(first.endswith('-round-1'))
        self.assertTrue(session.reservation_ref(second).endswith('-round-2'))
        for number in (0, 3, -1, True, 1.0, '1'):
            with self.subTest(number=number), self.assertRaises(ContractError):
                session.reservation_ref(dict(value, round=number))

    def test_rerun_and_boolean_native_ids_refuse(self):
        value = self.binding()
        for patch in ({'run_attempt':2},{'run_attempt':True},{'run_id':True},
                      {'sender_job_name':'other'},{'workflow_id':'11'}):
            with self.subTest(patch=patch), self.assertRaises(ContractError):
                session.checked_binding(dict(value, **patch))

    def test_unexpected_fields_and_qualified_label_refuse(self):
        value = self.binding()
        for patch in ({'extra':'value'},{'qualification_evidence':True},
                      {'label':'qualified production run'}):
            with self.subTest(patch=patch), self.assertRaises(ContractError):
                session.checked_binding(dict(value, **patch))

    def test_ref_path_injection_refuses(self):
        value = self.binding()
        for key, content in (('session_sha256','../other'),('source_sha','HEAD'),
                             ('workflow_path','.github/workflows/other.yml')):
            with self.subTest(key=key), self.assertRaises(ContractError):
                session.checked_binding(dict(value, **{key:content}))

    def test_create_requires_this_successful_post(self):
        value = self.binding()
        response = dict(ref=session.reservation_ref(value),
                        object={'type':'commit','sha':'a'*40})
        for status in (200, 202, 409, 422, 500, None, True):
            with self.subTest(status=status), self.assertRaises(ContractError):
                session.checked_create_ack(value, 'a'*40, status, response)
        receipt = session.checked_create_ack(value, 'a'*40, 201, response)
        self.assertEqual(receipt['record_sha256'],
                         hashlib.sha256(session.canonical_record(value)).hexdigest())
        self.assertFalse(receipt['qualification_evidence'])

    def test_wrong_ref_or_commit_ack_refuses(self):
        value = self.binding()
        responses = [
            dict(ref='refs/tags/other',object={'type':'commit','sha':'a'*40}),
            dict(ref=session.reservation_ref(value),object={'type':'commit','sha':'b'*40}),
            dict(ref=session.reservation_ref(value),object={'type':'tag','sha':'a'*40})]
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ContractError):
                session.checked_create_ack(value, 'a'*40, 201, response)

    def test_handoff_requires_exact_stored_bytes(self):
        value = self.binding()
        run, job = self.observations(value)
        record = session.canonical_record(value)
        self.assertEqual(self.handoff(value,record,run,job), value)
        for wrong in (record+b' ', session.canonical_record(dict(value,run_id=88))):
            with self.subTest(wrong=wrong), self.assertRaises(ContractError):
                self.handoff(value,wrong,run,job)

    def test_cross_run_sender_cannot_adopt_reservation(self):
        value = self.binding()
        run, job = self.observations(value)
        for key, changed in (('id',99),('run_attempt',2),('workflow_id',99),
                             ('head_sha','b'*40),('event','pull_request'),
                             ('path','.github/workflows/other.yml'),('status','completed'),
                             ('repository',{'full_name':'another/repo'})):
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.handoff(value,session.canonical_record(value),
                                               dict(run,**{key:changed}),job)

    def test_other_job_or_attempt_cannot_adopt_reservation(self):
        value = self.binding()
        run, job = self.observations(value)
        for key, changed in (('id',99),('run_id',99),('run_attempt',2),
                             ('head_sha','b'*40),('name','other'),
                             ('status','completed')):
            with self.subTest(key=key), self.assertRaises(ContractError):
                self.handoff(value,session.canonical_record(value),
                                               run,dict(job,**{key:changed}))

    def test_second_round_requires_failed_completed_verdict(self):
        for outcome in ('PASS','UNKNOWN','ERROR','PENDING'):
            value, previous, continuation = self.second(outcome)
            with self.subTest(outcome=outcome), self.assertRaises(ContractError):
                session.checked_second_round(value, previous, continuation)
        value, previous, continuation = self.second()
        self.assertEqual(session.checked_second_round(value,previous,continuation),value)

    def test_changed_previous_receipt_or_continuation_refuses(self):
        value, previous, continuation = self.second()
        for old, human in ((previous+b' ',continuation),(previous,continuation+b' '),
                           (previous,b'')):
            with self.subTest(old=old,human=human), self.assertRaises(ContractError):
                session.checked_second_round(value,old,human)

    def test_previous_other_session_or_source_refuses_even_with_matching_hash(self):
        value, previous, continuation = self.second()
        for key, changed in (('session_sha256','a'*64),('packet_sha256','a'*64),
                             ('source_sha','a'*40),('round',True),
                             ('qualification_evidence',True)):
            receipt = json.loads(previous)
            receipt[key] = changed
            raw = json.dumps(receipt).encode()
            adjusted = dict(value,previous_receipt_sha256=hashlib.sha256(raw).hexdigest())
            with self.subTest(key=key), self.assertRaises(ContractError):
                session.checked_second_round(adjusted,raw,continuation)

    def test_duplicate_previous_verdict_key_refuses(self):
        value, previous, continuation = self.second()
        raw = previous[:-1]+b', "outcome":"FAIL"}'
        value['previous_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ContractError):
            session.checked_second_round(value,raw,continuation)

    def test_first_round_cannot_claim_continuation(self):
        value = self.binding()
        with self.assertRaises(ContractError):
            session.checked_binding(dict(value,previous_receipt_sha256='a'*64))
        second, _, _ = self.second()
        with self.assertRaises(ContractError):
            session.checked_binding(dict(second,continuation_sha256=None))

    def test_validation_returns_copy_not_mutable_alias(self):
        value = self.binding()
        result = session.checked_binding(value)
        value['round'] = 3
        self.assertEqual(result['round'],1)


    def test_incomplete_duplicated_or_ambiguous_sender_list_refuses(self):
        value = self.binding()
        run, job = self.observations(value)
        record = session.canonical_record(value)
        other = dict(job,id=14)
        for listing in ({'total_count':2,'jobs':[job]},
                        {'total_count':2,'jobs':[job,job]},
                        {'total_count':2,'jobs':[job,other]},
                        {'total_count':1,'jobs':[dict(job,run_id=99)]},
                        {'total_count':True,'jobs':[job]}):
            with self.subTest(listing=listing), self.assertRaises(ContractError):
                session.checked_sender_handoff(value,record,run,job,listing,
                                               b'public workflow fixture')

    def test_changed_workflow_bytes_refuse(self):
        value = self.binding()
        run, job = self.observations(value)
        with self.assertRaises(ContractError):
            session.checked_sender_handoff(value,session.canonical_record(value),
                run,job,{'total_count':1,'jobs':[job]},b'other workflow')

    def test_reservation_needs_role_not_unallocated_job_id(self):
        value = self.binding()
        self.assertNotIn('sender_job_id',value)
        self.assertEqual(session.checked_binding(value)['sender_job_name'],
                         'supervised-sender')
        with self.assertRaises(ContractError):
            session.checked_binding(dict(value,sender_job_id=13))
