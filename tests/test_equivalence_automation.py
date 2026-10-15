"""Adversarial proof/accounting tests; executed by the CI workflow only."""
import copy
from fractions import Fraction
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from lightyear_mainframe.equivalence_automation import (bound,verify,sealed,digest,triage,slice_to_outputs,audit_samples,audit_disposition,upper_bound,score)
from lightyear_mainframe.generic_scenario_ir import translate
from lightyear_mainframe.equivalence_compiler import normalize,require_ci
from lightyear_mainframe.equivalence_solver import statement,query,receive,stored_bytes,Unsupported
from lightyear_mainframe.equivalence_classes import signed_member,dead_store

ROOT=Path(__file__).resolve().parents[1]

def fixture(body):
    text='       IDENTIFICATION DIVISION.\n       PROGRAM-ID. TESTING.\n       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       01 A PIC S9(3)V99.\n       01 B PIC S9(3)V99.\n       PROCEDURE DIVISION.\n'+body
    return text,translate(bound('testing.cbl',text),{})

class AutomationTests(unittest.TestCase):
    def test_triage_covers_all_227_plus_evidence_gaps(self):
        data=[triage(ROOT,p,'a'*40) for p in ('INTCALC','POSTTRAN')]
        self.assertEqual(227,sum(r['argued'] for d in data for r in d['rows']))
        self.assertEqual(47,sum(r['individual_review'] for d in data for r in d['rows']))
        self.assertTrue(all(r['status']=='unresolved' for d in data for r in d['rows']))
        self.assertEqual(data,[triage(ROOT,p,'a'*40) for p in ('INTCALC','POSTTRAN')])
    def test_comments_preserve_token_boundaries_and_literals(self):
        out,_=normalize({'x.c':'int/**/answer(void){return 1;} char *s="/*not a comment*/"; // gone\n'})
        self.assertIn('int answer',out['x.c']);self.assertIn('/*not a comment*/',out['x.c'])
    def test_generated_names_bijective_and_strings_unchanged(self):
        out,m=normalize({'x.c':'static int b_17=1; int f(void){return b_17;} char *s="b_17";'})
        self.assertEqual({'b_17':'lyeq_private_0'},m);self.assertIn('"b_17"',out['x.c'])
        out,m=normalize({'x.c':'int b_17=1; int f(void){return b_17;}'})
        self.assertEqual({},m)
    def test_macro_and_location_metadata_cannot_be_normalized(self):
        for content in ('int x=__LINE__;','char *x=__FILE__;','int x=__func__;'):
            with self.assertRaises(ValueError):normalize({'x.c':content})
    def test_unknown_slice_is_never_false_unobservable(self):
        _,ir=fixture("           CALL 'EXTERNAL'.\n")
        self.assertIsNone(slice_to_outputs(ir,{'A'},{'B'})['reaches_output'])
    def test_unsigned_class_never_resolves(self):
        cp=sealed(dict(matcher_sha256='m',matches={'id':{}},class_id='class'))
        request={'class_proof':cp,'contract':{'details':{'class_proof_sha256':cp['content_sha256']}}}
        with self.assertRaisesRegex(ValueError,'signed-class'):signed_member(None,request,{},'id',{},'m')
    def test_dead_store_positive_and_near_miss_read(self):
        from lightyear_mainframe.systematic_mutation import _source_sites
        for second,expected in [('MOVE 2 TO A',True),('MOVE A TO B',False),('ADD 1 TO A',False),('CALL \'X\'',False)]:
            text,ir=fixture('           MOVE 1 TO A\n           '+second+'\n           STOP RUN.\n')
            m=next(m for m in _source_sites(text,'TESTING') if m['operator']=='delete-MOVE')
            self.assertEqual(expected,dead_store(ir,text,m) is not None)
    def test_rounding_exact_cent_expression_unsat_and_near_miss_sat(self):
        _,ir=fixture('           CONTINUE.\n')
        a=statement('           COMPUTE B = A + 1',ir)
        b=statement('           COMPUTE B ROUNDED = A + 1',ir)
        local=dict(original=a,mutant=b,target='B',fields={**a['fields'],**b['fields']})
        self.assertEqual('unsat',str(query(local)[0].check()))
        b['expression']['operands'][1]['value']='0.001';self.assertEqual('sat',str(query(local)[0].check()))
    def test_noop_includes_old_receiving_state(self):
        _,ir=fixture('           CONTINUE.\n');a=statement('           MOVE 0 TO B',ir)
        self.assertEqual('sat',str(query(dict(original=a,mutant=dict(kind='noop'),target='B',fields=a['fields']))[0].check()))
    def test_size_error_and_partial_writes_refused(self):
        _,ir=fixture('           CONTINUE.\n')
        for text in ('COMPUTE B = A ON SIZE ERROR MOVE 0 TO B','MOVE 1 TO B(1:1)','COMPUTE B = A / 3'):
            with self.assertRaises(ValueError):statement('           '+text,ir)
    def test_rounding_overflow_and_negative(self):
        _,ir=fixture('           CONTINUE.\n');f=ir['fields'][1]
        self.assertEqual((-101,False),receive(Fraction('-1.005'),f,True))
        self.assertEqual((0,True),receive(Fraction('1000'),f,False))
        self.assertEqual(b'0010J',stored_bytes(-101,f))
    def test_audit_seed_pending_stats_and_error_disable(self):
        rows=[dict(id=str(i),program='P',route='S1',status='equivalent') for i in range(50)]
        a=audit_samples(rows,'hash');self.assertEqual(a,audit_samples(list(reversed(rows)),'hash'))
        self.assertEqual(30,len(a[0]['items']));self.assertIsNone(a[0]['upper_95'])
        results,disabled=audit_disposition(a,{a[0]['items'][0]:'incorrect'})
        self.assertEqual({('P','S1')},disabled);self.assertEqual(1,results[0]['confirmed_errors'])
        self.assertAlmostEqual(1-.05**(1/30),upper_bound(0,30))
    def test_score_never_excludes_unresolved_or_unobservable(self):
        rows=[dict(id='e',status='equivalent'),dict(id='u',status='unobservable'),dict(id='p',status='proposed')]
        self.assertEqual(dict(numerator=1,denominator=3),score(4,['k'],[],rows)['adjusted'])
        with self.assertRaises(ValueError):score(4,['e'],[],rows)
        with self.assertRaises(ValueError):score(4,[],[],rows+rows)
    def test_no_native_execution_and_seal_tamper(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError):require_ci()
        value=sealed({'x':1});value['x']=2
        with self.assertRaises(ValueError):verify(value)

