"""Synthetic CI scope refusal tests; no formatter or factory execution here."""
import unittest
from tools.java_format_fenced import selected,verify
class FencedFormatTests(unittest.TestCase):
    def test_only_selected_modifications_are_reported(self):
        self.assertEqual(['a'],verify({'a':'1','b':'2'},{'a':'3','b':'2'},['a']))
        self.assertEqual([],verify({'a':'1'},{'a':'1'},['a']))
    def test_unlisted_modification_deletion_and_addition_refuse(self):
        for after in ({'a':'2'},{},{'a':'1','b':'2'}):
            with self.assertRaises(ValueError):verify({'a':'1'},after,[])
    def test_reserved_unsafe_duplicate_and_empty_scopes_refuse(self):
        prefix='factory/carddemo-web/service/src/main/java/ai/lightyear/carddemo/'
        valid=prefix+'Commarea.java';self.assertEqual([valid],selected({'selected':[{'path':valid}]}))
        for names in ([],[valid,valid],[prefix+'AuthorizationRecords.java'],[prefix+'SourceEdits.java'],['../bad.java'],['elsewhere.java'],[prefix+'authorization/X.java']):
            with self.assertRaises(ValueError):selected({'selected':[{'path':p} for p in names]})
