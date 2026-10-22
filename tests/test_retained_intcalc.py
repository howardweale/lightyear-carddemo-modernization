"""CI-only synthetic refusal checks and actual public consumer binding."""
from copy import deepcopy
from hashlib import sha256
import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from tools import retained_intcalc as retained

class RetainedIntcalcTests(unittest.TestCase):
    def fixture(self,root):
        original='docs/factory/evidence-retention-2026-10-18-intcalc.json'
        target=root/original;target.parent.mkdir(parents=True);target.write_bytes(b'{}')
        oh=sha256(b'{}').hexdigest();index_path='docs/factory/release-evidence-2026-10-18/index.json'
        index=dict(head='a'*40,run_id=9,external_archive=dict(manifest_sha256=oh),sources=[dict(head='a'*40,run_id=9,files={original:oh})])
        ib=json.dumps(index).encode();rp='docs/factory/intcalc-releasability-2026-10-18.json'
        report=dict(schema='intcalc-releasability/3',prepared_on='2026-10-18',head='a'*40,run_id=9,release_authorized=False,evidence_index=dict(path=index_path,sha256=sha256(ib).hexdigest()))
        files={index_path:ib,rp:json.dumps(report).encode()};stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for n,b in files.items():z.writestr(n,b)
        raw=stream.getvalue();base='https://github.com/'+retained.REPOSITORY+'/releases/download/intcalc-verdict-run11-attempt1/'
        m=dict(schema=retained.SCHEMA,repository=retained.REPOSITORY,prepared_on='2026-10-18',source=dict(head='b'*40,run_id=11,run_attempt=1,artifact_id=12,artifact_name='intcalc-current-verdict'),archive=dict(url=base+'intcalc-current-verdict.zip',bytes=len(raw),sha256=sha256(raw).hexdigest()),files=[dict(path=n,bytes=len(b),sha256=sha256(b).hexdigest()) for n,b in files.items()],report=rp,index=index_path,measurement=dict(head='a'*40,run_id=9),release_authorized=False,original_manifest=dict(path=original,sha256=oh),verdict_url=base+'intcalc-releasability-2026-10-18.md',packet_url=base+'howard-decision-packet-2026-10-18-handoff-refresh.md')
        return m,raw

    def test_reads_without_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m,raw=self.fixture(root);before=sorted(str(p) for p in root.rglob('*'))
            value=retained.read(root,m,fetch=lambda *args:raw)
            self.assertEqual('a'*40,value['release']['head']);self.assertEqual(9,value['release']['run_id'])
            self.assertFalse(value['release']['release_authorized']);self.assertEqual(before,sorted(str(p) for p in root.rglob('*')))
            self.assertEqual([m['original_manifest']['path']],value['local_inputs'])

    def test_archive_tamper_missing_download_and_origin_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m,raw=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'archive-hash'):retained.read(root,m,fetch=lambda *args:raw+b'x')
            with self.assertRaises(OSError):retained.read(root,m,fetch=lambda *args:(_ for _ in ()).throw(OSError('unavailable')))
            for url in ('http://github.com/x','https://example.com/x',m['archive']['url']+'?token=x'):
                changed=deepcopy(m);changed['archive']['url']=url
                with self.subTest(url=url),self.assertRaisesRegex(ValueError,'url'):
                    retained.read(root,changed,fetch=lambda *args:self.fail('download must not occur'))

    def test_inventory_hash_source_and_authority_substitution_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);m,raw=self.fixture(root)
            for mutation in ('missing','duplicate','size','hash','measurement','authority','source','path','backslash'):
                changed=deepcopy(m)
                if mutation=='missing':changed['files'].pop()
                if mutation=='duplicate':changed['files'].append(changed['files'][0])
                if mutation=='size':changed['files'][0]['bytes']+=1
                if mutation=='hash':changed['files'][0]['sha256']='0'*64
                if mutation=='measurement':changed['measurement']['run_id']=10
                if mutation=='authority':changed['release_authorized']=True
                if mutation=='source':changed['source']['run_id']=13
                if mutation=='path':changed['files'][0]['path']='../outside'
                if mutation=='backslash':changed['files'][0]['path']='folder'+chr(92)+'outside'
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):retained.read(root,changed,fetch=lambda *args:raw)
            (root/m['original_manifest']['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'original-hash'):retained.read(root,m,fetch=lambda *args:raw)

    def test_actual_status_packet_and_input_binding(self):
        from tools.release_status_records import ROOT,inputs,load,render
        from tools.build_release_packet import build
        model=load();publication=model['retained_publication'];self.assertIsNotNone(publication)
        self.assertEqual(39685093189,publication['source']['run_id']);self.assertEqual('311/424',model['release']['raw_kill_rate'])
        self.assertFalse(model['release']['release_authorized']);self.assertEqual('unknown',model['release']['ordered_decisions']['state'])
        self.assertNotIn('INTCALC',model['projections']);value,text=render(model)
        self.assertIn('intcalc-releasability-2026-10-21.md',text);self.assertIn(publication['packet_url'],text)
        self.assertIn('docs/factory/intcalc-releasability-2026-10-21.json',inputs())
        self.assertTrue(all((ROOT/name).is_file() for name in inputs()));self.assertNotIn('docs/factory/current-status.json',inputs())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'docs/factory').mkdir(parents=True)
            with patch('tools.build_release_packet.load',return_value=model):packet=build(root=root)
            text=next((root/'docs/factory').glob('howard-decision-packet-*.md')).read_text()
            self.assertEqual(value['release_evidence_sha256'],packet['release_evidence_sha256']);self.assertIn('intcalc-releasability-2026-10-21.md',text)
            self.assertFalse(packet['release_authorized'])