class ReviewOverlayTests(unittest.TestCase):
    def test_confirmed_signed_error_retracts_entire_route_without_editing_parent(self):
        from lightyear_mainframe.equivalence_reviews import apply_reviews
        rows=[dict(id=str(i),program='P',route='S1',status='equivalent') for i in range(2)]
        ledger=sealed(dict(head='a'*40,program='P',rows=rows))
        packet=sealed(dict(head='a'*40,samples=audit_samples(rows,'seed'),resolutions=rows))
        contract=dict(details=dict(packet_sha256=digest(packet)))
        request=dict(contract=contract,packet=packet)
        class Authority:
            signed_only=True
            def verify(self,*args):return dict(validation=dict(items={'0':dict(outcome='reject'),'1':dict(outcome='accept')}))
        result=apply_reviews(ledger,[],request,{digest(contract):dict(decision_sha256='signed')},Authority(),'matcher')
        self.assertTrue(all(r['status']=='unresolved' for r in result['rows']))
        self.assertTrue(all(r['status']=='equivalent' for r in ledger['rows']))
        self.assertEqual([['P','S1']],result['disabled_routes'])
    def test_no_signature_context_means_no_review_overlay(self):
        from lightyear_mainframe.equivalence_reviews import apply_reviews
        with self.assertRaisesRegex(ValueError,'authority'):
            apply_reviews(sealed(dict(rows=[])),[],{}, {}, None,'matcher')

class OracleGapTests(unittest.TestCase):
    def test_unobserved_counter_is_gap_and_group_read_refuses(self):
        from lightyear_mainframe.equivalence_classes import unobservable_counter
        from lightyear_mainframe.systematic_mutation import _source_sites
        for extra,gap in [('',True),('           DISPLAY A\n',False)]:
            text,ir=fixture('           ADD 1 TO A\n'+extra+'           STOP RUN.\n')
            mutant=next(m for m in _source_sites(text,'TESTING') if m['operator']=='delete-ADD')
            finding=unobservable_counter(ir,text,mutant)
            self.assertEqual(gap,finding is not None)
            if finding:self.assertFalse(finding['resolved'])

