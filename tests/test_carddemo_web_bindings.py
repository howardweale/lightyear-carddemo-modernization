from pathlib import Path
import unittest
from lightyear_data.carddemo.web_bindings import build, program, menu, fraud_schema

ROOT=Path(__file__).resolve().parents[1]/'spec/modernization/carddemo-screens'


class WebBindingsTests(unittest.TestCase):
    def test_six_transactions_and_linked_fraud_are_source_bound(self):
        result=build(ROOT)
        self.assertEqual({'CC00','CM00','CAVW','CAUP','CPVS','CPVD'}, {s['transaction'] for s in result['screens']})
        self.assertEqual(6,len(result['screens']))
        self.assertEqual(7,len(result['programs']))
        self.assertEqual(26,len(result['fraud']['fields']))
        self.assertEqual(['card_num','auth_ts'],result['fraud']['primary_key'])
        linked=[c for c in result['programs']['COPAUS1C']['calls'] if c['operation']=='LINK']
        self.assertEqual('COPAUS2C',linked[0]['operands']['PROGRAM'][0]['literal'])
        self.assertTrue(any(c['program']=='COPAUS2C' and c['kind']=='SQL' and c['operation']=='INSERT' for c in result['data_uses']))
        self.assertFalse(result['screen_equivalence_verified'])

    def test_all_menu_options_preserved_outside_options_listed(self):
        result=build(ROOT);options=result['menu']
        self.assertEqual(11,len(options))
        self.assertEqual([1,2,11],[o['number'] for o in options if o['in_slice']])
        self.assertEqual([3,4,5,6,7,8,9,10],[q['number'] for q in result['quirks']])
        self.assertTrue(all(o['role']=='U' for o in options))
        self.assertEqual('/not-in-this-slice',result['outside_endpoint'])

    def test_changed_transaction_and_menu_role_change_generated_values(self):
        p=ROOT/'upstream/app/cbl/COSGN00C.cbl'
        result=program(p.read_bytes().replace(b"VALUE 'CC00'",b"VALUE 'ZZ01'"),'changed.cbl')
        self.assertEqual('ZZ01',result['transaction'])
        p=ROOT/'upstream/app/cpy/COMEN02Y.cpy'
        result=menu(p.read_bytes().replace(b"VALUE 'U'",b"VALUE 'A'",1),'changed.cpy',{'COACTVWC'})
        self.assertEqual('A',result[0]['role'])
        self.assertGreater(result[0]['line'],1)

    def test_unrecognized_sql_type_is_not_silently_mapped(self):
        p=ROOT/'upstream/app/app-authorization-ims-db2-mq/ddl/AUTHFRDS.ddl'
        with self.assertRaisesRegex(ValueError,'unsupported fraud column'):
            fraud_schema(p.read_bytes().replace(b'SMALLINT',b'XML'),'changed.ddl')

    def test_pf_actions_are_extracted_with_physical_source_locations(self):
        result=build(ROOT)
        self.assertTrue({'PF3','PF5','PF8'} <= {a['aid'] for a in result['programs']['COPAUS1C']['aids']})
        for p in result['programs'].values():
            raw=(ROOT/'upstream'/p['source']).read_text(encoding='utf-8').splitlines()
            for aid in p['aids']:self.assertIn(aid['symbol'],raw[aid['line']-1])
