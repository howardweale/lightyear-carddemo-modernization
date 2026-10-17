"""CI-only temporary import roots; never open an installed Factory root."""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.factory_import import historical_contract,import_request
from lightyear_control_tower.factory_history_supersessions import SUPERSEDED

ROOT=Path(__file__).resolve().parents[1]

class HistoricalRecordsTests(unittest.TestCase):
    def test_every_preserved_backfill_imports_or_has_bound_supersession(self):
        record=json.loads((ROOT/'docs/factory/tower-backfill-supersessions-2026-10-17.json').read_bytes())
        markers={r['path']:r for r in record['records']}
        for path in sorted((ROOT/'docs/factory').glob('tower-backfill-request-*.json')):
            value=json.loads(path.read_bytes());name=path.relative_to(ROOT).as_posix()
            with self.subTest(path=name),tempfile.TemporaryDirectory() as td:
                if name in markers:
                    m=markers[name]
                    self.assertEqual(m['file_sha256'],sha256(path.read_bytes()).hexdigest())
                    self.assertEqual(m['contract_sha256'],sha256(canonical(value)).hexdigest())
                    self.assertEqual(m['superseded_by'],SUPERSEDED[m['contract_sha256']])
                    self.assertTrue((ROOT/m['superseded_by']).is_file())
                    with self.assertRaisesRegex(ValueError,'superseded'):import_request(ROOT,Path(td),value)
                    self.assertEqual([],list(Path(td).iterdir()))
                else:
                    self.assertTrue(import_request(ROOT,Path(td),value)['id'])

    def test_corrected_source_reproduces_signed_contract_fingerprint(self):
        record=json.loads((ROOT/'docs/factory/factory-local-activation-correction-2026-10-17.json').read_bytes())
        contract=historical_contract(ROOT,record['backfill_source_commit'])
        self.assertEqual('96d0043704ba1029328a1fe8e43cf82362328d3eff4dd57c377abd227d3243fd',sha256(canonical(contract)).hexdigest())
        self.assertEqual(record['backfill_record_count'],len(contract['details']['records']))
        self.assertFalse(record['new_activation_performed']);self.assertFalse(record['new_signature_created'])
        self.assertEqual(('Howard','Codex'),(record['authorized_by'],record['performed_by']))
