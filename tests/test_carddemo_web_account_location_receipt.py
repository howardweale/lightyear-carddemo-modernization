import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('location_receipt',ROOT/'factory/carddemo-web/runtime/receipt.py')
RECEIPT=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECEIPT)

class AccountLocationReceiptTests(unittest.TestCase):
    def evaluate(self, location, obsolete_model=()):
        root=ET.Element('mutations')
        def add(name,status):
            node=ET.SubElement(root,'mutation',status=status)
            ET.SubElement(node,'mutatedClass').text='ai.lightyear.carddemo.'+name
        # All other required classes remain present and green; they cannot mask this group.
        legacy=set(RECEIPT.CLASSES)|{'SignonRules','AccountInputRules','AccountTextRules',
            'AccountMoneyRule','CobolNumber','AccountSsnRule','AccountFicoRule'}
        for name in sorted(legacy):
            for _ in range(100):add(name,'KILLED')
        for name,statuses in [('AccountLocationRules',location),('AccountValidationModel',obsolete_model)]:
            for status in statuses:add(name,status)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'mutations.xml';ET.ElementTree(root).write(path)
            with patch.object(RECEIPT,'idiomatic_mutation',return_value={'passed':True}):
                return RECEIPT.mutation(path)

    def test_missing_class_and_timeout_are_not_success_or_borrowed_credit(self):
        green=['KILLED']*10
        self.assertFalse(self.evaluate([],green)['passed'])
        for status in ['TIMED_OUT','NO_COVERAGE','SURVIVED','RUN_ERROR','MEMORY_ERROR']:
            with self.subTest(status=status):
                value=self.evaluate(['KILLED']*8+[status]*2,green)
                self.assertEqual({'AccountLocationRules'},set(value['account_location_java']))
                row=value['account_location_java']['AccountLocationRules']
                self.assertEqual((8,10),(row['killed'],row['total']))
                self.assertEqual(2,len(row['non_killed']))
                self.assertGreater(value['percent'],90)
                self.assertFalse(value['passed'])

    def test_exact_ninety_percent_passes_without_rounding_or_deleted_class(self):
        value=self.evaluate(['KILLED']*9+['TIMED_OUT'])
        self.assertTrue(value['passed'])
        self.assertEqual({'AccountLocationRules'},set(value['account_location_java']))
        row=value['account_location_java']['AccountLocationRules']
        self.assertEqual((9,10,90.0),(row['killed'],row['total'],row['percent']))
        self.assertFalse(self.evaluate(['KILLED']*89+['SURVIVED']*11,['KILLED']*100)['passed'])
