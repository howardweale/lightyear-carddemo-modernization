import copy
import subprocess
import json
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.factory_evidence import FactoryEvidence, INDEX
from lightyear_control_tower.presentation import FACTORY_FILES

ROOT=Path(__file__).resolve().parents[1]


def fixture_snapshot(root):
    rows=[]
    for name in FACTORY_FILES:
        relative="docs/factory/"+name
        raw=(ROOT/relative).read_bytes()
        destination=Path(root)/relative
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
        rows.append(dict(path=relative,sha256=sha256(raw).hexdigest()))
    index=dict(schema="factory-evidence-index/1",commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),created_at="2026-10-12T04:10:00Z",sources=rows)
    path=Path(root)/INDEX;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(canonical(index))
    return sha256(canonical(index)).hexdigest()


class FactoryViewsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.pin=fixture_snapshot(self.root)
        self.evidence=FactoryEvidence(self.root,self.pin)

    def test_every_program_figure_uses_bound_artifacts_and_recomputes(self):
        for program in ("INTCALC","POSTTRAN"):
            view=self.evidence.program(program)
            fresh=self.evidence.read("tower-run-38198096890/"+program+"/fresh.json")
            mutation=view["mutation"]["value"]
            self.assertEqual(mutation["raw_counts"],fresh["mutation_counts"])
            self.assertEqual(view["observed_head"],fresh["campaign_head"])
            self.assertFalse(view["releasable"])
            killed=fresh["mutation_counts"]["killed-failure"]+fresh["mutation_counts"]["killed-divergent"]
            self.assertEqual(mutation["raw_kill_fraction"],f"{killed}/{sum(fresh['mutation_counts'].values())}")
            for scope,row in mutation["scoped_assessments"].items():
                expected="met" if Fraction(killed,row["mutation"]["eligible"])>=Fraction(9,10) else "failed"
                self.assertEqual(expected,next(c["state"] for c in view["checklist"] if c["criterion"]=="Mutation rate ("+scope+")"))
            for name in ("mutation","scenarios","answer_key","keep_or_fix"):
                self.assertTrue(view[name]["sources"])
                for source in view[name]["sources"]:
                    self.assertEqual(source["sha256"],sha256((self.root/source["path"]).read_bytes()).hexdigest())
            self.assertEqual("pending",view["checklist"][-1]["state"])
            self.assertEqual("failed",next(c["state"] for c in view["checklist"] if c["criterion"]=="Output diversity"))

    def test_tampered_source_and_index_refused(self):
        path=self.root/"docs/factory/tower-run-38198096890/POSTTRAN/fresh.json"
        value=json.loads(path.read_bytes());value["kill_rate"]="483/483";path.write_bytes(canonical(value))
        with self.assertRaisesRegex(ValueError,"evidence-hash"):self.evidence.program("POSTTRAN")
        with self.assertRaisesRegex(ValueError,"index-hash"):FactoryEvidence(self.root,"f"*64)

    def test_unlisted_path_and_program_refused(self):
        with self.assertRaises(ValueError):self.evidence.program("../authority")
        path=self.root/INDEX;v=json.loads(path.read_bytes());v["sources"][0]["path"]="docs/factory/unknown.json"
        path.write_bytes(canonical(v))
        with self.assertRaisesRegex(ValueError,"adapter-not-allowed"):FactoryEvidence(self.root,sha256(path.read_bytes()).hexdigest())

    def test_other_scopes_return_unavailable(self):
        from unittest.mock import Mock
        from lightyear_control_tower.server import ConsoleAPI
        for scope in ("ms94-b06","carddemo-zos"):
            service=Mock(scope=scope)
            api=object.__new__(ConsoleAPI);api.service=service
            for route in ("programs","program"):
                self.assertFalse(api.read(route,"fixture",{"id":"INTCALC"})["available"])


if __name__=="__main__":unittest.main()
