import copy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from tools.carddemo_idiomatic_status import INPUT, PATH, load, paragraph, render

ROOT = Path(__file__).resolve().parents[1]


class IdiomaticStatusTests(unittest.TestCase):
    def fixture(self, root):
        group = json.loads((ROOT/INPUT).read_bytes())
        names = {INPUT, *[group[k]['path'] for k in ('receipt','mutations','scope','baseline','manifest')]}
        names.update(json.loads((ROOT/group['manifest']['path']).read_bytes()))
        for name in names:
            target = root/name; target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes())
        return group

    def change_receipt(self, root, group, value):
        path = root/group['receipt']['path']
        path.write_text(json.dumps(value),encoding='utf-8')
        group['receipt']['sha256'] = sha256(path.read_bytes()).hexdigest()
        manifest_path = root/group['manifest']['path']
        manifest = json.loads(manifest_path.read_bytes())
        manifest[group['receipt']['path']] = group['receipt']['sha256']
        manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
        group['manifest']['sha256'] = sha256(manifest_path.read_bytes()).hexdigest()
        (root/INPUT).write_text(json.dumps(group),encoding='utf-8')

    def test_retained_xml_and_every_scenario_bind_the_group(self):
        value = load(ROOT, INPUT)
        self.assertEqual(120,value['cases']);self.assertEqual(678,value['interactions'])
        self.assertEqual((702,769),(value['killed'],value['total']))
        self.assertEqual((701,768),(value['previous_killed'],value['previous_total']))
        self.assertEqual(15,value['current']['SignonRules']['killed'])
        self.assertEqual(21,value['current']['SignonService']['total'])
        self.assertEqual(2,len(value['current']['SignonService']['non_killed']))
        self.assertEqual(4,len(value['remaining_statement_engine_programs']))
        self.assertTrue(value['unsigned'])

    def test_changed_counts_scope_and_date_change_both_texts(self):
        before = load(ROOT, INPUT); after = copy.deepcopy(before)
        after.update(date='2026-10-19',killed=703,interactions=679)
        after['current']['SignonService']['killed'] = 20
        after['remaining_statement_engine_programs'].remove('COACTUPC')
        for formatter in (paragraph,render):
            old,new = formatter(before),formatter(after)
            self.assertNotEqual(old,new)
            self.assertIn('703/769',new);self.assertIn('679/679',new)
            self.assertIn('2026-10-19',new);self.assertIn('20/21',new)
            self.assertNotIn('COACTUPC',new)

    def test_tampering_timeout_credit_class_and_case_omission_fail(self):
        for case in ('hash','timeout','class','cases','scope'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);group=self.fixture(root)
                value=json.loads((root/group['receipt']['path']).read_bytes())
                if case in ('hash','timeout'):value['gates']['mutation']['killed']+=1
                elif case=='class':value['gates']['mutation']['idiomatic_java']['current']['SignonService']['killed']+=1
                elif case=='cases':value['gates']['api-reference']['completed_cases']-=1
                else:value['gates']['mutation']['idiomatic_java']['remaining_statement_engine_programs'].pop()
                if case=='hash':(root/group['receipt']['path']).write_text(json.dumps(value))
                else:self.change_receipt(root,group,value)
                with self.assertRaises(ValueError):load(root,INPUT)

    def test_temporary_status_tree_keeps_bound_scope_and_rejects_tampering(self):
        from tools.render_oct16_status import copy_status_inputs
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'source', Path(temp)/'target'
            group = self.fixture(source)
            (source/PATH).write_text(json.dumps(group), encoding='utf-8')
            for name in ('src/lightyear_control_tower/threshold_evidence.py',
                         'src/lightyear_factory/threshold3.py'):
                path = source/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('# fixture implementation marker\n', encoding='utf-8')
            copy_status_inputs(source, target)
            scope = group['scope']['path']
            self.assertEqual((source/scope).read_bytes(), (target/scope).read_bytes())
            self.assertEqual(load(source), load(target))
            (target/scope).write_bytes((target/scope).read_bytes()+b'\n')
            with self.assertRaisesRegex(ValueError, 'idiomatic-evidence-hash'):
                load(target)
            self.assertEqual(group['scope']['sha256'], sha256((source/scope).read_bytes()).hexdigest())

    def test_readme_has_one_receipt_derived_status_and_no_obsolete_pending_claim(self):
        readme = (ROOT/'factory/carddemo-web/README.md').read_text(encoding='utf-8')
        start, end = '<!-- idiomatic-group-status:start -->', '<!-- idiomatic-group-status:end -->'
        self.assertEqual(1, readme.count(start)); self.assertEqual(1, readme.count(end))
        block = readme.split(start, 1)[1].split(end, 1)[0].strip()
        self.assertEqual(paragraph(load(ROOT)), block)
        self.assertNotIn('CI proof pending', readme)
        self.assertNotIn('No new score is claimed until that CI result exists', readme)
