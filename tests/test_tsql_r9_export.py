"""Synthetic CI-only export fixtures; no VM, cloud, database or model access."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from tools import export_tsql_r9 as export


class R9ExportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.run=self.root/'run';self.run.mkdir()
        # Public synthetic key only: random base64 signatures can resemble a
        # credential marker. Real signature verification and scanning stay on.
        self.key=Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.files={}
        self.store('evidence-public-key.bin',self.public)
        self.store('plan.json',self.signed(dict(comparison_revision=9)))
        self.store('coverage-control-evidence/control.json',b'{"fixture":true}')
        records=[]
        for i in range(1,109):
            name=f'pair-{i:03d}-fixture-correct-1'
            pair=self.signed(dict(schema='tsql-native-pair/1',index=i))
            self.store(name+'/manifest.json',pair)
            for file in ('source.json','target.json','comparison.json'):
                self.store(name+'/'+file,b'{"fixture":true}')
            records.append(dict(index=i,id='fixture',variant='correct',repeat=1,
                status='match-on-compared-observables',manifest_sha256=json.loads(pair)['content_sha256']))
        self.body=dict(schema='tsql-native-run-report/1',model_calls=0,qualification_passed=True,
            files=self.files,records=records)
        self.reseal()

    def signed(self,body):
        raw=export.canonical(body)
        return export.canonical(dict(body,content_sha256=export.sha(raw),signature=base64.b64encode(self.key.sign(raw)).decode()))

    def store(self,name,raw):
        path=self.run/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        self.files[name]=export.sha(raw)

    def reseal(self):
        raw=self.signed(self.body);(self.run/'report.json').write_bytes(raw)
        self.expected=json.loads(raw)['content_sha256']

    def guard(self):
        return patch.multiple(export,REPORT=self.expected,KEY=export.sha(self.public),FILES=len(self.files))

    def test_exact_closure_package_hashes_and_siblings_excluded(self):
        sibling=self.root/'credential-sibling';sibling.mkdir();(sibling/'private.pem').write_text('PRIVATE')
        with self.guard():
            self.assertEqual(self.run.resolve(strict=True),export.locate(self.root))
            review=export.inspect(self.run);out=self.root/'out';out.mkdir()
            (out/'inspection.json').write_bytes(export.canonical(review))
            export.package(self.run,out,review['identifiers_sha256'])
            manifest=json.loads((out/'export-manifest.json').read_bytes())
            package=out/export.PACKAGE
            self.assertEqual(export.sha(package.read_bytes()),manifest['package_sha256'])
            with zipfile.ZipFile(package) as archive:
                self.assertEqual({'revision-9/'+p for p in self.files}|{'revision-9/report.json'},set(archive.namelist()))
            with self.assertRaises(FileExistsError):export.package(self.run,out,review['identifiers_sha256'])

    def test_wrong_report_key_count_modified_and_extra_files_refuse(self):
        with self.guard():
            with patch.object(export,'REPORT','0'*64),self.assertRaises(ValueError):export.inspect(self.run)
            with patch.object(export,'KEY','0'*64),self.assertRaises(ValueError):export.inspect(self.run)
            with patch.object(export,'FILES',len(self.files)-1),self.assertRaises(ValueError):export.inspect(self.run)
            path=self.run/'coverage-control-evidence/control.json';before=path.read_bytes();path.write_bytes(before+b' ')
            with self.assertRaisesRegex(ValueError,'signed-file-hash'):export.inspect(self.run)
            path.write_bytes(before);extra=self.run/'extra.txt';extra.write_text('extra')
            with self.assertRaisesRegex(ValueError,'run-file-closure'):export.inspect(self.run)

    def test_markers_credentials_and_encoded_secrets_refuse_without_value_logging(self):
        values=[{'password':'fixture-secret'},{'access_token':'fixture-secret'},
                {'accessToken':'fixture-secret'},{'apiKey':'fixture-secret'},
                {'note':'-----BEGIN OPENSSH PRIVATE KEY-----'},
                {'note':'https://user:fixture-secret@example.test'},
                {'note':base64.b64encode(b'{"token":"fixture-secret"}').decode()},
                {'note':b'{"credential":"fixture-secret"}'.hex()}]
        for value in values:
            with self.subTest(value=list(value)),self.assertRaises(ValueError) as failure:
                export.scan(value,'fixture.json',set())
            self.assertNotIn('fixture-secret',str(failure.exception))
        export.scan({'tds_tokens':[{'token':171,'flags':16}]},'fixture.json',set())
        for name in ('../outside','a/../b','/absolute','a\\b','private-key.pem','.ssh/id_ed25519'):
            with self.assertRaises(ValueError):export.relative(name)

    def test_identifiers_require_exact_review_hash_and_changed_inventory_refuses(self):
        self.store('host.json',b'{"hostname":"vm.example.internal","project_id":"review-project"}')
        self.reseal()
        with self.guard():
            review=export.inspect(self.run)
            self.assertTrue(any(x['value']=='review-project' for x in review['identifiers']))
            out=self.root/'out';out.mkdir();(out/'inspection.json').write_bytes(export.canonical(review))
            with self.assertRaisesRegex(ValueError,'reviewed-inspection-changed'):export.package(self.run,out,'0'*64)
            self.assertFalse((out/export.PACKAGE).exists())
            changed=copy.deepcopy(review);changed['total_bytes']+=1
            (out/'inspection.json').write_bytes(export.canonical(changed))
            with self.assertRaisesRegex(ValueError,'reviewed-inspection-changed'):
                export.package(self.run,out,review['identifiers_sha256'])

    def test_signed_inventory_with_secret_or_unknown_binary_cannot_be_packaged(self):
        for raw in (b'{"password":"fixture-secret"}', b'\xff\xfe\x80\x00'):
            name='unreviewed.txt';self.store(name,raw);self.reseal()
            with self.guard(),self.assertRaises(ValueError):export.inspect(self.run)
            self.assertFalse(any(self.root.rglob('*.zip')))
        del self.files[name];(self.run/name).unlink();self.reseal()
        self.body['records']=self.body['records'][:-1];self.reseal()
        with self.guard(),self.assertRaisesRegex(ValueError,'108-pair-count'):export.inspect(self.run)

    def test_duplicate_revision9_runs_and_symlinks_refuse(self):
        with self.guard():
            duplicate=self.root/'second';duplicate.mkdir()
            (duplicate/'report.json').write_bytes((self.run/'report.json').read_bytes())
            with self.assertRaisesRegex(ValueError,'exactly-one'):export.locate(self.root)
            link=self.run/'link'
            try:link.symlink_to(self.root,target_is_directory=True)
            except OSError:return  # Windows may prohibit link creation; Linux exercises it.
            with self.assertRaisesRegex(ValueError,'linked-evidence-directory'):export.inspect(self.run)

    def test_fixed_public_fixture_signatures_are_scanned_and_verified(self):
        for name in ('plan.json', 'report.json', *(
                f'pair-{i:03d}-fixture-correct-1/manifest.json' for i in range(1, 109))):
            value = json.loads((self.run / name).read_bytes())
            with self.subTest(path=name):
                self.assertIsNone(export.SECRET_TEXT.search(value['signature']))
                export.scan(value, name, set())
                export.envelope(value, self.public)
        with self.guard():
            self.assertEqual(108, export.inspect(self.run)['native_pairs'])

    def test_credential_shaped_signature_still_refuses(self):
        # Deliberately synthetic, not a credential: preserve the exact refusal
        # that exposed the random-fixture collision, even in a signature field.
        value = {'signature': 'AKIA' + 'A' * 16}
        with self.assertRaisesRegex(ValueError, 'secret-marker:fixture.json'):
            export.scan(value, 'fixture.json', set())