class ContractSchemaTests(unittest.TestCase):
    def test_class_and_audit_packets_satisfy_existing_factory_schema(self):
        from lightyear_mainframe.equivalence_classes import class_contract
        from tools.run_equivalence_automation import audit_request
        c=class_contract('INTCALC','a'*40,'adjacent-dead-literal-store/1',{'mutant':dict(mutant_sha256='b'*64)},'docs/factory/packet.json','b'*64,'c'*64)
        self.assertEqual('unsigned',c['status'])
        rows=[dict(id='mutant',program='INTCALC',route='S1',status='equivalent')]
        audit=audit_request('INTCALC','a'*40,{},audit_samples(rows,'run'),rows)
        self.assertEqual('unsigned',audit['status'])

class ToolchainProfileTests(unittest.TestCase):
    def test_binary_profile_comes_from_included_config_and_fails_closed(self):
        import tempfile
        from lightyear_mainframe.equivalence_compiler import binary_profile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'ibm.conf').write_text('include "base.conf"\nbinary-truncate: yes\n')
            (root/'base.conf').write_text('binary-truncate: no\nbinary-byteorder: big-endian\nbinary-size: 2-4-8\n')
            self.assertTrue(binary_profile(root)['binary_truncate'])
            (root/'ibm.conf').write_text('binary-size: unknown\n')
            with self.assertRaises(ValueError):binary_profile(root)

class ConditionEncoderTests(unittest.TestCase):
    def test_pic_domain_proves_condition_and_refutes_near_miss(self):
        _,ir=fixture('           CONTINUE.\n')
        a=statement('           IF A < 1000',ir);b=statement('           IF A <= 1000',ir)
        local=dict(original=a,mutant=b,fields={**a['fields'],**b['fields']},target='LY-RESULT')
        self.assertEqual('unsat',str(query(local)[0].check()))
        c=statement('           IF A > 0',ir);local['mutant']=c
        self.assertEqual('sat',str(query(local)[0].check()))

class CounterexampleScenarioTests(unittest.TestCase):
    def test_solver_model_only_maps_known_public_fields(self):
        from lightyear_mainframe.equivalence_scenarios import identifier
        _,ir=fixture('           CONTINUE.\n');a=statement('           MOVE A TO B',ir)
        with self.assertRaisesRegex(ValueError,'no-public-dataset-binding'):
            identifier('INTCALC',dict(original=a,mutant=a,fields=a['fields']),{'A':'123','B':'0'})
    def test_counterexample_uses_extension_without_changing_approved_generator(self):
        from lightyear_mainframe.scenario_generation import case as generated
        from lightyear_mainframe.equivalence_scenarios import case,identifier
        from lightyear_mainframe.loader_domain import source_binding
        name=identifier('INTCALC',dict(original={},mutant={},fields={}),{})
        self.assertEqual(case(name),generated(name))
        self.assertTrue(source_binding())
    def test_nonfinite_and_unmapped_inputs_refused(self):
        import base64
        from lightyear_mainframe.equivalence_scenarios import case
        for values in ({'UNMAPPED':'1'}, {'ACCT-CURR-BAL':'NaN'}):
            name='b1-target:POSTTRAN:equivalence-cex:'+base64.urlsafe_b64encode(json.dumps(values).encode()).decode()
            with self.assertRaises(ValueError):case(name)

class ExecutionKillTests(unittest.TestCase):
    def test_sat_and_execution_refusal_are_not_kills(self):
        from lightyear_mainframe.systematic_mutation import outcome
        a=dict(status='executed',returncode=0,outputs={'out':'a'},stdout_sha256='s',stderr_sha256='e')
        self.assertFalse(outcome(a,dict(status='execution-refusal')).startswith('killed-'))
        self.assertFalse(outcome(dict(status='execution-refusal'),a).startswith('killed-'))
        self.assertEqual('survived',outcome(a,dict(a)))
        self.assertEqual('killed-divergent',outcome(a,dict(a,outputs={'out':'b'})))

