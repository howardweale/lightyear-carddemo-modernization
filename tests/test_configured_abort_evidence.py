"""CI-only early refusals. Synthetic bytes never confer admission or origin."""
import unittest
from lightyear_factory.contracts import ContractError
from lightyear_execution.configured_abort_evidence import check_abort_file_relations,LIMITS

class AbortEvidenceRefusalTests(unittest.TestCase):
    def test_missing_file_refused(self):
        with self.assertRaises(ContractError):check_abort_file_relations({})
    def test_extra_file_refused(self):
        raw={k:b'{}' for k in LIMITS};raw['receipt.json']=b'{}'
        with self.assertRaises(ContractError):check_abort_file_relations(raw)
    def test_string_instead_of_bytes_refused(self):
        raw={k:b'{}' for k in LIMITS};raw['human-admission.json']='{}'
        with self.assertRaises(ContractError):check_abort_file_relations(raw)
    def test_empty_original_refused(self):
        raw={k:b'{}' for k in LIMITS};raw['attempt-accounting.jsonl']=b''
        with self.assertRaises(ContractError):check_abort_file_relations(raw)
    def test_oversize_identity_refused(self):
        raw={k:b'{}' for k in LIMITS};raw['attempt-identity.json']=b'x'*(LIMITS['attempt-identity.json']+1)
        with self.assertRaises(ContractError):check_abort_file_relations(raw)
    def test_duplicate_json_key_refused(self):
        raw={k:b'{}' for k in LIMITS};raw['human-admission.json']=b'{"status":"passed","status":"blocked"}'
        with self.assertRaises(ContractError):check_abort_file_relations(raw)
    def test_nonfinite_json_refused(self):
        raw={k:b'{}' for k in LIMITS};raw['human-admission.json']=b'{"cost":NaN}'
        with self.assertRaises(ContractError):check_abort_file_relations(raw)
    def test_unhashed_mapping_refused(self):
        with self.assertRaises(ContractError):check_abort_file_relations({k:b'{}' for k in LIMITS})
