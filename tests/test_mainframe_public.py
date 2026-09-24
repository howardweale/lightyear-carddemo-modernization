"""Full pinned estate checks. CI supplies CARDDEMO_SOURCE; no test downloads code."""
import json
import os
from pathlib import Path
import unittest

from lightyear_mainframe.inventory import coverage, inventory
from lightyear_mainframe.public_corpus import CARDDEMO_COMMIT, verify_public

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('CARDDEMO_SOURCE'), 'set CARDDEMO_SOURCE to the pinned public checkout')
class PublicCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=Path(os.environ['CARDDEMO_SOURCE'])
        cls.report=inventory(cls.source)

    def test_all_44_programs_and_reviewed_denominator(self):
        r=self.report
        self.assertEqual(CARDDEMO_COMMIT,r['source']['commit'])
        self.assertFalse(r['source']['working_tree_dirty'])
        self.assertEqual((44,1423,3605),(r['summary']['programs'],r['summary']['decisions'],r['summary']['outcomes']))
        self.assertEqual({'missing-copybook':62},r['summary']['issues_by_cause'])
        self.assertEqual({'DFHAID','DFHBMSCA','CMQODV','CMQMDV','CMQV','CMQTML','CMQPMOV','CMQGMOV'}, {i['name'] for i in r['issues']})
        self.assertFalse(r['claims']['compiled_branch_complete'])
        self.assertIsNone(coverage(r)['coverage_percent'])
        self.assertEqual(119,sum(bool(d['inclusion']) for d in r['decisions']))

    def test_published_inventory_reproduces_exactly(self):
        published=json.loads((ROOT/'docs/mainframe/carddemo/inventory.json').read_text())
        self.assertEqual(published,self.report)

    def test_all_decision_origins_are_addressable_and_ids_unique(self):
        r=self.report; ids=[]
        for d in r['decisions']:
            physical=(self.source/d['path']).read_text().splitlines()[d['line']-1].expandtabs(8)
            self.assertTrue(physical[d['column']-1:].strip())
            self.assertIn(d['path'],r['source']['files'])
            ids.extend(o['id'] for o in d['outcomes'])
        self.assertEqual(3605,len(set(ids)))
        interest=next(p for p in r['programs'] if p['path']=='app/cbl/CBACT04C.cbl')
        self.assertEqual((47,94),(interest['decisions'],interest['outcomes']))

    def test_all_501_public_binary_records_decode_without_losing_bytes(self):
        r=verify_public(self.source)
        self.assertEqual(501,r['records'])
        self.assertEqual(5,len(r['datasets']))
        self.assertEqual('local_observed',r['evidence_class'])
        self.assertFalse(r['mainframe_equivalent'])
        published=json.loads((ROOT/'docs/mainframe/public-decoding.json').read_text())
        self.assertEqual(published,r)
