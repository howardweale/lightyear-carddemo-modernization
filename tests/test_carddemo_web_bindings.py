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

    def test_end_if_is_not_the_start_of_another_comparison(self):
        from lightyear_data.carddemo.screen_rules import comparisons
        raw=b'       CHECK-PAIR.\n           IF A = B CONTINUE ELSE SET CHANGED TO TRUE END-IF\n           IF C = D CONTINUE ELSE SET CHANGED TO TRUE END-IF\n           .\n       CHECK-PAIR-EXIT.\n           EXIT.\n'
        rows=comparisons(raw,'pair.cbl','CHECK-PAIR')
        self.assertEqual(['A','C'],[r['left']['name'] for r in rows])
        self.assertEqual(['B','D'],[r['right']['name'] for r in rows])

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

    def test_account_update_transfers_and_validators_are_generated(self):
        from lightyear_data.carddemo.screen_update import build as compile_update
        result=build(ROOT)['account_update']
        self.assertEqual(5,len(result['inputs']['numeric_conversions']))
        self.assertGreater(len(result['inputs']['moves']),35)
        self.assertGreater(len(result['validations']),20)
        first=next(v for v in result['validations'] if v['label']=='First Name')
        self.assertEqual(['ACUP-NEW-CUST-FIRST-NAME'],first['fields'])
        self.assertEqual('1225-EDIT-ALPHA-REQD',first['calls'][0]['paragraph'])
        self.assertEqual(300,result['buffers']['ACCT-UPDATE-RECORD']['record_length'])
        self.assertEqual(500,result['buffers']['CUST-UPDATE-RECORD']['record_length'])
        # The original account rewrite layout omits ACCT-ADDR-ZIP. Preserve that
        # byte-layout discrepancy for the reference proof, never map by names.
        account=result['buffers']['ACCT-UPDATE-RECORD']['fields']
        self.assertFalse(any('ADDR-ZIP' in f['path'] for f in account))
        source=(ROOT/'upstream/app/cbl/COACTUPC.cbl').read_bytes()
        changed=compile_update(source.replace(b'MOVE CUST-FIRST-NAME',b'MOVE CUST-MIDDLE-NAME'),'changed.cbl')
        transfer=next(v for v in changed['fetched'] if v['target']=='ACUP-OLD-CUST-FIRST-NAME')
        self.assertEqual('CUST-MIDDLE-NAME',transfer['expression']['name'])
        for row in result['writes']+result['fetched']:
            line=source.decode().splitlines()[row['line']-1]
            self.assertTrue('MOVE' in line or 'STRING' in line)
        with self.assertRaisesRegex(ValueError,'unaccounted update buffer'):
            compile_update(source.replace(b'MOVE ACCT-ID                  TO ACUP-OLD-ACCT-ID',b'MOVE FUNCTION ABS(ACCT-ID) TO ACUP-OLD-ACCT-ID'),'changed.cbl')


    def test_generic_edit_compiler_preserves_messages_predicates_and_refuses_new_verbs(self):
        from lightyear_data.carddemo.screen_edits import build as edits
        raw=(ROOT/'upstream/app/cbl/COACTUPC.cbl').read_bytes()
        model=edits(raw,'app/cbl/COACTUPC.cbl')
        self.assertEqual(7,len(model['paragraphs']))
        self.assertEqual('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',model['fields']['LIT-ALL-ALPHA-FROM-X']['initial'])
        self.assertEqual(["'Y'","'N'"],model['conditions']['FLG-YES-NO-ISVALID']['values'])
        self.assertEqual(75,model['fields']['WS-RETURN-MSG']['length'])
        import json
        changed=edits(raw.replace(b"' must not be zero.'",b"' zero is forbidden.'"),'changed.cbl')
        self.assertIn(' zero is forbidden.',json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'unsupported edit verb'):
            edits(raw.replace(b'SET FLG-MANDATORY-NOT-OK    TO TRUE',b'DISPLAY WS-EDIT-ALPHANUM-ONLY'),'changed.cbl')
        with self.assertRaisesRegex(ValueError,'unsupported edit transfer'):
            edits(raw.replace(b'GO TO  1215-EDIT-MANDATORY-EXIT',b'GO TO SOME-OTHER-PARAGRAPH'),'changed.cbl')


    def test_quoted_copy_and_called_date_service_are_in_the_source_closure(self):
        import json
        from lightyear_data.carddemo.source_closure import build as closure
        model=build(ROOT)
        self.assertEqual({'CSUTLDTC'},set(model['support_programs']))
        dependencies=model['source_closure']['dependencies']
        for name in ('CSUTLDWY','CSSTRPFY','CSUTLDTC'):
            self.assertTrue(any(d['name']==name and d['resolution']=='pinned-source' for d in dependencies))
        self.assertTrue(any(d['name']=='CEEDAYS' and d['resolution']=='external-intrinsic' for d in dependencies))
        proof=json.loads((ROOT/'provenance.json').read_bytes())
        del proof['files']['app/cpy/CSUTLDWY.cpy']
        with self.assertRaisesRegex(ValueError,'source dependency absent.*CSUTLDWY'):
            closure(ROOT,proof,json.loads((ROOT/'slice-1.json').read_bytes()))

    def test_lookup_edits_bind_source_tables_ranges_and_aliases(self):
        from lightyear_data.carddemo.screen_edits import build as edits
        raw=(ROOT/'upstream/app/cbl/COACTUPC.cbl').read_bytes()
        path='app/cpy/CSLKPCDY.cpy';lookup=(ROOT/'upstream'/path).read_bytes()
        model=edits(raw,'app/cbl/COACTUPC.cbl',(path,lookup))
        self.assertEqual(13,len(model['paragraphs']))
        self.assertEqual([dict(lower='300',upper='850')],model['conditions']['FICO-RANGE-IS-VALID']['ranges'])
        self.assertEqual('ACUP-NEW-CUST-FICO-SCORE-X',model['fields']['ACUP-NEW-CUST-FICO-SCORE']['alias_of'])
        self.assertIn("'CA94'",model['conditions']['VALID-US-STATE-ZIP-CD2-COMBO']['values'])
        changed=edits(raw,'app/cbl/COACTUPC.cbl',(path,lookup.replace(b"'CA94'",b"'CA00'")))
        self.assertNotIn("'CA94'",changed['conditions']['VALID-US-STATE-ZIP-CD2-COMBO']['values'])
        self.assertIn("'CA00'",changed['conditions']['VALID-US-STATE-ZIP-CD2-COMBO']['values'])
        self.assertEqual(path,model['conditions']['VALID-US-STATE-CODE']['source'])

    def test_ssn_implicit_period_scope_and_perform_are_not_flattened(self):
        model=build(ROOT)['account_update']['generic_edits']
        body=model['paragraphs']['1265-EDIT-US-SSN']
        outer=next(x for x in body if x['op']=='if')
        self.assertEqual('FLG-EDIT-US-SSN-PART1-ISVALID',outer['test']['name'])
        self.assertEqual(2,sum(x['op']=='perform' for x in outer['yes']))
        self.assertEqual(1,sum(x['op']=='perform' for x in body))
        self.assertEqual([dict(lower='900',upper='999')],model['conditions']['INVALID-SSN-PART1']['ranges'])

    def test_phone_storage_and_internal_transfers_come_from_source(self):
        model=build(ROOT)['account_update']['generic_edits']
        fields={f['path'].split('.')[-1]:f for f in model['storage']['fields']}
        text=fields['WS-EDIT-US-PHONE-NUMA'];numeric=fields['WS-EDIT-US-PHONE-NUMA-N']
        self.assertEqual(text['offset'],numeric['offset'])
        self.assertEqual(3,numeric['length'])
        flags=fields['WS-EDIT-US-PHONE-NUM-FLGS']
        self.assertEqual(3,flags['length'])
        self.assertEqual(flags['offset'],fields['WS-EDIT-US-PHONEA-FLG']['offset'])
        labels={x['name'] for x in model['paragraphs']['1260-EDIT-US-PHONE-NUM'] if x['op']=='label'}
        self.assertEqual({'EDIT-AREA-CODE','EDIT-US-PHONE-PREFIX','EDIT-US-PHONE-LINENUM','EDIT-US-PHONE-EXIT'},labels)


    def test_date_copy_retains_fallthrough_labels_shared_storage_and_feedback_origins(self):
        model=build(ROOT)['account_update']['date_edits']
        labels={s['name'] for s in model['paragraphs']['EDIT-DATE-CCYYMMDD'] if s['op']=='label'}
        self.assertTrue({'EDIT-YEAR-CCYY-EXIT','EDIT-MONTH','EDIT-DAY','EDIT-DATE-LE'} <= labels)
        fields={f['path'].split('.')[-1]:f for f in model['storage']['fields']}
        self.assertEqual(fields['WS-EDIT-DATE-CCYYMMDD']['offset'],fields['WS-EDIT-DATE-CCYYMMDD-N']['offset'])
        self.assertEqual(8,fields['WS-EDIT-DATE-CCYYMMDD']['length'])
        self.assertEqual(2508,model['service']['feedback']['FC-BAD-DATE-VALUE']['message'])
        self.assertEqual('app/cbl/CSUTLDTC.cbl',model['service']['feedback']['FC-BAD-DATE-VALUE']['source'])

    def test_validation_sequence_retains_no_change_confirmation_and_literal_periods(self):
        result=build(ROOT)['account_update']['validation']
        self.assertIn('1200-EDIT-MAP-INPUTS',result['paragraphs'])
        self.assertIn('1250-EDIT-SIGNED-9V2',result['paragraphs'])
        self.assertEqual(["'No change detected with respect to values fetched.'"],result['conditions']['NO-CHANGES-DETECTED']['values'])
        self.assertGreater(result['area_offset'],0)
        self.assertEqual(2000,result['area_length'])
        self.assertTrue(any(f['path'].endswith('.ACUP-OLD-ACCT-DATA') for f in result['storage']['fields']))

    def test_authorization_render_and_linked_sql_are_derived_with_complete_inventory(self):
        result=build(ROOT)
        summary=result['authorization']['COPAUS0C'];detail=result['authorization']['COPAUS1C']
        self.assertEqual(5,sum(name.startswith('ROW-') and name!='ROW-PREFIX' for name in summary['paragraphs']))
        self.assertEqual(10,len(detail['lookups']['WS-DECLINE-REASON-TAB']))
        self.assertEqual('INVALID CARD    ',detail['lookups']['WS-DECLINE-REASON-TAB'][1]['description'])
        self.assertEqual('-ZZZZZZZ9.99',detail['fields']['WS-AUTH-AMT']['picture'])
        self.assertEqual(26,len(result['fraud']['action']['bindings']))
        self.assertEqual(['auth_fraud','fraud_rpt_date'],result['fraud']['action']['update_columns'])
        for screen in result['screens']:
            names={f['name'] for f in screen['model']['maps'][0]['fields'] if f['name']}
            self.assertTrue(all(h['target'] in names for h in result['programs'][screen['program']]['headers']))

    def test_header_scanner_does_not_treat_commarea_prefix_as_bms_output(self):
        raw=b"       IDENTIFICATION DIVISION.\n       PROGRAM-ID. EXAMPLE1.\n           MOVE WS-PGMNAME TO CDEMO-FROM-PROGRAM\n           MOVE WS-PGMNAME TO PGMNAMEO\n"
        self.assertEqual(['PGMNAME'],[h['target'] for h in program(raw,'example.cbl')['headers']])
