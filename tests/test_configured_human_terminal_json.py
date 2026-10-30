"""CI-only parsing boundary tests. Synthetic data grants no origin or authority."""
import json,os,unittest
from lightyear_factory.contracts import ContractError,canonical_hash
from lightyear_execution.configured_human_terminal import _original_json,_ledger_bytes


class ConfiguredTerminalJSONTests(unittest.TestCase):
    def setUp(self):self.assertEqual(os.environ.get('GITHUB_ACTIONS'),'true')

    def test_distinct_original_json_fields_are_preserved(self):
        value={'status':'blocked','payload':{'sequence':1,'billing_final':False}}
        self.assertEqual(_original_json(json.dumps(value).encode()),value)

    def test_duplicate_top_level_and_nested_keys_refused(self):
        for raw in (b'{"status":"passed","status":"blocked"}',
                    b'{"payload":{"calls":1,"calls":0}}'):
            with self.assertRaisesRegex(ContractError,'duplicate-json-key'):_original_json(raw)

    def test_nonfinite_json_constants_refused(self):
        for raw in (b'{"cost":NaN}',b'{"cost":Infinity}',b'{"cost":-Infinity}'):
            with self.assertRaisesRegex(ContractError,'nonfinite-json'):_original_json(raw)

    def test_boolean_sequence_refused_even_with_matching_self_hash(self):
        row={'sequence':True,'previous_sha256':None,'state':'BLOCKED',
             'kind':'controller_error','payload':{}}
        row['event_sha256']=canonical_hash(row)
        with self.assertRaisesRegex(ContractError,'ledger-chain'):
            _ledger_bytes(json.dumps(row).encode()+b'\n')

    def test_duplicate_ledger_sequence_refused_before_chain_interpretation(self):
        raw=b'{"sequence":2,"sequence":1,"previous_sha256":null}\n'
        with self.assertRaisesRegex(ContractError,'duplicate-json-key'):_ledger_bytes(raw)
