"""Declared public synthetic seeds only; no generated suite is uploaded."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import generate_intcalc_heldout_inputs as g
from lightyear_mainframe.records import load_copybook
from tools.intcalc_reference_execution import preferred_signs, clock_env

ROOT=Path(__file__).resolve().parents[1]
SYNTHETIC_SEED=bytes(range(32))


class FreshInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layouts={dd:load_copybook(ROOT/'spec/mainframe/copybooks'/name) for dd,name in g.COPYBOOKS.items()}

    def test_generated_clock_matches_reference_input_contract(self):
        cases=g.generate_inputs(SYNTHETIC_SEED,2,self.layouts)
        for case in cases:
            env=clock_env(case['timestamp'],case['processing_date'])
            self.assertEqual(env['TWIN_PROCESSING_DATE'],case['processing_date'])

    def test_seed_shape_refuses(self):
        for seed in ('secret',b'abc',bytes(31),bytes(33)):
            with self.assertRaises(g.Refused):g.Draws(seed)

    def test_labelled_draws_reproduce_and_domain_is_bounded(self):
        a=g.Draws(SYNTHETIC_SEED);b=g.Draws(SYNTHETIC_SEED)
        for i in range(40):
            self.assertEqual(a.below(str(i),101),b.below(str(i),101))
            self.assertTrue(0<=a.below(str(i),101)<101)

    def test_draw_domain_refusals(self):
        for limit in (0,-1,True,2**64+1):
            with self.assertRaises(g.Refused):g.Draws(SYNTHETIC_SEED).below('x',limit)

    def test_all_synthetic_generated_inputs_preferred_and_framed(self):
        cases=g.generate_inputs(SYNTHETIC_SEED,8,self.layouts)
        self.assertEqual(len(cases),8)
        for case in cases:
            for dd,raw in case['inputs'].items():
                preferred_signs(raw,self.layouts[dd],g.DDS[dd][0])
                self.assertEqual(len(raw)%g.DDS[dd][0],0)

    def test_deterministic_private_payload(self):
        a=g.private_payload(g.generate_inputs(SYNTHETIC_SEED,2,self.layouts),{})
        b=g.private_payload(g.generate_inputs(SYNTHETIC_SEED,2,self.layouts),{})
        self.assertEqual(a,b)
        self.assertNotIn(SYNTHETIC_SEED.hex().encode(),a)
        self.assertNotEqual(a,g.private_payload(g.generate_inputs(bytes(reversed(range(32))),2,self.layouts),{}))

    def test_case_count_and_dd_set_refuse(self):
        for n in (0,65,True):
            with self.assertRaises(g.Refused):g.generate_inputs(SYNTHETIC_SEED,n,self.layouts)
        with self.assertRaises(g.Refused):g.generate_inputs(SYNTHETIC_SEED,1,{})

    def test_zoned_zero_and_negative_have_c_and_d(self):
        field=next(f for f in self.layouts['TCATBALF'].fields if f.signed)
        self.assertEqual(g.encode(field,0)[-1]>>4,12)
        self.assertEqual(g.encode(field,-5)[-1]>>4,13)

    def test_unsigned_negative_and_overflow_refuse(self):
        f=next(f for f in self.layouts['ACCTFILE'].fields if f.digits and not f.signed)
        for value in (-1,10**f.digits,1.0):
            with self.assertRaises(g.Refused):g.encode(f,value)

    def test_unknown_field_refuses(self):
        with self.assertRaises(g.Refused):g.record(self.layouts['ACCTFILE'],{'UNKNOWN':1})

    def test_validator_rejects_mutated_nonpreferred_sign(self):
        layout=self.layouts['TCATBALF'];raw=bytearray(g.record(layout,{}))
        f=next(f for f in layout.fields if f.signed);raw[f.offset+f.length-1]|=0xF0
        with self.assertRaises(ValueError):preferred_signs(bytes(raw),layout,layout.record_length)

    def test_non_tty_refuses_without_seed_prompt(self):
        with tempfile.TemporaryDirectory() as td, patch.object(g.getpass,'getpass') as prompt:
            err=io.StringIO()
            with contextlib.redirect_stderr(err),patch.object(g.sys,'stdin',io.StringIO()),patch.object(g.sys,'stdout',io.StringIO()):
                rc=g.main(['--source-root',td,'--source-manifest',td+'/missing','--manifest-sha256','0'*64,'--private-parent',td,'--run-name','fresh','--cases','1'])
            self.assertEqual(rc,2);prompt.assert_not_called()
            self.assertEqual(err.getvalue(),('attended-terminal' if os.name=='posix' else 'platform')+'\n')

    def test_unknown_argument_never_echoed(self):
        err=io.StringIO()
        with contextlib.redirect_stderr(err):self.assertEqual(g.main(['--seed','SENTINEL_PRIVATE_SEED']),2)
        self.assertNotIn('SENTINEL',err.getvalue())

    def test_private_exclusive_write_or_clean_platform_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            parent=Path(td).resolve()
            if os.name!='posix':
                with self.assertRaisesRegex(g.Refused,'platform'):g.persist(parent,'fresh',b'public synthetic')
                return
            parent.chmod(0o700)
            payload=b'public synthetic'
            self.assertEqual(g.persist(parent,'fresh',payload),g.sha(payload))
            self.assertEqual((parent/'fresh/inputs.json').stat().st_mode&0o777,0o600)
            self.assertEqual((parent/'fresh').stat().st_mode&0o777,0o700)
            with self.assertRaises(FileExistsError):g.persist(parent,'fresh',payload)

    def test_private_parent_mode_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td).resolve()
            if os.name!='posix':
                with self.assertRaisesRegex(g.Refused,'platform'):g.checked_parent(p)
            else:
                p.chmod(0o755)
                with self.assertRaisesRegex(g.Refused,'private-parent'):g.checked_parent(p)

    def test_no_expected_answers_generated(self):
        cases=g.generate_inputs(SYNTHETIC_SEED,1,self.layouts)
        self.assertEqual(set(cases[0]),{'id','processing_date','timestamp','inputs'})
        self.assertEqual(set(cases[0]['inputs']),set(g.COPYBOOKS))


    def test_scenario_weight_partition_exact(self):
        counts=[sum(g.scenario(i)==mode for i in range(100)) for mode in range(5)]
        self.assertEqual(counts,[70,15,5,5,5])

    def test_balance_and_rate_domains_with_explicit_zero(self):
        class D:
            def __init__(self,value):self.value=value
            def below(self,label,size):return self.value%size
        self.assertEqual(g.balance(D(0),'x',False),-1000000000)
        self.assertTrue(90000000000<=abs(g.balance(D(1),'x',True))<=99999999999)
        self.assertEqual(g.rate(D(0),'x',False),0)
        self.assertTrue(1<=g.rate(D(1),'x',False)<=3600)
        self.assertTrue(900000<=g.rate(D(1),'x',True)<=999999)

    def test_default_case_contains_direct_and_default_rates(self):
        class D:
            def __init__(self,seed):pass
            def below(self,label,size):
                if label.endswith('lookup-mode'):return 70
                return 1%size
        with patch.object(g,'Draws',D):case=g.generate_inputs(SYNTHETIC_SEED,1,self.layouts)[0]
        layout=self.layouts['DISCGRP'];f=next(f for f in layout.fields if f.path.endswith('DIS-ACCT-GROUP-ID'))
        raw=case['inputs']['DISCGRP'];groups={raw[i+f.offset:i+f.offset+f.length].decode('cp037').strip() for i in range(0,len(raw),layout.record_length)}
        self.assertIn('DEFAULT',groups);self.assertIn('G00',groups)
        self.assertTrue(case['inputs']['TCATBALF'])

    def test_closed_refusals_never_dynamic_text(self):
        self.assertEqual(g.refusal_code(g.Refused('field-overflow')),'field-overflow')
        self.assertEqual(g.refusal_code(g.Refused('SECRET SENTINEL')),'fresh-inputs-refused')
        self.assertEqual(g.refusal_code(RuntimeError('SECRET SENTINEL')),'fresh-inputs-refused')
        self.assertEqual(g.refusal_code(g.ReferenceRefused('reference-sign-layout')),'reference-sign-layout')
        self.assertEqual(g.refusal_code(g.Refused(['secret'])),'fresh-inputs-refused')

    def test_cli_fixed_code_is_printed(self):
        err=io.StringIO()
        with contextlib.redirect_stderr(err):rc=g.main(['--unexpected-private-argument'])
        self.assertEqual(rc,2);self.assertEqual(err.getvalue(),'arguments\n')


if __name__=='__main__':unittest.main()
