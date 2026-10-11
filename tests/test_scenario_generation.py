import unittest
from decimal import Decimal
from lightyear_mainframe.records import compile_copybook
from lightyear_mainframe.scenario_generation import boundaries,manifest,case,solve,mutate,MUTANTS
from lightyear_mainframe.legacy_twin import ROOT,FILES


class GeneratorTests(unittest.TestCase):
    def test_pic_signed_scale_packed_and_alphanumeric(self):
        layout=compile_copybook('       01 ROW.\n           05 AMT PIC S9(3)V99 COMP-3.\n           05 TXT PIC X(3).\n')
        self.assertEqual({'-999.99','999.99','0','0.01','-0.01'},set(x['value'] for x in boundaries(layout.fields[0])))
        self.assertEqual('000000',boundaries(layout.fields[1])[1]['value_hex'])

    def test_deterministic_public_only_complete_images(self):
        self.assertEqual(manifest(),manifest())
        for spec in manifest():
            job,meta,images,provenance=case(spec['id'])
            self.assertEqual(set(FILES[job]),set(images))
            for dd,raw in images.items():self.assertEqual(0,len(raw)%(FILES[job][dd][0]+1))
            self.assertEqual(spec['id'],provenance['id'])
        with self.assertRaisesRegex(ValueError,'unknown-generated'):case('../../customer')

    def test_finite_solver_does_not_claim_unreachable(self):
        self.assertEqual({'x':1},solve({'x':[0,1]},lambda r:r['x']>0)['witness'])
        self.assertEqual('not-solved',solve({'x':[0,1]},lambda r:r['x']>2)['status'])

    def test_mutants_modify_exact_pinned_legacy_not_python(self):
        for name,(job,old,new) in MUTANTS.items():
            program='CBACT04C' if job=='INTCALC' else 'CBTRN02C'
            text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text()
            self.assertNotEqual(text,mutate(text,job,name))
            with self.assertRaisesRegex(ValueError,'mutant-source-anchor'):mutate('',job,name)
