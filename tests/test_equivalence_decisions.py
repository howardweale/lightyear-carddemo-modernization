import copy
import json
import unittest
from decimal import Decimal
from lightyear_mainframe.equivalence_evidence import ROOT, SOURCES, appl_result_census, class_covered, register_dependencies,validate_dependencies
from lightyear_mainframe.systematic_mutation import generate
from lightyear_mainframe.scenario_generation import case,manifest
from lightyear_mainframe.posttran_invariants import chronological_context,review_sheet,records
from lightyear_mainframe.legacy_twin import public_inputs
from tools.check_equivalence_followup import population,normalize_c

class EquivalenceDecisionTests(unittest.TestCase):
 def test_pinned_census_and_new_consumers_refused(self):
  for program in SOURCES:
   text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text()
   census=appl_result_census(text,program);self.assertTrue(census['passed']);self.assertFalse(census['raw_consumers'])
   for line in ('           DISPLAY APPL-RESULT.','           MOVE APPL-RESULT TO RETURN-CODE.','           CALL "X" USING APPL-RESULT.'):
    with self.assertRaisesRegex(ValueError,'new-consumer'):appl_result_census(text+'\n'+line,program)
   with self.assertRaisesRegex(ValueError,'source-changed'):appl_result_census(text+'\n',program)
 def test_population_and_class_proof_retain_individual_flow_argument(self):
  total=0
  for job,program in [('INTCALC','CBACT04C'),('POSTTRAN','CBTRN02C')]:
   old=population(job);total+=len(old);text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text();census=appl_result_census(text,program)
   current={r['id']:r for r in generate(text,program)}
   self.assertEqual(421 if job=='INTCALC' else 483,len(current))
   covered=[k for k,r in old.items() if class_covered(current[k],r['disposition'],census)]
   self.assertGreater(len(covered),70)
  self.assertEqual(227,total)
 def test_register_fix_invalidates_known_argument(self):
  register=json.loads((ROOT/'docs/factory/keep-or-fix-register.json').read_text())
  a=population('POSTTRAN')['CBTRN02C-delete-MOVE-557-314']['disposition']
  a={**a,'depends_on_register':register_dependencies(a,register)}
  self.assertEqual(['REWRITE-109'],[r['id'] for r in a['depends_on_register']]);self.assertTrue(validate_dependencies(a,register))
  changed=copy.deepcopy(register);row=next(r for r in changed['defects'] if r['id']=='REWRITE-109');row['disposition']='fix';row['fix_authorized']=True
  with self.assertRaisesRegex(ValueError,'decision-changed'):validate_dependencies(a,changed)
 def test_C_comparison_does_not_erase_literal_or_code_differences(self):
  self.assertEqual(normalize_c('/* one */\n#line 1 "x"\nint x = 1;'),normalize_c('/* two */\n#line 20 "y"\nint x = 1;'))
  self.assertNotEqual(normalize_c('int x = 1;'),normalize_c('int x = 2;'))
  self.assertIn('"/*literal*/"',normalize_c('char *s="/*literal*/";'))
 def test_target_case_bounds_and_curated_identity(self):
  for job in ('INTCALC','POSTTRAN'):
   for profile in ('numeric','xref-suffix','timestamp','record-count','status-path','storage-display'):
    for index in (0,199):
     name=f'b1-target:{job}:{profile}:{index:03d}';self.assertEqual(case(name),case(name))
     self.assertEqual('curated-finite-witness',case(name)[3]['generator_class'])
   with self.assertRaisesRegex(ValueError,'bound'):case(f'b1-target:{job}:numeric:200')
  self.assertTrue(all(r['generator_class']=='curated-finite-witness' for r in manifest()))
 def test_threshold_does_not_accept_unreviewed_or_host_only_zos_arguments(self):
  from lightyear_mainframe.equivalence_evidence import mutation_threshold_report
  register={'defects':[]};identifier='CBTRN02C-delete-MOVE-718-447'
  fresh=[dict(id=identifier,status='equivalent (argued, listed)')]
  follow=[dict(id=identifier,argument={'argument':'host only','depends_on_register':[]},mutant={'source_sha256':'a'},TCE={'identical':True},class_covered=False)]
  twin=mutation_threshold_report(fresh,follow,[], 'twin',register)
  zos=mutation_threshold_report(fresh,follow,[], 'zos-facing',register)
  self.assertEqual(1,len(twin['excluded_equivalents']));self.assertEqual(1,len(zos['unresolved_survivors']))
  self.assertFalse(twin['whole_threshold_effective']);self.assertFalse(twin['release_authorized'])
 def test_kept_sign_discriminator(self):
  _,_,images,_=case('posttran-cycle-debit-sign');rows,_,_=chronological_context(images);r=rows[0];s=r['account_state_before']
  self.assertEqual(102,r['reason']);self.assertEqual(Decimal('1101'),Decimal(s['WS-TEMP-BAL']))
  self.assertLess(Decimal(s['cycle_credit'])+Decimal(s['cycle_debit'])+Decimal(r['input']['DALYTRAN-AMT']),Decimal(s['credit_limit']))
 def test_duplicate_stops_after_partial_update_without_second_row(self):
  _,_,single,_=case('posttran-positive');_,_,duplicate,_=case('posttran-duplicate-id')
  one,a1,c1=chronological_context(single);two,a2,c2=chronological_context(duplicate)
  self.assertEqual(['posted','duplicate-write-abend-after-balances'],[r['outcome'] for r in two])
  aid=two[0]['account_state_before']['account_id'];amount=Decimal(two[1]['input']['DALYTRAN-AMT'])
  self.assertEqual(Decimal(a1[aid]['ACCT-CURR-BAL'])+amount,Decimal(a2[aid]['ACCT-CURR-BAL']))
  self.assertEqual(sum(c1.values())+amount,sum(c2.values()))
 def test_public_batch_review_state_is_chronological(self):
  _,_,before,_=public_inputs('posttran-public');rows,_,_=chronological_context(before)
  self.assertEqual(300,len(rows));self.assertEqual(262,sum(r['outcome']=='posted' for r in rows));self.assertEqual(38,sum(r['outcome']=='rejected' for r in rows))
  self.assertTrue(all('WS-TEMP-BAL' in r['account_state_before'] for r in rows if r['account_state_before']))

if __name__=='__main__':unittest.main()
