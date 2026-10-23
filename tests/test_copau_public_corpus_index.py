"""Public collector fixtures: mock metadata and synthetic bytes only."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import copau_public_corpus_index as collector
from tools import copau_private_prerequisites as custody


class PublicCorpusIndexTests(unittest.TestCase):
    def test_pagination_complete_and_changed_total_refused(self):
        first = dict(total_count=101, artifacts=[dict(id=i) for i in range(100)])
        second = dict(total_count=101, artifacts=[dict(id=100)])
        with patch.object(collector, 'github', side_effect=[first, second]) as api:
            self.assertEqual(len(collector.pages('actions/artifacts', 'artifacts')), 101)
            self.assertEqual(api.call_count, 2)
        with patch.object(collector, 'github', side_effect=[first, dict(second, total_count=102)]):
            with self.assertRaises(custody.Refused):collector.pages('actions/artifacts', 'artifacts')

    def test_download_digest_missing_expired_and_private_draft(self):
        raw = b'synthetic-public-artifact'
        artifacts = [dict(id=1, digest='sha256:'+collector.sha(raw), size_in_bytes=len(raw), expired=False),
                     dict(id=2, digest='sha256:'+'0'*64, size_in_bytes=10, expired=True),
                     dict(id=3, digest=None, size_in_bytes=10, expired=False)]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / 'public'
            with patch.object(collector, 'pages', side_effect=[artifacts, [dict(id=9, draft=True)]]), \
                    patch.object(collector, 'github', return_value=raw) as api:
                index, missing = collector.collect_public(root)
            self.assertEqual(len(index['files']), 1)
            self.assertFalse(index['inventory_complete'])
            self.assertEqual({r['id'] for r in missing}, {2, 3})
            self.assertEqual(api.call_count, 1)
            self.assertEqual((root / 'artifact-1.bin').read_bytes(), raw)
            with self.assertRaises(custody.Refused):collector.collect_public(root)

    def test_wrong_bytes_refused_not_written(self):
        artifacts = [dict(id=1, digest='sha256:'+'0'*64, size_in_bytes=5, expired=False)]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / 'public'
            with patch.object(collector, 'pages', side_effect=[artifacts, []]), \
                    patch.object(collector, 'github', return_value=b'wrong'):
                index, missing = collector.collect_public(root)
            self.assertFalse(index['files']); self.assertEqual(len(missing), 1)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
