"""CI-only proof of exact constant exemptions with comparison/mutation retained."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from lightyear_factory.threshold3 import ROOT, ACCEPTANCE, BINDINGS, exemptions
from lightyear_factory.scenario_policy import assess, PROPOSAL


class Threshold3Tests(unittest.TestCase):
    def fixture(self):
        rows=json.loads((ROOT/ACCEPTANCE).read_bytes())['constant_field_acceptances']
        rows=[{k:r[k] for k in BINDINGS} for r in rows if r['program']=='INTCALC']
        threshold=dict(PROPOSAL,schema='scenario-threshold/3',constant_exemptions=rows)
        evidence={r['field']:dict(r,compared=True,mutants=[dict(id='fixture-'+str(r['source_line']),line=r['source_line'],
            source_sha256=r['source_sha256'],status='killed-divergent',valid_comparisons=1,evidence_complete=True,record_sha256='a'*64)]) for r in rows}
        adequacy=dict(program='CBACT04C',instrumented=True,coverage_by_class={'business-logic':{'fraction':'8/8'}},
            legacy_mutants_killed='50/50',systematic_mutation=dict(counts={'killed-divergent':50,'killed-failure':0,'survived':0,'not-compiled':0,'equivalent (argued, listed)':0},eligible_count=50,excluded_equivalents=0,equivalent_dispositions=[],unresolved_survivors=[],not_compiled=[]),
            uncovered=[],constant_field_evidence=evidence,distinct_values_per_output_field={r['field']:1 for r in rows})
        return threshold,adequacy,list(evidence)

    def test_exact_seven_only_change_diversity(self):
        t,a,fields=self.fixture()
        self.assertEqual([],assess(a,t,fields))
        self.assertIn('output-diversity-below-threshold',assess(a,PROPOSAL,fields))
        a['distinct_values_per_output_field']['variable-field']=1
        self.assertIn('output-diversity-below-threshold',assess(a,t,fields+['variable-field']))
        a['coverage_by_class']['business-logic']['fraction']='7/8'
        self.assertIn('business-outcomes-below-threshold',assess(a,t,fields))

    def test_missing_comparison_or_mutation_voids_exemption(self):
        for change in ('comparison','mutation','gap','incomplete','line','extra','missing'):
            t,a,f=self.fixture(); item=a['constant_field_evidence'][f[0]]
            if change=='comparison': item['compared']=False
            if change=='mutation': item['mutants']=[]
            if change=='gap': item['mutants'][0]['status']='evidence-gap'
            if change=='incomplete': item['mutants'][0]['evidence_complete']=False
            if change=='line': t['constant_exemptions'][0]['source_line_sha256']='0'*64
            if change=='extra': t['constant_exemptions'].append(copy.deepcopy(t['constant_exemptions'][0]))
            if change=='missing': t['constant_exemptions'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError): exemptions(a,t,f)

    def test_survived_and_equivalent_only_refuses(self):
        for status in ('survived','equivalent (argued, listed)'):
            t,a,f=self.fixture()
            a['constant_field_evidence'][f[0]]['mutants'][0]['status']=status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError,'constant-mutant-not-caught'):
                exemptions(a,t,f)

    def test_changed_source_line_refuses(self):
        t,a,f=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for path in (ACCEPTANCE,t['constant_exemptions'][0]['source_path']):
                target=root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((ROOT/path).read_bytes())
            path=root/t['constant_exemptions'][0]['source_path']; path.write_bytes(path.read_bytes()+b'\nchanged\n')
            with self.assertRaisesRegex(ValueError,'source-binding'): exemptions(a,t,f,root)
