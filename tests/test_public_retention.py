import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from copy import deepcopy
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

    def test_archive_inventory_checks_every_member_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); stream=io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                archive.writestr('receipt.json', b'public receipt')
            raw=stream.getvalue(); tag='evidence-2026-10-18-intcalc'
            asset=dict(release=tag,name='receipt.zip',url=f'https://github.com/{REPOSITORY}/releases/download/{tag}/receipt.zip',
                bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
                files=[dict(path='receipt.json',bytes=14,sha256=hashlib.sha256(b'public receipt').hexdigest())])
            manifest=dict(schema='public-evidence-retention/1',repository=REPOSITORY,scope='public CardDemo only',
                source_evidence_date='2026-10-18',assets=[asset])
            path=root/'manifest.json'
            def run(value):
                path.write_text(json.dumps(value))
                return verify(path,root/'result.json',open_url=lambda *a,**k:io.BytesIO(raw))
            self.assertTrue(run(manifest)['assets'][0]['verified'])
            for alteration in ['hash','size','missing','extra','duplicate']:
                changed=deepcopy(manifest); rows=changed['assets'][0]['files']
                if alteration=='hash': rows[0]['sha256']='0'*64
                if alteration=='size': rows[0]['bytes']+=1
                if alteration=='missing': rows.clear()
                if alteration=='extra': rows.append(dict(rows[0],path='unlisted.json'))
                if alteration=='duplicate': rows.append(dict(rows[0]))
                with self.subTest(alteration=alteration),self.assertRaisesRegex(ValueError,'public-retention-file'):
                    run(changed)
