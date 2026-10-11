import unittest,json
from lightyear_mainframe.legacy_twin import ROOT
from lightyear_mainframe.scenario_coverage import instrument,observe,inventory
from lightyear_mainframe.systematic_mutation import generate,apply,outcome,OPERATORS
from lightyear_mainframe.io_faults import declarations,derive

class FactoryReviewTests(unittest.TestCase):
 def test_explicit_source_bound_classification_and_split(self):
  prior=json.loads((ROOT/'docs/factory/generated-runtime-coverage.json').read_text())
  for program,job in [('CBACT04C','INTCALC'),('CBTRN02C','POSTTRAN')]:
   text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text();_,inv=instrument(text,program)
   self.assertTrue(all(p['data_flow'] and len(p['outcome_classification'])==2 for p in inv['points']))
   old=prior['programs'][job]['public_plus_generated']
   trace='\n'.join(f"LYC|D|{p['line']}|{p['outcome']}" for p in old['observed_outcomes'])
   row=observe(inv,trace);self.assertEqual(old['decision_outcomes'],row['decision_outcomes'])
   self.assertEqual(sum(x['covered'] for x in row['coverage_by_class'].values()),len(old['observed_outcomes']))
   self.assertEqual(row['coverage_by_class']['business-logic']['covered'],row['coverage_by_class']['business-logic']['total'])
   with self.assertRaisesRegex(ValueError,'classification-source-changed'):inventory(text+'\n',program)
 def test_systematic_operators_immutable_sites_and_taxonomy(self):
  for program in ('CBACT04C','CBTRN02C'):
   text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text();rows=generate(text,program)
   self.assertGreater(len(rows),50);self.assertEqual(len(rows),len({r['id'] for r in rows}))
   self.assertTrue({'constant','relational','rounded','negate-condition','skip-PERFORM','receiving-size'}<={r['operator'] for r in rows})
   for row in rows:
    operand=(ROOT/'spec/mainframe/copybooks'/row['source_path']).read_text() if row.get('source_path') else text
    self.assertNotEqual(operand,apply(operand,row))
   self.assertTrue(any(r.get('source_path') for r in rows))
  base=dict(status='executed',returncode=0,outputs={'a':'b'})
  self.assertEqual('killed-failure',outcome(base,{**base,'returncode':12}))
  self.assertEqual('killed-divergent',outcome(base,{**base,'outputs':{}}))
  self.assertEqual('survived',outcome(base,base))
 def test_faults_declared_and_no_source_mutation(self):
  for program in ('CBACT04C','CBTRN02C'):
   text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text();rows=declarations(text,program)
   self.assertTrue({'OPEN','READ','WRITE','REWRITE','CLOSE'}<={r['operation'] for r in rows})
   for row in rows:
    changed,inv,declaration=derive(text,program,row['id']);self.assertIn('LYF|'+row['id'],changed)
    self.assertEqual(row,declaration)
   with self.assertRaisesRegex(ValueError,'undeclared'):derive(text,program,'unbound')

 def test_equivalence_is_individually_source_bound_not_blanket_survivor_waiver(self):
  from lightyear_mainframe.mutant_equivalence import argument
  for p,n in [('CBACT04C',30),('CBTRN02C',42)]:
   text=(ROOT/f'spec/mainframe/public-source/{p}.cbl').read_text();rows=generate(text,p)
   proofs=[(r,argument(text,p,r)) for r in rows if argument(text,p,r)]
   self.assertEqual(n,len(proofs))
   for row,proof in proofs:
    self.assertEqual(row['id'],proof['mutant_id']);self.assertTrue(proof['supporting_source_lines'])
   with self.assertRaisesRegex(ValueError,'source-changed'):argument(text+'\n',p,proofs[0][0])
