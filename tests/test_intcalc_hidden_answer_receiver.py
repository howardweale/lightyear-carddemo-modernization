"""Only fake streams and fake custodian ports. No age, USB, host or candidate."""
from contextlib import nullcontext
from io import BytesIO
import pickle
import time
import unittest
from unittest.mock import Mock, patch

from tools import generate_intcalc_heldout_inputs as generator
from tools import intcalc_heldout_encrypted_stream as w
from tools import intcalc_hidden_answer_receiver as r


def canonical_case(i):
    return dict(sequence=i, inputs={dd: '7879' for dd in w.FIELDS},
                processing_date='2026111600', timestamp='2026-11-16-12.00.00.770000',
                outputs={'ACCTFILE': 'ab', 'TRANSACT': '', 'stdout': '68756d616e', 'stderr': ''},
                exit=0, compare_output_files=True)


class Source(BytesIO):
    def read(self, size, end):
        return super().read(min(13, size))


def example(count=3):
    cases = [canonical_case(i) for i in range(count)]
    source = {'generator_sha256': 'f' * 64}
    # The serializer only. No random data, seed or generator invocation.
    raw_input = generator.private_payload([dict(id=f'HC-{i+1:03d}', timestamp=case['timestamp'],
                processing_date=case['processing_date'], inputs={k: bytes.fromhex(v) for k,v in case['inputs'].items()})
                for i,case in enumerate(cases)], source)
    binding = {k: ('d'*40 if k in ('source_commit','source_tree') else 'f'*64) for k in w.BINDINGS}
    binding['input_commitment_sha256'] = w.sha(raw_input)
    stream = BytesIO()
    frame = w.Framer(stream, w.checked_binding(binding), count)
    for case in cases:
        frame.case(case)
    frame.finish()
    value = dict(schema='heldout-private-completion/1',bindings=binding,count=count,
                 ciphertext=dict(sha256='a'*64,bytes=128), postflight_sha256='c'*64,cleanup=True)
    complete = w.canonical(value) + b'\n'
    approval = dict(operation_id='a'*64,stage1_sha256='b'*64,jar_sha256='a'*64,
                    completion_sha256=w.sha(complete),bindings_sha256=w.checked_binding(binding),
                    input_sha256=w.sha(raw_input),age_sha256=binding['encryptor_sha256'],
                    source_manifest_sha256=w.sha(w.canonical(source)),count=count,plaintext_cap=w.STREAM_CAP)
    return cases, stream.getvalue(), source, complete, approval


def read_frames(stream, approval, source):
    return r.decode(Source(stream), approval, source, time.monotonic() + 10)


