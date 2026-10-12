import tempfile
import unittest
from pathlib import Path
from tools.check_tower_manual import ROOT,check,vocabulary


class ManualTests(unittest.TestCase):
    def test_complete_closed_vocabulary(self):
        self.assertGreater(check()["kinds"],30)

    def test_new_route_kind_or_tab_requires_documentation(self):
        files=("src/lightyear_control_tower/server.py","src/lightyear_control_tower/kinds.py","src/lightyear_control_tower/carddemo_policy.py","knowledge/viewer/decision-console.html","docs/control-tower-users-manual.md")
        for relative,old,new in ((files[0],'"queue",','"new-undocumented-route", "queue",'),(files[1],'"scenario-threshold-approval":','"new-undocumented-kind":'),(files[3],'>Programs<','>New undocumented tab<')):
            with self.subTest(relative=relative),tempfile.TemporaryDirectory() as td:
                root=Path(td)
                for name in files:
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes((ROOT/name).read_bytes())
                path=root/relative;path.write_text(path.read_text(encoding="utf-8").replace(old,new),encoding="utf-8")
                with self.assertRaisesRegex(ValueError,"manual missing"):check(root)
