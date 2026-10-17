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
   self.assertEqual(424 if job=='INTCALC' else 483,len(current))
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
 def test_targeted_fields_include_admitted_clock_and_received_account_suffix(self):
  clocks=set();accounts=set();filler=set()
  for index in range(200):
   _,meta,_,_=case(f'b1-target:INTCALC:timestamp:{index:03d}');clocks.add(meta['candidate_timestamp'])
   self.assertTrue(meta['candidate_timestamp'].endswith('.000000'))
   from lightyear_mainframe.legacy_twin import runtime_clock
   runtime_clock('INTCALC',meta)
   _,_,images,_=case(f'b1-target:POSTTRAN:xref-suffix:{index:03d}')
   xr=records(images,'XREFFILE');ar=records(images,'ACCTFILE');tr=records(images,'DALYTRAN')
   self.assertEqual(1,len(xr));self.assertEqual(1,len(ar));self.assertEqual(tr[0]['DALYTRAN-CARD-NUM'],xr[0]['XREF-CARD-NUM'])
   self.assertEqual(xr[0]['XREF-ACCT-ID'],ar[0]['ACCT-ID']);accounts.add(ar[0]['ACCT-ID']);filler.add(images['XREFFILE'][36])
  self.assertEqual(200,len(clocks));self.assertEqual(200,len(accounts));self.assertEqual(94,len(filler))
 def test_only_explicit_two_scope_amendments_extend_accepted_zos_scope(self):
  from lightyear_mainframe.equivalence_evidence import mutation_threshold_report
  accepted=json.loads((ROOT/'docs/factory/equivalence-decision-binding-2026-10-11.json').read_text())['accepted_mutants']
  amended=[r for r in accepted if r.get('explicit_zos_scope_basis')]
  self.assertEqual({'CBACT04C-receiving-size-133-19','CBTRN02C-constant-718-445'},{r['id'] for r in amended})
  for approval in amended:
   row=dict(id=approval['id'],argument={'argument':'not z/OS','compiler_storage_semantics':{},'depends_on_register':[]},mutant={'source_sha256':approval['source_sha256']},TCE={},class_covered=False)
   from lightyear_mainframe.claim_scope import digest
   scopes=dict(arguments=[dict(id=row['id'],record_sha256=digest(row['argument']),source_sha256=approval['source_sha256'],claim_scope='host-compiler-scoped')],
     acceptances=[dict(id=row['id'],record_sha256=digest(approval),source_sha256=approval['source_sha256'],claim_scope='twin-and-zos')])
   result=mutation_threshold_report([dict(id=row['id'],status='survived')],[row],accepted,'zos-facing',{'defects':[]},scope_decisions=scopes)
   self.assertEqual(1,len(result['excluded_equivalents']))
   wrong={**row,'mutant':{'source_sha256':'0'*64}}
   with self.assertRaisesRegex(ValueError,'claim-scope-host-semantics-unclassified'):
    mutation_threshold_report([dict(id=row['id'],status='survived')],[wrong],accepted,'zos-facing',{'defects':[]},scope_decisions=scopes)
 def test_threshold_does_not_accept_unreviewed_or_host_only_zos_arguments(self):
  from lightyear_mainframe.equivalence_evidence import mutation_threshold_report
  register={'defects':[]};identifier='CBTRN02C-delete-MOVE-718-447'
  fresh=[dict(id=identifier,status='equivalent (argued, listed)')]
  follow=[dict(id=identifier,argument={'argument':'host only','depends_on_register':[]},mutant={'source_sha256':'a'},TCE={'identical':True},class_covered=False)]
  twin=mutation_threshold_report(fresh,follow,[], 'twin',register)
  zos=mutation_threshold_report(fresh,follow,[], 'zos-facing',register)
  self.assertEqual(1,len(twin['excluded_equivalents']));self.assertEqual(1,len(zos['unresolved_survivors']))
  self.assertFalse(twin['whole_threshold_effective']);self.assertFalse(twin['release_authorized'])
 def test_amended_threshold_retains_review_diversity_and_freshness_blockers(self):
  from lightyear_mainframe.equivalence_evidence import amended_threshold_report
  coverage=dict(instrumented=True,program='CBACT04C',source_sha256=SOURCES['CBACT04C'],coverage_by_class={'business-logic':dict(covered=8,total=8),'io-handling':dict(covered=85,total=86)},uncovered=[dict(id='legacy:cobol-decision:CBACT04C:189:671',outcome='false',classification='io-handling')])
  mutation=dict(claim_scope='twin',mutation_conditions_met=True,compiler_refusals=[],targeted_experiments_complete=True)
  r=amended_threshold_report(mutation,coverage,{'A':2},['A'],'a'*40)
  self.assertTrue(r['conditions_met']);self.assertFalse(r['release_authorized']);self.assertFalse(r['measurement_credit'])
  for changed,diversity,head,reason in (({**mutation,'mutation_conditions_met':False},{'A':2},'a'*40,'mutation-or-individual-review-conditions-unmet'),(mutation,{'A':1},'a'*40,'output-fields-below-two-values'),(mutation,{'A':2},'old','fresh-current-head-source-binding-required')):
   r=amended_threshold_report(changed,coverage,diversity,['A'],head);self.assertIn(reason,r['blocking_reasons'])
  listed=amended_threshold_report({**mutation,'compiler_refusals':['listed-mutant']},coverage,{'A':2},['A'],'a'*40)
  self.assertTrue(listed['conditions_met']);self.assertEqual(['listed-mutant'],listed['mutation']['compiler_refusals'])
  bad=copy.deepcopy(coverage);bad['uncovered'][0]['outcome']='true'
  self.assertIn('unaccepted-business-or-IO-outcome',amended_threshold_report(mutation,bad,{'A':2},['A'],'a'*40)['blocking_reasons'])
 def test_targeted_accounting_does_not_count_refused_baseline_as_valid_comparison(self):
  from tools.check_equivalence_followup import targeted_accounting
  rows=[dict(index=i,case=str(i),fault=None,baseline={'status':'executed'},actual={'status':'executed'},status='survived') for i in range(200)]
  self.assertTrue(targeted_accounting(rows)['targeted_evidence_complete'])
  rows[3]['baseline']['status']='execution-refusal';rows[3]['status']='baseline-refusal'
  rows[4]['actual']['status']='execution-refusal';rows[4]['status']='mutant-execution-refusal'
  result=targeted_accounting(rows)
  self.assertEqual(200,result['targeted_cases']);self.assertEqual(198,result['targeted_valid_comparisons'])
  self.assertFalse(result['targeted_evidence_complete']);self.assertEqual([3,4],[r['index'] for r in result['targeted_evidence_gaps']])
 def test_targeted_refusals_never_refute_a_mutant(self):
  from tools.check_equivalence_followup import targeted_outcome
  normal=dict(status='executed',returncode=0,outputs={'OUT':'same'},stdout_sha256='s',stderr_sha256='e')
  refusal=dict(status='execution-refusal',error_type='TimeoutExpired')
  self.assertEqual('mutant-execution-refusal',targeted_outcome(normal,refusal))
  self.assertEqual('baseline-refusal',targeted_outcome(refusal,normal))
  self.assertFalse(targeted_outcome(normal,refusal).startswith('killed-'))
  self.assertEqual('survived',targeted_outcome(normal,normal))
  self.assertEqual('killed-failure',targeted_outcome(normal,{**normal,'returncode':12}))
  self.assertEqual('killed-divergent',targeted_outcome(normal,{**normal,'outputs':{'OUT':'changed'}}))
 def test_accepted_equivalent_with_incomplete_targets_blocks_complete_threshold(self):
  from lightyear_mainframe.equivalence_evidence import mutation_threshold_report,amended_threshold_report
  identifier='accepted-site';approval={'id':identifier,'source_sha256':'source','scope':'stated-argument-scope'}
  fresh=[dict(id='kill-'+str(i),status='killed-divergent',baseline={'status':'executed'},actual={'status':'executed'}) for i in range(50)]
  fresh.append(dict(id=identifier,status='equivalent (argued, listed)'))
  row=dict(id=identifier,mutant={'source_sha256':'source'},argument={'depends_on_register':[]},TCE={},class_covered=False,targeted_cases=200,targeted_valid_comparisons=199,targeted_evidence_complete=False)
  mutation=mutation_threshold_report(fresh,[row],[approval],'twin',{'defects':[]})
  self.assertTrue(mutation['mutation_conditions_met']);self.assertEqual([identifier],mutation['targeted_evidence_gap_ids'])
  coverage=dict(instrumented=True,program='CBACT04C',source_sha256=SOURCES['CBACT04C'],coverage_by_class={'business-logic':{'covered':8,'total':8},'io-handling':{'covered':86,'total':86}},uncovered=[])
  result=amended_threshold_report(mutation,coverage,{'A':2},['A'],'a'*40)
  self.assertFalse(result['conditions_met']);self.assertEqual(['required-targeted-experiment-evidence-incomplete'],result['blocking_reasons'])
  mutation=mutation_threshold_report([dict(id=identifier,status='not-compiled')],[row],[approval],'twin',{'defects':[]})
  self.assertEqual([],mutation['targeted_evidence_gap_ids']);self.assertEqual([identifier],mutation['compiler_refusals'])
 def test_threshold_rejects_a_legacy_kill_with_refused_execution(self):
  from lightyear_mainframe.equivalence_evidence import mutation_threshold_report
  fresh=[dict(id='old-claimed-kill',status='killed-failure',baseline={'status':'executed'},actual={'status':'execution-refusal'})]
  result=mutation_threshold_report(fresh,[],[],'twin',{'defects':[]})
  self.assertEqual(0,result['killed']);self.assertEqual('unverified-kill-execution-evidence',result['unresolved_survivors'][0]['reason'])
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