class DominatingGuardTests(unittest.TestCase):
    def test_mutated_or_unknown_guard_state_is_not_assumed(self):
        from lightyear_mainframe.equivalence_solver import stable_guards
        for between,expected in [('',1),('             MOVE -2 TO A\n',0),("             CALL 'X'\n",0)]:
            text,ir=fixture('           IF A > 1\n'+between+'             IF A < 0\n               MOVE 1 TO B\n             END-IF\n           END-IF.\n')
            inner=next(s for s in ir['statements'] if s['kind']=='condition' and s['guards'])
            self.assertEqual(expected,len(stable_guards(ir,inner['location']['line'],{})))
    def test_safe_dominating_guard_is_in_saved_query(self):
        _,ir=fixture('           IF A > 1\n             IF A < 0\n               MOVE 1 TO B\n             END-IF\n           END-IF.\n')
        from lightyear_mainframe.equivalence_solver import stable_guards
        a=statement('           IF A < 0',ir);b=statement('           IF A < -1',ir)
        fields={**a['fields'],**b['fields']};line=ir['statements'][1]['location']['line']
        local=dict(original=a,mutant=b,target='LY-RESULT',fields=fields)
        self.assertEqual('sat',str(query(local)[0].check()))
        local['dominating_guards']=stable_guards(ir,line,fields)
        self.assertEqual('unsat',str(query(local)[0].check()))

class PrecisionLimitsTests(unittest.TestCase):
    def test_unbounded_intermediate_precision_is_refused(self):
        from lightyear_mainframe.equivalence_solver import supported_precision
        _,ir=fixture('           CONTINUE.\n');a=statement('           COMPUTE B = A * A * A * A * A * A * A * A',ir)
        with self.assertRaisesRegex(ValueError,'precision'):
            supported_precision(dict(original=a,mutant=a,fields=a['fields']),True)

class BinaryDomainTests(unittest.TestCase):
    def test_untruncated_binary_domain_is_storage_width_not_pic_digits(self):
        from lightyear_mainframe.equivalence_solver import input_bounds
        f=dict(usage='BINARY',length=4,signed=True,digits=9)
        self.assertEqual((-2147483648,2147483647),input_bounds(f,False))
        self.assertEqual((-999999999,999999999),input_bounds(f,True))
        self.assertEqual((0,4294967295),input_bounds(dict(f,signed=False),False))

class NormalizationBoundaryTests(unittest.TestCase):
    def test_header_macros_cannot_observe_renamed_identifiers(self):
        _,mapping=normalize({'p.c':'#include "header.h"\nstatic int b_12=1;\n'})
        self.assertEqual({},mapping)
    def test_c_comment_line_splicing_refused(self):
        text='int f(void) {\n// comment '+chr(92)+'\nreturn 2;\nreturn 1;\n}'
        with self.assertRaisesRegex(ValueError,'line-splicing'):normalize({'p.c':text})

class HeaderLocationTests(unittest.TestCase):
    def test_included_location_macros_keep_line_directives_and_comment_line_count(self):
        text='#include "header.h"\n#line 70 "original.c"\n/* first\nsecond */\nint f(void){return LOCATION_MACRO;}\n'
        output,_=normalize({'p.c':text})
        self.assertIn('#line 70 "original.c"',output['p.c'])
        self.assertEqual(text.count('\n'),output['p.c'].count('\n'))

class CompleteRepeatTests(unittest.TestCase):
    def test_repeat_includes_unresolved_classifications(self):
        from tools.compare_equivalence_runs import compare
        original=sealed(dict(head='a'*40,program='P',rows=[dict(id='x',status='unresolved',route=None)]))
        self.assertTrue(compare(original,original)['identical_resolutions'])
        changed=sealed(dict(head='a'*40,program='P',rows=[dict(id='x',status='equivalent',route='S1')]))
        with self.assertRaisesRegex(ValueError,'non-reproducible'):compare(original,changed)

class NegativeZeroTests(unittest.TestCase):
    def test_signed_zero_storage_is_not_silently_collapsed(self):
        _,ir=fixture('           CONTINUE.\n');field=ir['fields'][0]
        self.assertNotEqual(stored_bytes(0,field),stored_bytes(0,field,negative_zero=True))
        packed=dict(field,usage='COMP-3',length=3)
        self.assertEqual(13,stored_bytes(0,packed,negative_zero=True)[-1]&15)
