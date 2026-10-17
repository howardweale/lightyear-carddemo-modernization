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

    def test_change_and_conflict_comparisons_keep_their_distinct_source_semantics(self):
        from lightyear_data.carddemo.screen_rules import expression, comparisons
        result=build(ROOT)['account_update_comparisons']
        self.assertGreater(len(result['no_change']),25)
        self.assertGreater(len(result['concurrency']),25)
        def leaf(e):return e['name'] if e['operation']=='field' else leaf(e['operand'])
        before=next(p for p in result['no_change'] if leaf(p['left'])=='ACUP-NEW-CUST-FIRST-NAME')
        conflict=next(p for p in result['concurrency'] if leaf(p['left'])=='CUST-FIRST-NAME')
        self.assertEqual('TRIM',before['left']['operand']['operation'])
        self.assertEqual('field',conflict['left']['operand']['operation'])
        with self.assertRaisesRegex(ValueError,'unsupported change-detection'):
            expression('FUNCTION INVENTED(ACUP-OLD-ACCT-ID)')
        source=(ROOT/'upstream/app/cbl/COACTUPC.cbl').read_bytes()
        changed=comparisons(source.replace(b'FUNCTION LOWER-CASE',b'FUNCTION UPPER-CASE'),'changed.cbl','9700-CHECK-CHANGE-IN-REC')
        group=next(p for p in changed if leaf(p['left'])=='ACCT-GROUP-ID')
        self.assertEqual('UPPER-CASE',group['left']['operation'])

    def test_program_commareas_follow_transmitted_and_private_layouts(self):
        result=build(ROOT);layouts=result['program_commareas']
        self.assertEqual(2000,layouts['COACTVWC']['record_length'])
        self.assertEqual(2000,layouts['COACTUPC']['record_length'])
        self.assertEqual(layouts['COPAUS0C']['record_length']+100,layouts['COPAUS1C']['record_length'])
        for program,layout in layouts.items():
            for field in layout['fields']:
                source=(ROOT/'upstream'/field['source']).read_text().splitlines()
                leaf=field['path'].split('.')[-1].split('[')[0]
                self.assertIn(leaf,source[field['line']-1])
        fields=layouts['COACTUPC']['fields']
        original=next(f for f in fields if f['path'].endswith('ACUP-OLD-CURR-BAL'))
        overlay=next(f for f in fields if f['path'].endswith('ACUP-OLD-CURR-BAL-N'))
        self.assertEqual(original['offset'],overlay['offset'])

    def test_account_projection_comes_from_move_and_string_source(self):
        result=build(ROOT);projection=result['account_view_projection']
        names={r['target']:r for r in projection}
        self.assertEqual('ACCT-CURR-BAL',names['ACURBAL']['field'])
        self.assertEqual('CUST-DOB-YYYY-MM-DD',names['ACSTDOB']['field'])
        self.assertEqual([0,3,5],[p['offset'] for p in names['ACSTSSN']['pieces'] if 'field' in p])
        from lightyear_data.carddemo.screen_projection import projection as compile_projection
        raw=(ROOT/'upstream/app/cbl/COACTVWC.cbl').read_bytes()
        screen=next(s for s in result['screens'] if s['program']=='COACTVWC')['model']['maps'][0]
        changed=compile_projection(raw.replace(b'MOVE CUST-FIRST-NAME',b'MOVE CUST-MIDDLE-NAME'),'changed.cbl','1200-SETUP-SCREEN-VARS',screen)
        self.assertEqual('CUST-MIDDLE-NAME',next(p['field'] for p in changed if p['target']=='ACSFNAM'))
        with self.assertRaisesRegex(ValueError,'unsupported projection'):
            compile_projection(raw.replace(b'CUST-SSN(1:3)',b'FUNCTION TRIM(CUST-SSN)'),'changed.cbl','1200-SETUP-SCREEN-VARS',screen)

    def test_pf_actions_are_extracted_with_physical_source_locations(self):
        result=build(ROOT)
        self.assertTrue({'PF3','PF5','PF8'} <= {a['aid'] for a in result['programs']['COPAUS1C']['aids']})
        for p in result['programs'].values():
            raw=(ROOT/'upstream'/p['source']).read_text(encoding='utf-8').splitlines()
            for aid in p['aids']:self.assertIn(aid['symbol'],raw[aid['line']-1])
