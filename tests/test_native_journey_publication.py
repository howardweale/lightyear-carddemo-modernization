"""Exported journals preserve the same signature, scope and chain boundaries."""
import copy
from pathlib import Path
import tempfile
import unittest

from lightyear_calibration.contracts import seal
from lightyear_calibration.journey_order import save
from lightyear_calibration.journey_runtime import JourneySigner
from lightyear_workflow.campaign_journals import signed_append
from lightyear_workflow.run_store import RunStore
from tools.publish_native_journeys import safe_relative, verify_run_identity, matches_implementation, encode_blob, decode_blob, split_json_observation


class PublicationTests(unittest.TestCase):
    def test_json_components_restore_original_order_bytes_and_hash(self):
        import hashlib
        import json
        values=[{'artifact_type':'lightyear-native-state-observation','observed_at':'observed',
                 'tables':{'z':{'rows':1,'row_multiset':{'f'*64:1},'raw_file':'z.gz'},'a':{'rows':1,'row_multiset':{'f'*64:1},'raw_file':'a.gz'}},
                 'structure':{'columns':[{'name':'caf\u00e9','precision':2.5}]}},
                {'evidence_class':'native-catalog-observation','results':{'columns':[{'name':'x'}]},'observed_at':'another'}]
        for value in values:
            blobs={}
            def put(data):
                digest=hashlib.sha256(data).hexdigest();blobs[digest]=data;return digest
            original=json.dumps(value,separators=(',',':')).encode()
            stored,encoding=split_json_observation(original,put)
            entry={'sha256':hashlib.sha256(original).hexdigest(),'blob_sha256':hashlib.sha256(stored).hexdigest(),'bytes':len(original),**encoding}
            self.assertEqual(original,decode_blob(stored,entry,blobs.__getitem__))
            with self.assertRaises(ValueError):decode_blob(stored,entry,lambda _:b'{}')

    def test_gzip_timestamp_deduplication_restores_every_original_byte(self):
        import gzip
        import hashlib
        import io
        stored=[]
        for stamp in (123,456):
            buffer=io.BytesIO()
            with gzip.GzipFile(filename='native.rows.jsonl',mode='wb',fileobj=buffer,mtime=stamp) as stream:stream.write(b'{"native":"row"}\n')
            original=buffer.getvalue();blob,encoding=encode_blob(original);stored.append(blob)
            entry={'sha256':hashlib.sha256(original).hexdigest(),'blob_sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(original),**encoding}
            self.assertEqual(original,decode_blob(blob,entry))
            with self.assertRaises(ValueError):decode_blob(blob+b'changed',entry)
        self.assertEqual(stored[0],stored[1])

    def test_only_checkout_line_endings_may_differ_for_python_implementation(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'gate.py';path.write_bytes(b'verdict = False\n')
            expected=hashlib.sha256(b'verdict = False\r\n').hexdigest()
            self.assertTrue(matches_implementation(path,expected))
            path.write_bytes(b'verdict = True\n')
            self.assertFalse(matches_implementation(path,expected))

    def test_archive_paths_cannot_escape_or_alias(self):
        for value in ('../outside','/absolute','a/../b','a\\b','C:/x','a//b','a/./b'):
            with self.subTest(value=value), self.assertRaises(ValueError):safe_relative(value)
        self.assertEqual('safe/path.json',str(safe_relative('safe/path.json')))

    def test_exported_terminal_and_outer_chain_are_both_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);signer=JourneySigner(root);run=root/'journey-test';run.mkdir()
            plan=seal({'mode':'replay'});save(run/'plan.json',plan)
            auth=signer.sign({'run_id':run.name,'plan':{'plan_sha256':plan['content_sha256']}})
            receipt=signer.sign({'run_id':run.name,'plan_sha256':plan['content_sha256'],'status':'failed'})
            save(run/'authorization.json',auth);save(run/'receipt.json',receipt)
            (run/'authority.public.pem').write_bytes(signer.public)
            store=RunStore(run/'journal')
            try:
                signed_append(store,signer,auth,'started',{},'journey')
                signed_append(store,signer,auth,'halted',{k:v for k,v in receipt.items() if k not in ('signature','content_sha256')},'journey')
                events=store.events()
            finally:store.close()
            save(run/'journal.json',events)
            self.assertEqual('failed',verify_run_identity(run,signer.public)['status'])
            tampered=copy.deepcopy(events);tampered[0]['at']='edited'
            save(run/'journal.json',tampered)
            with self.assertRaises(ValueError):verify_run_identity(run,signer.public)
            save(run/'journal.json',events)
            altered=signer.sign({**{k:v for k,v in receipt.items() if k not in ('signature','content_sha256')},'status':'passed'})
            save(run/'receipt.json',altered)
            with self.assertRaises(ValueError):verify_run_identity(run,signer.public)


if __name__=='__main__':unittest.main()
