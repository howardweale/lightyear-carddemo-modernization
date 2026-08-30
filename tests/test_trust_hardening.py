from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lightyear_common.trust import (
    CLAIM_FIELDS,
    TrustBoundaryError,
    audit_receipt_claims,
    audit_script_catalog,
    require_unpromoted_claims,
    validate_upstream_fixture,
)


ROOT = Path(__file__).resolve().parents[1]


class ReceiptTrustBoundaryTests(unittest.TestCase):
    def test_repository_claims_and_script_catalog_validate(self) -> None:
        self.assertEqual([], audit_receipt_claims(ROOT))
        self.assertEqual([], audit_script_catalog(ROOT))
        self.assertEqual([], validate_upstream_fixture(ROOT))

    def test_all_four_claims_are_required_and_individually_fail_closed(self) -> None:
        receipt = {field: False for field in CLAIM_FIELDS}
        require_unpromoted_claims(receipt)
        for field in CLAIM_FIELDS:
            with self.subTest(field=field):
                mutated = dict(receipt)
                mutated[field] = True
                with self.assertRaisesRegex(TrustBoundaryError, field):
                    require_unpromoted_claims(mutated)
        for field in CLAIM_FIELDS:
            with self.subTest(missing=field):
                mutated = dict(receipt)
                mutated.pop(field)
                with self.assertRaisesRegex(TrustBoundaryError, field):
                    require_unpromoted_claims(mutated)

    def test_literal_python_and_json_promotions_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/emitter.py").write_text(
                "receipt = {'production_ready': True}\n", encoding="utf-8"
            )
            (root / "receipt.json").write_text(
                json.dumps({"mainframe_equivalent": True}), encoding="utf-8"
            )
            errors = audit_receipt_claims(root)
        self.assertTrue(any("production_ready" in error for error in errors))
        self.assertTrue(any("mainframe_equivalent" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