class ReceiverTests(unittest.TestCase):
    def test_matches_real_writer_and_generator_serializer(self):
        cases, stream, source, _, approval = example()
        self.assertEqual(read_frames(stream,approval,source), [w.canonical(x) for x in cases])

    def test_truncated_and_extra_suffix_refuse(self):
        _, stream, source, _, approval = example()
        for bad in [b'', stream[:8], stream[:-1], stream + b'x']:
            with self.subTest(length=len(bad)), self.assertRaises(r.Refused):
                read_frames(bad,approval,source)

    def test_tampered_frame_refuses_even_when_valid_json(self):
        _, stream, source, _, approval = example()
        with self.assertRaisesRegex(r.Refused,'receive-trailer'):
            read_frames(stream.replace(b'68756d616e',b'68756d616f',1), approval,source)

    def test_input_precommitment_recomputed(self):
        _, stream, source, _, approval = example()
        with self.assertRaisesRegex(r.Refused,'receive-input-manifest'):
            read_frames(stream, dict(approval,input_sha256='e'*64), source)

    def test_length_before_allocation_and_total_budget(self):
        _, stream, source, _, approval = example()
        for data, cap in [((w.CASE_CAP + 1).to_bytes(8,'big'), w.STREAM_CAP), (stream, len(stream)-1)]:
            with self.assertRaisesRegex(r.Refused,'receive-limit'):
                read_frames(data, dict(approval,plaintext_cap=cap), source)

    def test_canonical_duplicate_and_float_refused(self):
        for raw in [b'{"a":0,"a":1}', b'{"a":0.0}', b'{"a":NaN}', b'{ "a":1}']:
            with self.subTest(raw=raw), self.assertRaises(r.Refused):
                r.strict(raw,128)

    def test_changed_completion_fails_before_cipher_open(self):
        _, _, _, raw, approval = example()
        with self.assertRaisesRegex(r.Refused,'receive-commitment'):
            r.completion(raw + b'\n', approval)
        self.assertEqual(r.completion(raw,approval)['schema'],'heldout-private-completion/1')

    def test_wrong_bound_age_refuses(self):
        _, _, _, raw, approval = example()
        with self.assertRaisesRegex(r.Refused,'receive-binding'):
            r.completion(raw,dict(approval,age_sha256='1'*64))

    def broker_run(self, *, claim=True, exit_ok=True, custody=True, corrupt=False, over=False):
        cases, stream, source, raw, approval = example()
        events = []
        proof = dict(claim_sha256='c'*64,operation_id=approval['operation_id'],
                     decryptor_exited=True,group_absent=True,handles_closed=True,usb_mount_absent=custody,
                     howard_removed_usb=custody,howard_no_identity_copy=custody,codex_absent=True)
        class Session:
            def __enter__(self):
                return self
            def __exit__(self,*args):
                events.append('session-closed')
            def pipe(self):
                events.append('pipe')
                return Source(stream[:-1] if corrupt else stream)
            def join_success(self,deadline):
                events.append('join')
                return exit_ok
        class Broker:
            def claim(self, approval, deadline):
                events.append('claim')
                return 'c'*64 if claim else None
            def read_completion(self,claim,deadline):
                events.append('completion')
                return raw
            def open_cipher(self,claim,deadline):
                events.append('cipher')
                return nullcontext(5)
            def decrypt(self,fd,claim,digest,deadline):
                events.append('decrypt')
                return Session()
            def removal_receipt(self,claim,deadline):
                events.append('removal')
                return proof
        receiver = r.Receiver()
        self.events = events
        return receiver,lambda: receiver.receive(approval,source,Broker(),
                    time.monotonic() + (-1 if over else 10)),cases

    def run_with_broker(self, **kwargs):
        receiver,start,cases=self.broker_run(**kwargs)
        with patch.object(r,'verify_cipher',side_effect=lambda *_: self.events.append('cipher-verified')):
            return receiver,start(),cases

    def test_claim_must_precede_any_private_access(self):
        with self.assertRaisesRegex(r.Refused,'receive-claim'):
            self.run_with_broker(claim=False)
        self.assertEqual(self.events,['claim'])

    def test_release_only_after_eof_exit_and_usb_removal(self):
        _,handoff,cases=self.run_with_broker()
        self.assertEqual(self.events,['claim','completion','cipher','cipher-verified','decrypt','pipe','join',
                                     'session-closed','removal'])
        with self.assertRaisesRegex(r.Refused,'receive-private'):
            pickle.dumps(handoff)
        got=handoff.consume(lambda frames,claim,removal:list(frames))
        self.assertEqual(got,[w.canonical(case) for case in cases])
        with self.assertRaisesRegex(r.Refused,'receive-consumed'):
            handoff.consume(Mock())

    def test_nonzero_exit_never_releases(self):
        with self.assertRaisesRegex(r.Refused,'receive-age-exit'):
            self.run_with_broker(exit_ok=False)
        self.assertNotIn('removal',self.events)

    def test_usb_or_copy_confirmation_stops(self):
        with self.assertRaisesRegex(r.Refused,'receive-custody'):
            self.run_with_broker(custody=False)

    def test_incomplete_stream_closes_broker_without_handoff(self):
        with self.assertRaises(r.Refused):
            self.run_with_broker(corrupt=True)
        self.assertIn('session-closed',self.events)
        self.assertNotIn('join',self.events)

    def test_deadline_refusal_and_terminal_instance(self):
        receiver, start, _ = self.broker_run(over=True)
        with self.assertRaisesRegex(r.Refused,'receive-deadline'):
            start()
        self.assertEqual(self.events,[])
        with self.assertRaisesRegex(r.Refused,'receive-consumed'):
            receiver.receive(None,None,None,0)
