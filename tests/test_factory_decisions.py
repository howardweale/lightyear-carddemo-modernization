import copy
import json
import unittest
from pathlib import Path
from hashlib import sha256
from lightyear_mainframe.legacy_twin import ROOT
from lightyear_mainframe.systematic_mutation import candidates,generation_inventory,_display_lengths,_invalid_literal_references
from lightyear_factory.scenario_policy import PROPOSAL,IO_ACCEPTANCES,assess
from tools.build_factory_decision_review import build,select,render


class FactoryDecisionsTests(unittest.TestCase):
    def evidence(self):
        return dict(instrumented=True,legacy_mutants_killed='50/50',
            coverage_by_class={'business-logic':{'fraction':'4/4'}},
            systematic_mutation=dict(counts={'killed-divergent':45,'killed-failure':5,'survived':0,'not-compiled':2,'equivalent (argued, listed)':0},
                eligible_count=50,excluded_equivalents=0,equivalent_dispositions=[],unresolved_survivors=[],not_compiled=['compile-a','compile-b']),
            distinct_values_per_output_field={'amount':2},uncovered=[])

    def test_compiler_refusals_excluded_not_blockers_but_inventory_bound(self):
        a=self.evidence();self.assertEqual([],assess(a,PROPOSAL,['amount']))
        for field,value in [('eligible_count',52),('not_compiled',['compile-a']),('not_compiled',['compile-a','compile-a'])]:
            bad=copy.deepcopy(a);bad['systematic_mutation'][field]=value
            self.assertIn('malformed-scenario-evidence',assess(bad,PROPOSAL,['amount']))
        bad=copy.deepcopy(a);bad['legacy_mutants_killed']='50/52'
        self.assertIn('malformed-scenario-evidence',assess(bad,PROPOSAL,['amount']))
        self.assertEqual('proposed-not-approved',PROPOSAL['status'])

    def test_eof_acceptance_is_exact_source_and_outcome_bound(self):
        for acceptance in IO_ACCEPTANCES:
            a=self.evidence();a.update(program=acceptance['program'],source_sha256=acceptance['source_sha256'],
                uncovered=[dict(id=acceptance['id'],outcome='false',classification='io-handling')])
            self.assertEqual([],assess(a,PROPOSAL,['amount']))
            for key,value in [('source_sha256','0'*64),('program','other')]:
                self.assertIn('unaccepted-outcome-gap',assess({**a,key:value},PROPOSAL,['amount']))
            bad=copy.deepcopy(a);bad['uncovered'][0]['outcome']='true'
            self.assertIn('unaccepted-outcome-gap',assess(bad,PROPOSAL,['amount']))
            bad=copy.deepcopy(a);bad['uncovered'][0]['classification']='business-logic'
            self.assertIn('unaccepted-outcome-gap',assess(bad,PROPOSAL,['amount']))

    def test_avoids_exactly_eleven_known_invalid_sites_without_renumbering(self):
        for job,program,count in [('intcalc','CBACT04C',5),('posttran','CBTRN02C',6)]:
            text=(ROOT/f'spec/mainframe/public-source/{program}.cbl').read_text(encoding='utf-8')
            historical=json.loads((ROOT/f'docs/factory/systematic-{job}-review311.json').read_text(encoding='utf-8'))['mutants']
            refused={r['id'] for r in historical if r['status']=='not-compiled'}
            generated=generation_inventory(text,program)
            self.assertEqual(count,generated['avoided_count'])
            self.assertEqual(refused,{r['mutant']['id'] for r in generated['avoided']})
            before={r['id']:r for r in candidates(text,program)}
            self.assertEqual(len(historical),generated['generated_site_count'])
            for row in generated['candidates']:self.assertEqual(before[row['id']],row)
            self.assertEqual(set(before)-refused,{r['id'] for r in generated['candidates']})

    def test_conservative_storage_and_reference_checks(self):
        text='       01 GROUP-A.\n           05 A PIC 9.\n           05 B PIC 999.\n       01 UNKNOWN PIC 9(4) BINARY.\n       PROCEDURE DIVISION.\n           MOVE X TO GROUP-A(3:2).\n'
        self.assertEqual(4,_display_lengths(text)['GROUP-A'])
        self.assertNotIn('UNKNOWN',_display_lengths(text))
        self.assertFalse(_invalid_literal_references(text,_display_lengths(text)))
        self.assertTrue(_invalid_literal_references(text.replace('(3:2)','(4:2)'),_display_lengths(text)))
        self.assertTrue(_invalid_literal_references('           MOVE X TO UNKNOWN(0:2)',{}))
        self.assertFalse(_invalid_literal_references('           MOVE X TO UNKNOWN(4:2)',{}))
        self.assertFalse(_invalid_literal_references('           MOVE X TO GROUP-A(I:L)',{'GROUP-A':4}))
        self.assertFalse(_invalid_literal_references("           DISPLAY 'GROUP-A(0:0)'",{'GROUP-A':4}))

    def test_sample_reproducible_complete_pool_pending_and_raw_records_preserved(self):
        packet,report,register=build(ROOT)
        self.assertEqual(packet,json.loads((ROOT/'docs/factory/equivalence-review-sample-2026-10-11.json').read_text(encoding='utf-8')))
        self.assertEqual(render(packet),(ROOT/'docs/factory/equivalence-review-sample-2026-10-11.md').read_text(encoding='utf-8'))
        self.assertEqual(report,json.loads((ROOT/'docs/factory/howard-decisions-2026-10-11.json').read_text(encoding='utf-8')))
        self.assertEqual(register,json.loads((ROOT/'docs/factory/keep-or-fix-register.json').read_text(encoding='utf-8')))
        self.assertFalse(packet['threshold_approved']);self.assertFalse(report['release_approved'])
        for job,total in [('INTCALC',113),('POSTTRAN',114)]:
            group=packet['programs'][job];self.assertEqual(total,group['population_count'])
            self.assertEqual(10,len(group['sample']));self.assertEqual(10,len({r['id'] for r in group['sample']}))
            self.assertTrue(all(r['independent_review']['status']=='pending' and r['argument']['argument'] for r in group['sample']))
            pool=[dict(id=i) for i in group['population_ids']]
            expected=[r['id'] for r in select(pool,group['program'])]
            self.assertEqual(expected,[r['id'] for r in group['sample']])
            self.assertEqual(expected,[r['id'] for r in select(list(reversed(pool)),group['program'])])
            self.assertNotEqual(expected,[r['id'] for r in select(pool,group['program'],seed='another-seed')])
        for name,expected in packet['input_lf_sha256'].items():
            self.assertEqual(expected,sha256((ROOT/'docs/factory'/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest())
        self.assertEqual('308/308',report['programs']['INTCALC']['conditional_eligible_kill_fraction'])
        self.assertEqual('369/369',report['programs']['POSTTRAN']['conditional_eligible_kill_fraction'])
        self.assertTrue(all(r['disposition']=='keep-by-default' and not r['fix_authorized'] for r in register['defects']))
        self.assertEqual('Howard',register['decision_by'])
        self.assertEqual('2026-10-11',register['decision_date'])
        with self.assertRaisesRegex(ValueError,'duplicate-mutant'):select([{'id':'x'}]*10,'P')
