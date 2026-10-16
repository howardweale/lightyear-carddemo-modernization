import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from tools.verify_public_retention import verify, REPOSITORY

class RetentionTests(unittest.TestCase):
    def test_future_manifest_and_failures(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); raw=b'public receipt'; release='evidence-2027-01-02-new-set'
            asset=dict(release=release,name='receipt.json',url=f'https://github.com/{REPOSITORY}/releases/download/{release}/receipt.json',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            manifest=dict(schema='public-evidence-retention/1',repository=REPOSITORY,scope='public CardDemo only',source_evidence_date='2027-01-02',assets=[asset])
            path=root/'manifest.json';path.write_text(json.dumps(manifest))
            self.assertTrue(verify(path,root/'out.json',open_url=lambda *a,**k:io.BytesIO(raw))['assets'][0]['verified'])
            with self.assertRaisesRegex(ValueError,'content'):
                verify(path,root/'out.json',open_url=lambda *a,**k:io.BytesIO(b'wrong'))
            def missing(*a,**k):raise FileNotFoundError('asset missing')
            with self.assertRaises(FileNotFoundError):verify(path,root/'out.json',open_url=missing)
            manifest['source_evidence_date']='2027-01-03';path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'url'):verify(path,root/'out.json',open_url=lambda *a,**k:io.BytesIO(raw))
