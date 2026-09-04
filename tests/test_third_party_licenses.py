from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ThirdPartyLicenseTests(unittest.TestCase):
    def test_reference_license_copies_match_pinned_hashes(self) -> None:
        cases = [
            (
                "reference-estates/idempiere/source-pin.json",
                "LICENSES/GPL-2.0-only.md",
            ),
            (
                "reference-estates/cloudbank/source-pin.json",
                "LICENSES/UPL-1.0.txt",
            ),
        ]
        for pin_path, license_path in cases:
            pin = json.loads((ROOT / pin_path).read_text(encoding="utf-8"))
            digest = hashlib.sha256((ROOT / license_path).read_bytes()).hexdigest()
            self.assertEqual(pin["license"]["license_sha256"], digest)

    def test_carddemo_license_and_notice_are_bundled(self) -> None:
        license_text = (ROOT / "LICENSES/Apache-2.0.txt").read_text(encoding="utf-8")
        notice = (ROOT / "LICENSES/AWS-CardDemo-NOTICE.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        self.assertEqual(
            "Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.",
            notice.strip(),
        )

    def test_oracle_non_affiliation_notice_is_explicit(self) -> None:
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn(
            "does not sponsor, endorse, or certify LIGHTYEAR",
            " ".join(notices.split()),
        )


if __name__ == "__main__":
    unittest.main()
