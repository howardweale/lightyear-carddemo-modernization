"""Proposal-only negative controls using retained public framework bytes locally."""
import copy
import json
from pathlib import Path
import unittest
from tools.b06_host_probe.pool_analysis import compare_extension,check_methods

ROOT=Path(__file__).resolve().parents[1]
AREA=ROOT/'work/b06-observer-v2-host'
SOURCE=ROOT/'work/b06-admission-r4/b06-catalog-r4-0fc42f4b1ed248debefbf84b45042c5f/class-bytes/b6ebf7618c7572195ec833104be65f54aaa090263dc14297bd471f9c4a1cd056.class'


@unittest.skipUnless(SOURCE.exists() and (AREA/'surefire59-baseline/observations.json').exists(), 'local host experiment not present; no native substitute')
class PoolProposalTests(unittest.TestCase):
    def setUp(self):
        self.source=SOURCE.read_bytes()
        self.a=json.loads((AREA/'surefire59-baseline/observations.json').read_text())['samples'][0]['definition']
        self.b=json.loads((AREA/'platform191-none-experiment/observations/observations.json').read_text())['samples'][0]['definition']

    def test_two_real_runtime_orders_canonicalize_equally(self):
        values=[compare_extension(self.source,v['constant_pool_hex'],v['constant_pool_count']) for v in (self.a,self.b)]
        self.assertNotEqual(values[0]['raw_sha256'],values[1]['raw_sha256'])
        self.assertEqual(values[0]['canonical_sha256'],values[1]['canonical_sha256'])
        self.assertEqual(values[1]['raw_sha256'],'b6eb2698546644b688cf9fc195a7445dff77fea21a0de5125e5f929440e14411')

    def test_prefix_corruption_is_never_normalized(self):
        raw=bytearray.fromhex(self.b['constant_pool_hex']);raw[5]^=1
        with self.assertRaisesRegex(ValueError,'prefix'):compare_extension(self.source,raw.hex(),159)

    def test_wrong_error_target_and_unknown_tail_fail(self):
        raw=bytes.fromhex(self.b['constant_pool_hex'])
        for broken in (raw.replace(b'AbstractMethodError',b'AbstractMethodErroX'),raw+b'\x01\x00\x01x'):
            with self.assertRaises(ValueError):compare_extension(self.source,broken.hex(),159)

    def test_missing_count_or_changed_source_fail(self):
        with self.assertRaises(ValueError):compare_extension(self.source,self.b['constant_pool_hex'],158)
        with self.assertRaises(ValueError):compare_extension(self.source+b'x',self.b['constant_pool_hex'],159)

    def test_method_changes_are_not_hidden_by_pool_comparison(self):
        self.assertEqual(check_methods(self.source,self.b['methods']),5)
        methods=copy.deepcopy(self.b['methods']);methods[0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'methods'):check_methods(self.source,methods)

    def test_changed_or_missing_method_access_flags_fail(self):
        for missing in (False,True):
            methods=copy.deepcopy(self.b['methods'])
            if missing:methods[0].pop('modifiers')
            else:methods[0]['modifiers']^=8
            with self.assertRaisesRegex(ValueError,'flags'):check_methods(self.source,methods)


if __name__=='__main__':unittest.main()
