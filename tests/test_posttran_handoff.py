import json
from pathlib import Path
from datetime import datetime, timezone
import shutil
import tempfile
import unittest
from tools.check_posttran_handoff import check, timing, READINESS
ROOT=Path(__file__).resolve().parents[1]
class HandoffTests(unittest.TestCase):
    def test_actual_committed_handoff(self):
        value=check(ROOT)
        self.assertFalse(value['signed']);self.assertFalse(value['effective'])
    def test_tampered_links_refuse(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'docs/factory').mkdir(parents=True)
            for p in (ROOT/'docs/factory').glob('posttran-phase2-*.json'):shutil.copyfile(p,root/'docs/factory'/p.name)
            path=root/READINESS;original=json.loads(path.read_bytes())
            for field,value in [('plan_sha256','0'*64),('executable_commit','0'*40),('artifact_id',1)]:
                changed=dict(original);changed[field]=value;path.write_text(json.dumps(changed))
                with self.subTest(field=field),self.assertRaises(ValueError):check(root)
    def test_warning_begins_exactly_five_days_before_signing_deadline(self):
        ready=dict(signing_deadline='2026-10-29T14:46:00+00:00')
        self.assertFalse(timing(ready,datetime(2026,10,24,14,45,59,tzinfo=timezone.utc))['warning'])
        self.assertTrue(timing(ready,datetime(2026,10,24,14,46,tzinfo=timezone.utc))['warning'])
