# CI-only negative coverage for the preserved original compiler archive.
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import check_posttran_key_change as checker

# Exact public preservation record committed at 008cf01d3497f9ef5a964f1915171d622afdb969.
PROVENANCE = json.loads(r'''{
  "schema": "posttran-compiler-preservation/1",
  "preservation_only": true,
  "execution_authorized": false,
  "repository": "howardweale/lightyear-carddemo-modernization",
  "original_artifact": {
    "id": 12052649453,
    "name": "posttran-phase2-compiler-image",
    "size_in_bytes": 177127016,
    "digest": "sha256:43138bbcd2010f9f55570bead3ec2323bd27889f5386666e0f34792cdd8dad6a",
    "workflow_run": {
      "id": 38917806865,
      "head_sha": "e3ee73d8bff7e18491724d377ea9329e96896f71"
    },
    "created_at": "2026-10-16T14:46:14Z",
    "expires_at": "2026-10-30T14:46:00Z"
  },
  "retrieval_started_at": "2026-10-29T15:54:24.865116+00:00",
  "retrieved_at": "2026-10-29T15:56:24.409780+00:00",
  "archive_sha256": "43138bbcd2010f9f55570bead3ec2323bd27889f5386666e0f34792cdd8dad6a",
  "image_sha256": "bac290dafdb7342822f51a4b40822c8a232cb3ae61b4de490c0127ac1c6484a2",
  "image_size_in_bytes": 426930688,
  "image_id": "sha256:c88e45c7d65cf9392819fb0b048c1802dba2e2e7df4762f2df889528236c16e7",
  "release": {
    "tag": "compiler-preservation-12052649453",
    "asset_name": "posttran-phase2-compiler-image-original.zip",
    "download_url": "https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/compiler-preservation-12052649453/posttran-phase2-compiler-image-original.zip"
  },
  "public_content_review_sha256": "b59d2121192a8b7bf49c36847ddd7de7b641b77fefbaa978fcb3d6e391d6dcc2",
  "original_metadata_sha256": "a94ed922a87d53a682ac900ef4d18123def54673d5f396e84978da8e474b3911",
  "no_changes": [
    "original artifact bytes",
    "original plan and seal",
    "original executable",
    "POSTTRAN workflow",
    "checker",
    "gates",
    "authorization",
    "attempt namespace"
  ]
}''')


class PreservedCompilerTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.record = json.loads((root / checker.RECORD / 'amendment.json').read_bytes())
        self.plan = json.loads((root / checker.PLAN).read_bytes())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'compiler.zip'

    def check(self, provenance=None):
        return checker.image_check(self.record, self.plan,
                                   PROVENANCE if provenance is None else provenance, self.archive)

    def test_fixture_matches_exact_committed_provenance_pin(self):
        raw = json.dumps(PROVENANCE, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), checker.PRESERVED_PROVENANCE)

    def test_missing_archived_copy_is_refused(self):
        with self.assertRaisesRegex(ValueError, '^archived-copy-missing$'):
            self.check()

    def test_wrong_archive_size_is_refused(self):
        self.archive.write_bytes(b'not the original archive')
        with self.assertRaisesRegex(ValueError, '^archive-size$'):
            self.check()

    def test_wrong_bytes_at_original_size_are_refused(self):
        # Sparse zero bytes at the real size must not pass the digest check.
        with self.archive.open('wb') as stream:
            stream.truncate(PROVENANCE['original_artifact']['size_in_bytes'])
        with self.assertRaisesRegex(ValueError, '^archive-digest$'):
            self.check()

    def test_wrong_original_provenance_is_refused(self):
        changes = [
            ('id', 12052649454),
            ('name', 'different-compiler'),
            ('size_in_bytes', 177127017),
            ('digest', 'sha256:' + '0' * 64),
            ('workflow_run', {'id': 38917806866, 'head_sha': PROVENANCE['original_artifact']['workflow_run']['head_sha']}),
            ('workflow_run', {'id': 38917806865, 'head_sha': '0' * 40}),
        ]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                altered = copy.deepcopy(PROVENANCE)
                altered['original_artifact'][key] = value
                with self.assertRaisesRegex(ValueError, '^archived-provenance$'):
                    self.check(altered)

    def test_wrong_archive_location_or_retrieval_record_is_refused(self):
        for key, value in [
            ('retrieved_at', '2026-10-31T00:00:00+00:00'),
            ('release', {'tag': 'different', 'asset_name': 'different.zip', 'download_url': 'https://example.invalid/other.zip'}),
            ('image_sha256', '0' * 64),
            ('execution_authorized', True),
        ]:
            with self.subTest(key=key):
                altered = copy.deepcopy(PROVENANCE)
                altered[key] = value
                with self.assertRaisesRegex(ValueError, '^archived-provenance$'):
                    self.check(altered)

    def test_live_metadata_is_not_an_archived_provenance_record(self):
        with self.assertRaisesRegex(ValueError, '^archived-provenance-schema$'):
            self.check(PROVENANCE['original_artifact'])
