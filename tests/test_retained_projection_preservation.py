# CI-only negative coverage; network is mocked, verification and original pins are real.
import copy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from tools import build_oct16_review_projections as checker

PROVENANCE = b'{\r\n  "schema": "github-actions-artifact-preservation/1",\r\n  "preservation_only": true,\r\n  "execution_authorized": false,\r\n  "repository": "howardweale/lightyear-carddemo-modernization",\r\n  "original_artifact": {\r\n    "id": 11991139660,\r\n    "node_id": "MDg6QXJ0aWZhY3QxMTk5MTEzOTY2MA==",\r\n    "name": "factory-review-records-POSTTRAN-0",\r\n    "size_in_bytes": 2175361,\r\n    "url": "https://api.github.com/repos/howardweale/lightyear-carddemo-modernization/actions/artifacts/11991139660",\r\n    "archive_download_url": "https://api.github.com/repos/howardweale/lightyear-carddemo-modernization/actions/artifacts/11991139660/zip",\r\n    "expired": false,\r\n    "digest": "sha256:24ea12fe7a16fea5bb06999e6a409e36cfc3fba59646701ebfd453ed3eff343c",\r\n    "created_at": "2026-10-15T16:55:08Z",\r\n    "updated_at": "2026-10-15T16:55:08Z",\r\n    "expires_at": "2026-10-29T16:55:07Z",\r\n    "workflow_run": {\r\n      "id": 38763552148,\r\n      "repository_id": 1329380897,\r\n      "head_repository_id": 1329380897,\r\n      "head_branch": "main",\r\n      "head_sha": "f343925026bee705ed3c16a734dc5bae4b24c588"\r\n    }\r\n  },\r\n  "archive_sha256": "24ea12fe7a16fea5bb06999e6a409e36cfc3fba59646701ebfd453ed3eff343c",\r\n  "size_in_bytes": 2175361,\r\n  "retrieved_at": "2026-10-29T18:02:21.305802+00:00",\r\n  "retrieval_origin": {\r\n    "kind": "resident local recovery copy",\r\n    "historical_metadata_sha256": "9ed3e4ee7dac0533ab727007f3ea597a0c91cea196ffc7f44b6ee5e6e47de748",\r\n    "github_original_current_status": "expired 410 in CI; metadata now404"\r\n  },\r\n  "metadata_capture": "historical retained API response",\r\n  "release": {\r\n    "tag": "artifact-preservation-11991139660",\r\n    "asset_name": "11991139660-original.zip",\r\n    "download_url": "https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/artifact-preservation-11991139660/11991139660-original.zip"\r\n  },\r\n  "public_content_review_sha256": "9946f6e65c8d84995ddfa9c12e5ab828e70751b752db2e1d77e4e45f7c8c65b9",\r\n  "original_metadata_sha256": "fb780891cacdaff500b3d498afc25feef4c0b43a7a402e1e7aa723ac9b5e671b",\r\n  "members": [\r\n    {\r\n      "name": "campaign-resources.json",\r\n      "bytes": 3276,\r\n      "sha256": "a9f1dd18913afd5c19cc3508f79c6e616e642e692b9400b13f2f1e3e50d6de89"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/resource-usage.json",\r\n      "bytes": 1013,\r\n      "sha256": "f23a204491880667ee73f561441ffb1be10c297b7d6224fd1133eece023c7709"\r\n    },\r\n    {\r\n      "name": "retention-preflight.json",\r\n      "bytes": 1536,\r\n      "sha256": "02179cd35632e727dfe612709d3dd25b00e14ac6cf6148e824aef2e7a74d7a9f"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/campaign-start.json",\r\n      "bytes": 45671,\r\n      "sha256": "4811242b2bfa8ef0520bc9e311280d96a9841854c01d865eee1e6a2b1fcbe299"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/campaign-manifest.json",\r\n      "bytes": 202826,\r\n      "sha256": "f7921a7ad666673a407b4e30d3309f28f1165ae2670e2bffe5cdffd94c7dc1fd"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/review-summary.json",\r\n      "bytes": 2533997,\r\n      "sha256": "a83fedd82fec28456f4b7422b3e38c30ea2b6b7d1787912f1bb87c60c5d41ee2"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/mutation-results.json",\r\n      "bytes": 11873268,\r\n      "sha256": "91d688ea2e71f3711b632f30cf1373320d6ab5d0d8e290f27b67b2062d311f2a"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/mutation-inventory.json",\r\n      "bytes": 176857,\r\n      "sha256": "12eb5e6c020734c9b6044a193b8e6099668296072cb350d647f67bca67aeeb88"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/systematic-scenario-selection.json",\r\n      "bytes": 23626,\r\n      "sha256": "68373895ce215d7a3aafea53134c90724be567bfcc1a608eae1653a98d40c294"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/generation-inventory.json",\r\n      "bytes": 189806,\r\n      "sha256": "a4c9a542c8c8812cea7142af03cf951606543f1e2cdb312a52353040d0512c82"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/fault-results.json",\r\n      "bytes": 742166,\r\n      "sha256": "0835685889c94269427510067485b36fe460b8b215f1a26bf56eecdf1ed8abd8"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/equivalence-followup/appl-result-census.json",\r\n      "bytes": 11631,\r\n      "sha256": "5260a41b68544ddf29f32639326a739f3325ee8d42c0b93fea132be1f94a4fff"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/equivalence-followup/resource-usage.json",\r\n      "bytes": 1747,\r\n      "sha256": "7b5c0855256abc85b2dfa83d35dd6bf89e83ceee16c18b332f8c99fe1eb4b27f"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/equivalence-followup/results.json",\r\n      "bytes": 91373,\r\n      "sha256": "863143ef9a24059f45a92be0578f14e977fd78771de8fb963fd1ac04a130bf00"\r\n    },\r\n    {\r\n      "name": "factory-review-POSTTRAN/equivalence-followup/shard.json",\r\n      "bytes": 15129735,\r\n      "sha256": "956d8fc6f1397984b445543f52bc5cfdab4cc356badf5b3ccb6c292b0d27483e"\r\n    }\r\n  ],\r\n  "unchanged": [\r\n    "original bytes",\r\n    "original pins",\r\n    "checks",\r\n    "workflows",\r\n    "POSTTRAN execution",\r\n    "gates",\r\n    "fence",\r\n    "approvals"\r\n  ]\r\n}\r\n'

