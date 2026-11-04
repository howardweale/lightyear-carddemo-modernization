"""CI-only original ZIP -> native envelope composition, never production evidence.

Real disposable Ed25519 fixture signatures and the existing archive decoder are
used together. No API, admission, controller context, production signer or
outcome authority is fabricated. Every fixture retains its original gaps and
production_controller_receipt=False.
"""
from io import BytesIO
from pathlib import Path
import copy
import hashlib
import os
import tempfile
import unittest
import zipfile

from lightyear_control_tower.decisions import canonical
from lightyear_factory.contracts import ContractError
from tools.ci.configured_outcome_archive import read_outcome_archive
from tools.ci.p5_drills import DRILLS, qualify
import test_configured_human_outcome_inventory as fixtures


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'CI-only disposable cryptography')
class OutcomeArchiveComposition(unittest.TestCase):
    def setUp(self):
        # Reuse existing native signing fixture construction without importing
        # its TestCase class into this module's unittest discovery namespace.
        self.fixture = fixtures.OutcomeInventoryBindings()
        self.fixture.setUp()

    def archive(self, original, compression=zipfile.ZIP_STORED):
        output = BytesIO()
        with zipfile.ZipFile(output, 'w', compression=compression) as archive:
            for name, raw in original.items():
                archive.writestr(name, raw)
        raw = output.getvalue()
        return raw, hashlib.sha256(raw).hexdigest()

    def test_native_signatures_survive_stored_and_deflated_archive_but_not_qualify(self):
        original = self.fixture.pack()
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(compression=compression):
                raw, digest = self.archive(original, compression)
                returned = read_outcome_archive(raw, digest, self.fixture.expected)
                self.assertEqual(returned, original)
                # Original strict qualifier must still refuse this signed,
                # independently bound, byte-exact disposable inventory.
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    for name, value in returned.items():
                        (root / name).write_bytes(value)
                    self.assertFalse(qualify(root))

    def test_resigned_wrong_run_refuses_after_valid_archive_digest(self):
        bodies = copy.deepcopy(self.fixture.bodies)
        bodies[DRILLS[0]]['run_id'] = '124'
        original = self.fixture.pack(bodies)
        raw, digest = self.archive(original)
        with self.assertRaisesRegex(ContractError, 'independent-run-source'):
            read_outcome_archive(raw, digest, self.fixture.expected)

    def test_changed_unsigned_summary_cannot_override_signed_fixture_gaps(self):
        import json
        original = self.fixture.pack()
        report = json.loads(original['summary.json'])
        report['drills'][0]['gaps'] = []
        original['summary.json'] = canonical(report)
        raw, digest = self.archive(original)
        with self.assertRaisesRegex(ContractError, 'signed-row-relations'):
            read_outcome_archive(raw, digest, self.fixture.expected)

    def test_archive_mismatch_refuses_before_invalid_expectation_provisioning(self):
        original = self.fixture.pack()
        raw, _ = self.archive(original)
        with self.assertRaisesRegex(ContractError, 'archive-digest'):
            read_outcome_archive(raw, '0' * 64, {})
