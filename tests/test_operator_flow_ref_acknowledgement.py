"""Original local Git acknowledgement and no-op refusal, CI only."""
import unittest
import test_operator_flow_ref_lease as fixtures
from tools.ci.operator_flow_ref_lease import verify_ref_push_acknowledgement

class RefAcknowledgement(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ExactRefLease();self.f.setUp();self.addCleanup(self.f.doCleanups)
    def verify(self,raw,code=0):
        return verify_ref_push_acknowledgement(self.f.c,raw,code,executable=self.f.E,
            metadata_head=self.f.M,branch_ref=self.f.branch)
    def test_original_native_fast_forward_acknowledgement(self):
        p=self.f.push();self.assertEqual(p.returncode,0)
        result=self.verify(p.stdout,p.returncode)
        self.assertEqual(result['metadata_head'],self.f.M);self.assertFalse(result['publication_authorized'])
        self.assertEqual(self.f.rgit('rev-parse',self.f.branch).decode().strip(),self.f.M)
    def test_already_M_success_is_not_a_second_publication(self):
        self.assertEqual(self.f.push().returncode,0)
        p=self.f.push();self.assertEqual(p.returncode,0)
        with self.assertRaisesRegex(ValueError,'fast-forward-only'):self.verify(p.stdout,p.returncode)
        self.assertEqual(self.f.rgit('rev-parse',self.f.branch).decode().strip(),self.f.M)
    def test_changed_scope_multiple_rows_and_non_update_flags_refuse(self):
        p=self.f.push();self.assertEqual(p.returncode,0);lines=p.stdout.decode().splitlines()
        for flag in ('=','+','*','-','!'):
            changed=list(lines);changed[1]=flag+changed[1][1:]
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.verify(('\n'.join(changed)+'\n').encode())
        with self.assertRaises(ValueError):self.verify(p.stdout.replace(self.f.branch.encode(),b'refs/heads/main'))
        with self.assertRaises(ValueError):self.verify(('\n'.join(lines[:2]+lines[1:])+'\n').encode())
    def test_failed_truncated_or_changed_range_never_resumes(self):
        p=self.f.push();self.assertEqual(p.returncode,0)
        for raw,code in ((p.stdout,1),(p.stdout,True),(p.stdout[:12],0),(b'x'*16385,0)):
            with self.subTest(code=code),self.assertRaises(ValueError):self.verify(raw,code)
        lines=p.stdout.decode().splitlines();fields=lines[1].split('\t');fields[2]='0000000..1111111';lines[1]='\t'.join(fields)
        with self.assertRaisesRegex(ValueError,'E-M-range'):self.verify(('\n'.join(lines)+'\n').encode())
