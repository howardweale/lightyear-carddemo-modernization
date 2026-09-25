"""Measured lift, parser negatives, and schema/session admission controls."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import io
from contextlib import redirect_stdout
import unittest

from lightyear_calibration.adapters import discover, scan
from lightyear_calibration.contracts import CalibrationError, digest
from lightyear_calibration.instrument import build_report, compare_reports
from lightyear_calibration.sql_context import baseline, predicate
from lightyear_calibration.sql_parser import parse_script
from lightyear_calibration.sql_gate import compare_pair
from lightyear_data.idempiere_sql import lex, Unsupported

ROOT=Path(__file__).resolve().parents[1]


class ParserLoopTests(unittest.TestCase):
    def test_public_gate_annotations_resolve(self):
        import typing
        self.assertIn('return',typing.get_type_hints(compare_pair))

    def test_deferral_state_not_discarded(self):
        pre='ALTER TABLE a ADD CONSTRAINT f FOREIGN KEY(id) REFERENCES b(id) '
        for suffix in ['DEFERRABLE INITIALLY DEFERRED','INITIALLY DEFERRED DEFERRABLE ENABLE NOVALIDATE']:
            unit=parse_script(pre+suffix+';','oracle')[0]
            self.assertTrue(unit.parsed,unit.reasons)
            self.assertEqual('deferred',unit.effects[0]['value']['initially'])
            self.assertIn('constraint-column-domain-required',unit.effects[0]['reasons'])
        for suffix in ['NOT DEFERRABLE INITIALLY DEFERRED','DEFERRABLE DEFERRABLE','DEFERRABLE GARBAGE','ENABLE ENABLE','INITIALLY DEFERRED']:
            self.assertFalse(parse_script(pre+suffix+';','oracle')[0].parsed)
        self.assertFalse(parse_script(pre+'ENABLE NOVALIDATE;','postgresql')[0].parsed)
        r=compare_pair('c',pre+'DEFERRABLE INITIALLY DEFERRED;',pre+'NOT DEFERRABLE;')
        self.assertEqual('indeterminate',r['verdict'])
        self.assertTrue(r['declared_differences'])

    def test_grouped_drop_and_national_type_retain_obligations(self):
        u=parse_script('ALTER TABLE x DROP (a,b);','oracle')[0]
        self.assertEqual(['x.a','x.b'],[e['target'] for e in u.effects])
        self.assertFalse(parse_script('ALTER TABLE x DROP (a,a);','oracle')[0].parsed)
        self.assertFalse(parse_script('ALTER TABLE x DROP (a,b);','postgresql')[0].parsed)
        u=parse_script('ALTER TABLE x MODIFY (a NVARCHAR2(20), b NCHAR(3));','oracle')[0]
        self.assertTrue(u.parsed)
        self.assertEqual('national',u.effects[0]['value']['character_set'])
        self.assertIn('national-character-domain-context-required',u.effects[0]['reasons'])
        self.assertFalse(parse_script('ALTER TABLE x ADD a NVARCHAR2(20);','postgresql')[0].parsed)
        self.assertFalse(parse_script('ALTER TABLE x ADD a NVARCHAR2(20 BYTE);','oracle')[0].parsed)
        self.assertFalse(parse_script('ALTER TABLE x ADD a NVARCHAR2(20) GARBAGE;','oracle')[0].parsed)

    def test_prefix_stops_and_never_resynchronizes(self):
        oracle='ALTER TABLE x ADD a NUMBER(8); UNKNOWN THING; ALTER TABLE x ADD b NUMBER(8);'
        pg='ALTER TABLE x ADD a NUMERIC(8); ALTER TABLE x ADD b NUMERIC(8);'
        r=compare_pair('c',oracle,pg)
        self.assertEqual(1,r['coverage']['oracle']['parsed-and-compared'])
        self.assertEqual(1,r['coverage']['postgresql']['parsed-and-compared'])
        self.assertEqual('indeterminate',r['verdict'])
        self.assertEqual(0,compare_pair('c',oracle,pg,prefix_alignment=False)['coverage']['oracle']['parsed-and-compared'])
        # Partial multi-effect units cannot be counted as decided.
        r=compare_pair('c','ALTER TABLE x ADD (a NUMBER(8),b NUMBER(8));','ALTER TABLE x ADD a NUMERIC(8);')
        self.assertEqual(0,r['coverage']['oracle']['parsed-and-compared'])

    def test_predicate_structure_precedence_and_trailing_garbage(self):
        p=predicate(lex('id=1 OR id=2 AND amount>=-3'),'oracle')
        self.assertEqual('or',p['kind']);self.assertEqual('and',p['terms'][1]['kind'])
        for text in ['id=1 garbage','id=evil()','id IN (SELECT id FROM x)','id=1 AND','id=1 UNION SELECT 1']:
            with self.subTest(text=text),self.assertRaises(Unsupported):predicate(lex(text),'oracle')


class ContextLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for side in ('source','target'):(self.root/side).mkdir()
        self.source='UPDATE accounts SET amount=12.50 WHERE id=7;'
        self.target=self.source
        self.write_inputs()

    def write_inputs(self):
        (self.root/'source'/'one.sql').write_text(self.source)
        (self.root/'target'/'one.sql').write_text(self.target)
        self.manifest=discover(self.root/'source',self.root/'target','oracle-postgresql-sql','context-test')
        self.before,texts=scan(self.manifest,include_texts=True)
        self.template=baseline(self.before,texts)
        self.context=deepcopy(self.template)
        self.context['evidence']={'mode':'declared-contract','references':[{'path':'fixture-catalog.json','sha256':'a'*64}]}
        for lane in self.context['cases']['one.sql']['lanes'].values():
            lane['session'].update(current_schema='app',search_path=['app'],numeric_characters='.,',standard_conforming_strings=True)
            table=lane['tables']['accounts']
            table.update(kind='base-table',complete=True,triggers=[],constraints=[],row_policies=[],rewrite_rules=[])
            table['columns']={k:{'type':{'canonical_type':'exact-decimal','precision':10,'scale':2 if k=='amount' else 0},'nullable':False} for k in ('id','amount')}

    def test_context_cli_generates_baseline_and_rejects_stale_scan_without_output(self):
        from lightyear_calibration.cli import main
        manifest=self.root/'corpus.json';manifest.write_text(json.dumps(self.manifest))
        generated=self.root/'baseline.json'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0,main(['baseline','--manifest',str(manifest),'--output',str(generated)]))
        self.assertEqual(self.template,json.loads(generated.read_text()))
        invalid=deepcopy(self.context);invalid['corpus_sha256']='0'*64
        generated.write_text(json.dumps(invalid));out=self.root/'scan-output'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(2,main(['scan','--manifest',str(manifest),'--context',str(generated),'--output',str(out)]))
        self.assertFalse(out.exists())

    def test_pinned_replay_consumes_its_own_baseline(self):
        from lightyear_calibration.replay import replay_idempiere
        from lightyear_calibration.contracts import seal,read_json
        from lightyear_data.idempiere_comparison import compare_pair as old_compare, _totals
        import hashlib
        source=self.root/'pinned';source.mkdir()
        pair={'pair_id':'one.sql'}
        for dialect,text in [('oracle',self.source),('postgresql',self.target)]:
            path=dialect+'.sql';(source/path).write_text(text)
            pair[dialect]={'path':path,'logical_sha256':hashlib.sha256(text.encode()).hexdigest(),'lines':1}
        manifest=seal({'source':{'commit':'c'*40,'tree':'d'*40},'pairs':[pair]})
        old=old_compare('one.sql',self.source,self.target)
        retained=seal({'schema_version':'1.0','artifact_type':'lightyear-idempiere-semantic-comparison',
             'scope':'all-current-pairs','project_id':'synthetic-replay',
             'bindings':{'pairing_manifest_sha256':manifest['content_sha256'],'source_commit':'c'*40,'source_tree':'d'*40},
             'results':[old],'statistics':_totals([old])})
        first=self.root/'first'
        replay_idempiere(source,retained,manifest,first)
        acquired=read_json(first/'schema-session-baseline.json')
        supplied=deepcopy(self.context)
        supplied['corpus_sha256']=acquired['corpus_sha256']
        supplied['cases']['one.sql']['inputs']=acquired['cases']['one.sql']['inputs']
        after=replay_idempiere(source,retained,manifest,self.root/'second',context=supplied)
        self.assertEqual(2,after['counts']['after']['parsed-and-compared'])
        self.assertEqual(digest(supplied),after['applied_context_sha256'])
        self.assertTrue((self.root/'second/context-used.json').is_file())
        supplied['corpus_sha256']='0'*64
        with self.assertRaises(CalibrationError):
            replay_idempiere(source,retained,manifest,self.root/'stale',context=supplied)
        self.assertFalse((self.root/'stale').exists())

    def test_real_loop_and_input_bound_template(self):
        self.assertEqual('indeterminate',self.before['cases'][0]['verdict'])
        self.assertEqual('indeterminate',scan(self.manifest,context=self.template)['cases'][0]['verdict'])
        after=scan(self.manifest,context=self.context)
        self.assertEqual('equivalent',after['cases'][0]['verdict'])
        delta=compare_reports(build_report(self.before),build_report(after))
        self.assertEqual((0,2),(delta['before']['decided_units'],delta['after']['decided_units']))
        self.assertEqual(digest(self.context),after['gate']['context_sha256'])
        self.assertEqual(0,after['provenance']['runtime_invocations'])

    def test_unknown_catalog_or_session_is_not_permission_to_pass(self):
        for key,value in [('triggers',None),('triggers',['audit_trigger']),('constraints',['fk']),('row_policies',['rls']),('rewrite_rules',['rule']),('complete',False),('kind','view')]:
            context=deepcopy(self.context);context['cases']['one.sql']['lanes']['oracle']['tables']['accounts'][key]=value
            with self.subTest(key=key,value=value):self.assertEqual('indeterminate',scan(self.manifest,context=context)['cases'][0]['verdict'])
        context=deepcopy(self.context);context['cases']['one.sql']['lanes']['postgresql']['session']['search_path']=['untrusted','app']
        self.assertEqual('indeterminate',scan(self.manifest,context=context)['cases'][0]['verdict'])
        context=deepcopy(self.context);context['cases']['one.sql']['lanes']['oracle']['tables']['accounts']['columns']['id']['type']=None
        self.assertEqual('indeterminate',scan(self.manifest,context=context)['cases'][0]['verdict'])

    def test_mutations_are_detected_and_never_normalized_away(self):
        self.target='UPDATE accounts SET amount=12.51 WHERE id=7;';self.write_inputs()
        self.assertEqual('divergent',scan(self.manifest,context=self.context)['cases'][0]['verdict'])
        for target in ['UPDATE accounts SET amount=12.50 WHERE id=8;',
                       'UPDATE accounts SET amount=unknown_fn() WHERE id=7;',
                       "UPDATE accounts SET amount='12.50' WHERE id=7;",
                       'UPDATE accounts SET amount=12.501 WHERE id=7;']:
            self.target=target;self.write_inputs()
            with self.subTest(target=target):self.assertEqual('indeterminate',scan(self.manifest,context=self.context)['cases'][0]['verdict'])

    def test_schema_change_expires_entry_baseline(self):
        self.source='ALTER TABLE accounts ADD spare NUMBER(4); '+self.source
        self.target='ALTER TABLE accounts ADD spare NUMERIC(4); '+self.target
        self.write_inputs();r=scan(self.manifest,context=self.context)
        self.assertEqual('indeterminate',r['cases'][0]['verdict'])
        self.assertEqual(2,build_report(r)['summary']['decided_units'])

    def test_stale_or_malformed_baseline_is_rejected(self):
        for mutate in [lambda c:c.update(corpus_sha256='0'*64),lambda c:c['cases'].clear(),
                       lambda c:c['cases']['one.sql']['inputs']['oracle'].update(sha256='0'*64),
                       lambda c:c['cases']['one.sql']['lanes']['oracle']['tables']['accounts'].update(ignore_triggers=True)]:
            context=deepcopy(self.context);mutate(context)
            with self.assertRaises(CalibrationError):scan(self.manifest,context=context)
        (self.root/'source'/'one.sql').write_text(self.source+'\n-- changed input')
        with self.assertRaises(CalibrationError):scan(self.manifest,context=self.context)


if __name__=='__main__':unittest.main()
