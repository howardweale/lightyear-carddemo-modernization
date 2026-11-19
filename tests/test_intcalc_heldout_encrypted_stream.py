"""Public synthetic data only; no age, key, generator, Docker or host operation."""
import copy
import unittest
from tools import intcalc_heldout_encrypted_stream as m


def case():
    return dict(sequence=0, inputs={k:'41' for k in m.FIELDS}, outputs={k:'42' for k in m.CHANNELS},
        processing_date='2026111600', timestamp='2026-11-16-12.00.00.000000', exit=0, compare_output_files=True)


class Sink:
    def __init__(self): self.parts=[]; self.finished=False; self.aborted=False
    def write(self, raw): self.parts.append(raw)
    def finish(self): self.finished=True
    def abort(self): self.aborted=True


class Store:
    def __init__(self): self.raw=None; self.closed=False; self.events=[]
    def start(self): self.events.append('ciphertext'); return 17
    def seal_ciphertext(self): self.events.append('readback'); return dict(sha256='a'*64,bytes=100)
    def complete(self, raw): self.events.append('manifest'); self.raw=raw
    def close(self): self.closed=True


class StreamTests(unittest.TestCase):
    def binding(self):
        return {k:'a'*(40 if k in ('source_commit','source_tree') else 64) for k in m.BINDINGS}
    def run_rows(self, rows, producer=lambda:True, post=lambda:'b'*64):
        store, sink = Store(), Sink()
        result=m.write_answers(rows,1,self.binding(),store,lambda fd,d:sink,producer,post,10,clock=lambda:0)
        return result,store,sink
    def test_manifest_last_and_public_only_commitment(self):
        r,s,k=self.run_rows([case()]); self.assertEqual(s.events,['ciphertext','readback','manifest'])
        self.assertEqual(set(r),{'schema','commitment_sha256'});self.assertEqual(r['commitment_sha256'],m.sha(s.raw));self.assertTrue(k.finished and s.closed)
    def test_private_frames_only_sink(self):
        _,s,k=self.run_rows([case()]);self.assertIn(b'"inputs"',b''.join(k.parts));self.assertNotIn(b'"inputs"',s.raw)
    def test_float_refused(self):
        with self.assertRaisesRegex(m.Refused,'stream-shape'):m.canonical({'x':1.0})
    def test_nonstring_key_refused(self):
        with self.assertRaises(m.Refused):m.canonical({1:2})
    def test_order_refused(self):
        c=case();c['sequence']=1
        with self.assertRaisesRegex(m.Refused,'stream-order'):self.run_rows([c])
    def test_duplicate_case_refused(self):
        with self.assertRaisesRegex(m.Refused,'stream-count'):self.run_rows([case(),case()])
    def test_missing_case_refused(self):
        with self.assertRaisesRegex(m.Refused,'stream-count'):self.run_rows([])
    def test_producer_failure_no_manifest(self):
        s,k=Store(),Sink()
        with self.assertRaisesRegex(m.Refused,'stream-producer'):
            m.write_answers([case()],1,self.binding(),s,lambda fd,d:k,lambda:False,lambda:'b'*64,10,clock=lambda:0)
        self.assertIsNone(s.raw);self.assertTrue(k.aborted)
    def test_postflight_failure_no_manifest(self):
        with self.assertRaisesRegex(m.Refused,'stream-binding'):self.run_rows([case()],post=lambda:None)
    def test_binding_missing(self):
        b=self.binding();b.pop('authority_sha256')
        with self.assertRaises(m.Refused):m.checked_binding(b)
    def test_altered_binding_changes_commitment(self):
        b=self.binding();c=copy.deepcopy(b);c['authority_sha256']='b'*64
        self.assertNotEqual(m.checked_binding(b),m.checked_binding(c))
    def test_unsafe_extra_key(self):
        c=case();c['path']='private-diagnostic'
        with self.assertRaises(m.Refused):self.run_rows([c])
    def test_upper_hex_refused(self):
        c=case();c['inputs']['ACCTFILE']='AA'
        with self.assertRaises(m.Refused):self.run_rows([c])
    def test_odd_hex_refused(self):
        c=case();c['inputs']['ACCTFILE']='a'
        with self.assertRaises(m.Refused):self.run_rows([c])
    def test_abend_omits_unsettled_files(self):
        c=case();c.update(exit=12,compare_output_files=False);c['outputs']['ACCTFILE']=c['outputs']['TRANSACT']=''
        self.run_rows([c])
    def test_abend_cannot_freeze_unsettled_files(self):
        c=case();c.update(exit=12,compare_output_files=False)
        with self.assertRaises(m.Refused):self.run_rows([c])
    def test_infrastructure_exit_refused(self):
        c=case();c['exit']=1
        with self.assertRaisesRegex(m.Refused,'stream-producer'):self.run_rows([c])
    def test_boolean_sequence_refused(self):
        c=case();c['sequence']=False
        with self.assertRaises(m.Refused):self.run_rows([c])
    def test_expired_before_open(self):
        s,k=Store(),Sink()
        with self.assertRaisesRegex(m.Refused,'stream-deadline'):
            m.write_answers([],1,self.binding(),s,lambda fd,d:k,lambda:True,lambda:'b'*64,0,clock=lambda:0)
        self.assertEqual(s.events,[])
    def test_frame_length_matches(self):
        k=Sink();f=m.Framer(k,'a'*64,1);f.case(case());f.finish()
        for b in k.parts:self.assertEqual(int.from_bytes(b[:8],'big'),len(b)-8)
    def test_finish_twice_refused(self):
        k=Sink();f=m.Framer(k,'a'*64,1);f.case(case());f.finish()
        with self.assertRaises(m.Refused):f.finish()
    def test_size_bound(self):
        c=case();c['outputs']['stdout']='ab'*(m.CASE_CAP//2+1)
        with self.assertRaises(m.Refused):m.checked_case(c,0)
    def test_error_redaction(self):
        self.assertEqual(m.refusal(ValueError('secret-canary')),'stream-fault')
    def test_sink_fault_aborts_no_manifest(self):
        s,k=Store(),Sink()
        def fail(raw):raise OSError('secret-canary')
        k.write=fail
        with self.assertRaises(OSError):m.write_answers([case()],1,self.binding(),s,lambda fd,d:k,lambda:True,lambda:'b'*64,10,clock=lambda:0)
        self.assertIsNone(s.raw);self.assertTrue(s.closed and k.aborted)


if __name__ == '__main__': unittest.main()
