"""Synthetic scope/fence refusal checks; CI alone runs the formatter."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.java_format_unfenced import selected, verify, combined_fence, check_scope_fence, inventory, require_clean

class UnfencedFormatTests(unittest.TestCase):
    def test_selected_modifications_only(self):
        self.assertEqual(['a'],verify({'a':'1','b':'2'},{'a':'3','b':'2'},['a']))
        self.assertEqual([],verify({'a':'1'},{'a':'1'},['a']))
        for after in ({'a':'2'},{},{'a':'1','b':'2'}):
            with self.assertRaises(ValueError):verify({'a':'1'},after,[])

    def test_unsafe_reserved_duplicate_empty_and_test_roots_refuse(self):
        prefix='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
        valid=prefix+'AccountMapModel.java'
        self.assertEqual([valid],selected({'selected':[{'path':valid}]}))
        for names in ([],[valid,valid],[prefix+'AuthorizationRecords.java'],[prefix+'SourceEdits.java'],['../bad.java'],['elsewhere.java'],[prefix+'authorization/X.java'],[prefix+'COPAU00.java'],[prefix.replace('/main/','/test/')+'X.java'],[prefix+'../X.java'],[prefix+'a:X.java']):
            with self.subTest(names=names),self.assertRaises(ValueError):selected({'selected':[{'path':p} for p in names]})

    def test_posttran_union_and_invalid_inventory(self):
        plan={'bound_files':{'b'+str(i):'hash' for i in range(182)},'candidate_files':{'c1':'hash','c2':'hash'}}
        with patch('tools.java_format_unfenced.derive',return_value={'paths':['copau'],'prefixes':['frozen/'],'inputs':{}}):
            result=combined_fence(lambda _:json.dumps(plan).encode(),['docs/factory/posttran-control.json'])
            self.assertTrue({'copau','b0','b181','c1','c2','docs/factory/posttran-control.json'}<=set(result['paths']))
            self.assertEqual(['frozen/'],result['prefixes'])
            plan['bound_files'].pop('b0')
            with self.assertRaises(ValueError):combined_fence(lambda _:json.dumps(plan).encode(),[])

    def test_exact_and_prefix_fences_refuse_at_trusted_base(self):
        fence={'paths':['exact.java'],'prefixes':['frozen/']}
        with patch('tools.java_format_unfenced.git',side_effect=lambda root,*a:b'base\n' if a[0]=='rev-parse' else b'exact.java\n'),patch('tools.java_format_unfenced.combined_fence',return_value=fence):
            for names in (['exact.java'],['frozen/new.java']):
                with self.assertRaises(ValueError):check_scope_fence(Path('.'),'base',names)
            self.assertEqual(1,check_scope_fence(Path('.'),'base',['allowed.java'])['paths'])

    def test_nonregular_tracked_input_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'directory').mkdir()
            with patch('tools.java_format_unfenced.git',return_value=b'directory\0'),self.assertRaises(ValueError):inventory(root)

    def test_current_scope_is_unfenced_and_all_sources_bound(self):
        from hashlib import sha256
        from tools.check_java_quality_fence import violations
        root=Path(__file__).resolve().parents[1]
        scope=json.loads((root/'tools/java-format/unfenced-scope.json').read_bytes())
        names=selected(scope)
        tracked=[p.relative_to(root).as_posix() for p in (root/'docs/factory').glob('*.json')]
        fence=combined_fence(lambda p:(root/p).read_bytes(),tracked)
        self.assertEqual([],violations(fence,names))
        for row in scope['selected']:
            self.assertEqual(row['sha256'],sha256((root/row['path']).read_bytes()).hexdigest())

    def test_formatted_batch_rejects_any_remaining_formatter_change(self):
        require_clean([])
        with self.assertRaisesRegex(ValueError, 'format-not-clean'):
            require_clean(['AccountFicoRule.java'])
