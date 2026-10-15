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