class PreservedProjectionTests(unittest.TestCase):
    def test_fixture_matches_exact_committed_provenance(self):
        self.assertEqual(hashlib.sha256(PROVENANCE).hexdigest(), checker.POSTTRAN_PROVENANCE_SHA256)
        record = json.loads(PROVENANCE)
        self.assertEqual(record['original_artifact']['workflow_run']['head_sha'], checker.HEAD)
        self.assertEqual(record['archive_sha256'], '24ea12fe7a16fea5bb06999e6a409e36cfc3fba59646701ebfd453ed3eff343c')

    def test_wrong_size_is_refused(self):
        with self.assertRaisesRegex(ValueError, '^POSTTRAN-original-archive-size$'):
            checker._verify_preserved_posttran(b'wrong bytes', PROVENANCE)

    def test_wrong_bytes_at_original_size_are_refused(self):
        with self.assertRaisesRegex(ValueError, '^POSTTRAN-original-archive-hash$'):
            checker._verify_preserved_posttran(bytes(2175361), PROVENANCE)

    def test_wrong_original_provenance_is_refused(self):
        original = json.loads(PROVENANCE)
        for key, value in [
            ('id', 11991139661),
            ('name', 'different-artifact'),
            ('workflow_run', {'id': 38763552149, 'head_sha': checker.HEAD}),
            ('workflow_run', {'id': 38763552148, 'head_sha': '0' * 40}),
        ]:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(original)
                changed['original_artifact'][key] = value
                with self.assertRaisesRegex(ValueError, '^POSTTRAN-archived-provenance$'):
                    checker._verify_preserved_posttran(b'', json.dumps(changed).encode())

    def test_wrong_location_or_authority_is_refused(self):
        for key, value in [('release', {'download_url': 'https://example.invalid/wrong.zip'}),
                           ('execution_authorized', True), ('archive_sha256', '0' * 64)]:
            with self.subTest(key=key):
                changed = json.loads(PROVENANCE)
                changed[key] = value
                with self.assertRaisesRegex(ValueError, '^POSTTRAN-archived-provenance$'):
                    checker._verify_preserved_posttran(b'', json.dumps(changed).encode())

    def test_missing_archive_is_refused_without_live_artifact_fallback(self):
        calls = []
        def fetch(url, *, timeout):
            calls.append(url)
            if url == checker.POSTTRAN_PROVENANCE_URL:
                return io.BytesIO(PROVENANCE)
            raise HTTPError(url, 404, 'missing', {}, None)
        with patch.object(checker.urllib.request, 'urlopen', side_effect=fetch):
            with self.assertRaisesRegex(ValueError, '^POSTTRAN-preserved-copy-unavailable$'):
                checker._preserved_posttran_bytes()
        self.assertEqual(calls, [checker.POSTTRAN_PROVENANCE_URL, checker.POSTTRAN_ARCHIVE_URL])

    def test_missing_provenance_is_refused_before_archive_fetch(self):
        with patch.object(checker.urllib.request, 'urlopen',
                          side_effect=HTTPError(checker.POSTTRAN_PROVENANCE_URL, 404, 'missing', {}, None)) as fetch:
            with self.assertRaisesRegex(ValueError, '^POSTTRAN-preserved-copy-unavailable$'):
                checker._preserved_posttran_bytes()
        fetch.assert_called_once_with(checker.POSTTRAN_PROVENANCE_URL, timeout=120)
