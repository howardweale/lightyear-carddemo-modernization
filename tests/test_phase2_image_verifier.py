"""Exercise the actual image verifier with in-memory GitHub responses only."""
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from types import SimpleNamespace
import unittest
import zipfile
from tools.posttran_phase2_authorization import verify_image


class ImagePreflightTests(unittest.TestCase):
    def fixture(self,mode='good'):
        tar=b'bounded compiler image fixture bytes'
        plan=dict(preparation_run=123,compiler_image_artifact='image',twin={'image_archive_sha256':sha256(tar).hexdigest()})
        artifact=dict(id=456,name='image',expired=False,expires_at='2026-10-30T14:46:00Z')
        listing=dict(total_count=1,artifacts=[artifact])
        if mode=='duplicate-name':listing.update(total_count=2,artifacts=[artifact,dict(artifact,id=457)])
        if mode=='incomplete-page':listing['total_count']=101
        payload=io.BytesIO()
        with zipfile.ZipFile(payload,'w') as archive:
            archive.writestr('wrong-name' if mode=='missing-member' else 'compiler-image.tar',b'changed' if mode=='changed-tar' else tar)
        calls=[]
        def run(command,**kwargs):
            calls.append(command)
            self.assertTrue(kwargs['check'])
            if command[-1].endswith('/artifacts?per_page=100'):
                return SimpleNamespace(stdout=json.dumps(listing).encode(),returncode=0)
            self.assertEqual('repos/fixture/repo/actions/artifacts/456/zip',command[-1])
            kwargs['stdout'].write(payload.getvalue())
            return SimpleNamespace(returncode=0)
        return plan,run,calls

    def test_actual_verifier_accepts_complete_matching_zip(self):
        plan,run,calls=self.fixture()
        result=verify_image(plan,'fixture/repo',now=datetime(2026,10,17,tzinfo=timezone.utc),run=run)
        self.assertTrue(result['verified_before_reservation'])
        self.assertEqual(plan['twin']['image_archive_sha256'],result['image_archive_sha256'])
        self.assertEqual(2,len(calls))

    def test_actual_verifier_refuses_changed_missing_ambiguous_or_incomplete_input(self):
        modes={'changed-tar':'phase2-image-archive-changed','missing-member':'phase2-image-archive-member',
               'duplicate-name':'phase2-image-artifact-missing-or-ambiguous','incomplete-page':'phase2-artifact-list-incomplete'}
        for mode,reason in modes.items():
            plan,run,calls=self.fixture(mode)
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,reason):
                verify_image(plan,'fixture/repo',now=datetime(2026,10,17,tzinfo=timezone.utc),run=run)
            self.assertEqual(1 if mode in ('duplicate-name','incomplete-page') else 2,len(calls))
