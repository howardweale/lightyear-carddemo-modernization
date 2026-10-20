"""CI-only lifecycle fixtures; no real tags, issues, signatures or execution."""
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from tools.check_posttran_plan_artifact import verify
from tools.check_posttran_deadline import evaluate, issue_body, upsert_issue, consumed, MARKER, main
from tools.check_posttran_runbook_constants import verify as verify_constants

ROOT=Path(__file__).resolve().parents[1]
UTC=timezone.utc


class LifecycleTests(unittest.TestCase):
    def test_live_plan_and_expired_retained_plan(self):
        amendment=json.loads((ROOT/'docs/factory/posttran-phase2-plan-amendment-2026-10-17.json').read_bytes())
        metadata=json.loads((ROOT/'docs/factory/posttran-phase2-artifact-metadata-2026-10-16.json').read_bytes())
        row=next(r for r in metadata['artifacts'] if r['id']==amendment['artifact_id'])
        package=io.BytesIO()
        with zipfile.ZipFile(package,'w') as archive:
            archive.writestr('posttran-phase2-plan-2026-10-16.json',(ROOT/amendment['original_path']).read_bytes())
        calls=[]
        def run(args):
            calls.append(args)
            return package.getvalue() if args[-1].endswith('/zip') else json.dumps(row).encode()
        live=verify(ROOT,now=datetime(2026,10,29,tzinfo=UTC),repository='fixture/repo',run=run)
        self.assertEqual('live-ci-artifact',live['verification_path'])
        self.assertIn('repos/fixture/repo/',calls[0][-1])
        calls.clear()
        expired=verify(ROOT,now=datetime(2026,10,30,14,46,14,tzinfo=UTC),repository='fixture/repo',run=run)
        self.assertEqual('committed-original-and-amendment',expired['verification_path']);self.assertEqual([],calls)
        self.assertNotEqual(live,expired)

    def test_expired_fallback_still_checks_original_bytes(self):
        names=['posttran-phase2-plan-amendment-2026-10-17.json','posttran-phase2-artifact-metadata-2026-10-16.json',
               'posttran-phase2-original-ci-plan-2026-10-17.json','posttran-phase2-plan-2026-10-16.json']
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'docs/factory').mkdir(parents=True)
            for name in names:(root/'docs/factory'/name).write_bytes((ROOT/'docs/factory'/name).read_bytes())
            (root/'docs/factory'/names[2]).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'amendment-file-binding'):
                verify(root,now=datetime(2026,11,1,tzinfo=UTC),repository='fixture/repo',run=lambda *a:self.fail('network fallback'))

    def test_terminal_states_and_text_are_derived(self):
        ready,warning=evaluate(ROOT,datetime(2026,10,25,tzinfo=UTC))
        _,expired=evaluate(ROOT,datetime(2026,10,30,tzinfo=UTC))
        _,used=evaluate(ROOT,datetime(2026,10,25,tzinfo=UTC),was_consumed=True)
        with patch('tools.check_posttran_deadline.withdrawn',return_value=True):
            _,superseded=evaluate(ROOT,datetime(2026,10,25,tzinfo=UTC))
        self.assertEqual(['warning','expired','consumed','superseded'],[x['state'] for x in [warning,expired,used,superseded]])
        self.assertEqual(4,len({issue_body(ready,x) for x in [warning,expired,used,superseded]}))
        self.assertIn('fresh preparation required',issue_body(ready,expired))
        self.assertEqual(0,main(['--root',str(ROOT)],now=datetime(2026,10,30,tzinfo=UTC)))
        with patch('tools.check_posttran_deadline.consumed',return_value=True),patch('tools.check_posttran_deadline.upsert_issue') as update:
            self.assertEqual(0,main(['--root',str(ROOT),'--issue-repository','fixture/repo'],now=datetime(2026,10,25,tzinfo=UTC)))
            self.assertTrue(update.call_args.kwargs['terminal'])

    def test_consumption_lookup_is_exact_and_read_only(self):
        plan='a'*64
        def run(args):
            self.assertNotIn('--method',args)
            return json.dumps([{'ref':'refs/tags/posttran-phase2-consumed-'+plan}]).encode()
        self.assertTrue(consumed('fixture/repo',plan,run=run))
        self.assertFalse(consumed('fixture/repo','b'*64,run=run))

    def test_expiry_issue_is_recorded_and_closed_once(self):
        ready,value=evaluate(ROOT,datetime(2026,10,30,tzinfo=UTC));body=issue_body(ready,value);stored=[];writes=[]
        def run(args,**kwargs):
            if '--method' not in args:return json.dumps(stored).encode()
            payload=json.loads(kwargs['input']);writes.append(payload)
            if not stored:stored.append(dict(number=42,body=body,state='open'))
            else:stored[0].update(payload)
            return json.dumps(stored[0]).encode()
        upsert_issue('fixture/repo',body,run=run,terminal=True)
        self.assertEqual('closed',stored[0]['state']);self.assertEqual(2,len(writes))
        upsert_issue('fixture/repo',body,run=run,terminal=True);self.assertEqual(2,len(writes))

    def test_readiness_withdrawal_requires_exact_hash_and_later_date(self):
        from tools.check_posttran_deadline import withdrawn
        ready=json.loads((ROOT/'docs/factory/posttran-phase2-readiness-2026-10-17.json').read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'docs/factory').mkdir(parents=True)
            raw=(ROOT/'docs/factory/posttran-phase2-readiness-2026-10-17.json').read_bytes()
            (root/'docs/factory/posttran-phase2-readiness-2026-10-17.json').write_bytes(raw)
            path=root/'docs/factory/posttran-phase2-readiness-supersession-2026-10-18.json'
            record=dict(schema='posttran-readiness-supersession/1',prepared_on='2026-10-18',supersedes_sha256='0'*64,withdrawn=True)
            path.write_text(json.dumps(record));self.assertFalse(withdrawn(root,ready))
            record['supersedes_sha256']=sha256(raw).hexdigest();path.write_text(json.dumps(record));self.assertTrue(withdrawn(root,ready))

    def test_every_documented_constant_matches_and_tampering_fails(self):
        expected=verify_constants(ROOT);text=(ROOT/'docs/factory/posttran-phase2-runbook.md').read_text(encoding='utf-8')
        for name,value in expected.items():
            changed=text.replace("$"+name+" = '"+value+"'","$"+name+" = '"+'0'*len(value)+"'",1)
            self.assertNotEqual(text,changed)
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'runbook-constant'):
                verify_constants(ROOT,changed)
