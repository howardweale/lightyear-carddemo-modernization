import json
import unittest
from pathlib import Path
from lightyear_mainframe.constant_evidence import build
from lightyear_mainframe.equivalence_evidence import seal
from lightyear_mainframe.systematic_mutation import generate, apply, generation_inventory
from lightyear_factory.threshold3 import ACCEPTANCE

ROOT=Path(__file__).resolve().parents[1]

class ConstantEvidenceTests(unittest.TestCase):
    def test_new_sites_preserve_old_identities_and_change_values(self):
        text=(ROOT/'spec/mainframe/public-source/CBACT04C.cbl').read_text()
        inventory=generate(text,'CBACT04C')
        targeted=[r for r in inventory if r['operator']=='constant-output']
        self.assertEqual({492,493,494},{r['line'] for r in targeted})
        self.assertEqual(424,len(inventory))
        for row in targeted:
            self.assertIn("MOVE 'X' TO "+row['field'],apply(text,row))
        old=json.loads((ROOT/'docs/factory/systematic-intcalc-review311.json').read_bytes())['mutants']
        avoided={r['mutant']['id'] for r in generation_inventory(text,'CBACT04C')['avoided']}
        self.assertEqual({r['id'] for r in old}-avoided,
                         {r['id'] for r in inventory}-{r['id'] for r in targeted})

    def test_record_hash_and_comparison_count_are_measured(self):
        text=(ROOT/'spec/mainframe/public-source/CBACT04C.cbl').read_text()
        inventory=generate(text,'CBACT04C');site=next(r for r in inventory if r['operator']=='constant-output')
        approved=next(r for r in json.loads((ROOT/ACCEPTANCE).read_bytes())['constant_field_acceptances'] if r['source_line']==site['line'] and r['program']=='INTCALC')
        baseline=dict(status='executed',returncode=0,outputs={'TRANSACT':{'sha256':'a'*64}},stdout_sha256='b'*64,stderr_sha256='c'*64)
        actual=dict(baseline,outputs={'TRANSACT':{'sha256':'d'*64}})
        pair=dict(baseline=baseline,actual=actual)
        row=dict(id=site['id'],status='killed-divergent',comparisons=[pair,pair],evidence_gaps=[])
        proof=build(ROOT,'CBACT04C',[row],inventory,[approved['field']])[approved['field']]
        self.assertTrue(proof['compared']);self.assertEqual(2,proof['mutants'][0]['valid_comparisons'])
        self.assertEqual(seal(row),proof['mutants'][0]['record_sha256'])
        row['comparisons'].append(dict(baseline={'status':'executed'},actual={'status':'timeout'}))
        proof=build(ROOT,'CBACT04C',[row],inventory,[])[approved['field']]
        self.assertFalse(proof['compared']);self.assertEqual([],proof['mutants'])
        self.assertEqual(1,len(proof['unqualified_mutants']))
