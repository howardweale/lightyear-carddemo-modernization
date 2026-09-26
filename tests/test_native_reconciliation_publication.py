"""Verify the published result is bound to the retained native checkpoints."""
from functools import lru_cache
import gzip
import hashlib
import json
import zipfile
from pathlib import Path
import unittest
from lightyear_calibration.contracts import verify

ROOT=Path(__file__).resolve().parents[1]/'docs/calibration/idempiere-reconciliation'
@lru_cache(maxsize=1)
def evidence_archive():
    return zipfile.ZipFile(ROOT/'evidence.zip')


def evidence_bytes(name):
    return evidence_archive().read(name)


def evidence_json(name):
    return json.loads(evidence_bytes(name))


class ReconciliationPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addClassCleanup(evidence_archive().close)

    def test_evidence_bytes_and_claim_boundaries(self):
        receipt=json.loads((ROOT/'receipt.json').read_text());verify(receipt)
        self.assertEqual(receipt['evidence_archive']['sha256'],hashlib.sha256((ROOT/'evidence.zip').read_bytes()).hexdigest())
        with zipfile.ZipFile(ROOT/'evidence.zip') as archive:
            self.assertEqual(set(receipt['evidence_files']),set(archive.namelist()))
        for name,expected in receipt['evidence_files'].items():
            path=(ROOT/name).resolve()
            self.assertTrue(path.is_relative_to(ROOT.resolve()))
            self.assertEqual(expected,hashlib.sha256(evidence_bytes(name)).hexdigest(),name)
        for name,expected in receipt.get('compressed_payloads',{}).items():
            data=gzip.decompress(evidence_bytes(name))
            self.assertEqual(expected['uncompressed_bytes'],len(data))
            self.assertEqual(expected['uncompressed_sha256'],hashlib.sha256(data).hexdigest())
        for key in ('application_equivalence','schema_equivalence','platform_qualification','oracle_catalog_native_conformance_claim'):
            self.assertFalse(receipt[key])
        for name,expected in receipt.get('implementation_sha256',{}).items():
            self.assertEqual(expected,hashlib.sha256((ROOT.parents[2]/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),name)
        core=evidence_json('evidence/rerun/result.json');verify(core)
        self.assertEqual(receipt['release13']['migration_pairs'],len(core['pairs']))
        for pair in core['pairs']:
            checkpoint=evidence_json(f"evidence/rerun/case-{pair['ordinal']:03}/checkpoint.json");verify(checkpoint)
            self.assertTrue(checkpoint['admitted'])
            self.assertFalse(checkpoint['unresolved_differences'])
            self.assertEqual(pair['checkpoint_sha256'],checkpoint['content_sha256'])
        maintenance=evidence_json('evidence/maintenance/processes_post_migration/reviewed-checkpoint.json');verify(maintenance)
        self.assertEqual(receipt['release13']['final_checkpoint_sha256'],maintenance['content_sha256'])
        self.assertTrue(maintenance['admitted'])
        self.assertEqual(receipt['release13']['retained_allowed_final_fields'],len(maintenance['allowed_differences']))
        self.assertFalse(evidence_json('evidence/maintenance/processes_post_migration/checkpoint.json')['admitted'])

    def test_historical_totals_are_bound_to_release_checkpoints(self):
        receipt=json.loads((ROOT/'receipt.json').read_text());verify(receipt)
        history=receipt['history'];releases=history['release_checkpoints']
        self.assertEqual(len(releases),len({r['release'] for r in releases}))
        self.assertEqual(history['admitted_release_pairs'],sum(r['attempted_pairs'] for r in releases if r['admitted']))
        self.assertEqual(history['native_executions'],sum(r['native_executions'] for r in releases))
        plan=evidence_json('evidence/history/expanded-plan.json');verify(plan)
        self.assertEqual(history['planned_regular_pairs'],sum(p['release_segment']!='processes_post_migration' for p in plan['pairs']))
        for release in releases:
            checkpoint=evidence_json(release['checkpoint_file']);verify(checkpoint)
            self.assertEqual(release['checkpoint_sha256'],checkpoint['content_sha256'])
            validity=evidence_json(release['validity_file'])
            self.assertEqual(release['remaining_oracle_invalid_objects'],len(validity.get('invalid_objects',validity.get('after_recompile',[]))))
            self.assertEqual(release['remaining_oracle_compilation_errors'],len(validity['errors']))
            self.assertEqual(release['unresolved_differences'],len(checkpoint['unresolved_differences']))
            if release['admitted']:
                self.assertTrue(checkpoint['admitted'])
                self.assertEqual(release['attempted_pairs'],release['planned_pairs'])
                self.assertEqual(release['successful_pair_clients'],release['planned_pairs'])
                self.assertEqual(0,release['remaining_oracle_invalid_objects'])
                self.assertEqual(0,release['remaining_oracle_compilation_errors'])
