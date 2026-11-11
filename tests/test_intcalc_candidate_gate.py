"""CI-only binding checks. Case definitions and answers are external verifier assets."""
import copy
import io
import tarfile
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from lightyear_mainframe import intcalc_candidate_gate as gate


class CandidateGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        frozen = Path(os.environ["C1_FROZEN"])
        shutil.copytree(frozen, self.root/"frozen")
        artifact = self.root/"fixture.jar"
        artifact.write_bytes(b"mock-public-artifact-not-runnable")
        self.binding = dict(schema="full-intcalc-c1/2",upstream=gate.UPSTREAM,
            case_manifest=dict(path="frozen/case-manifest.json",sha256=gate.digest((self.root/"frozen/case-manifest.json").read_bytes())),
            artifact=dict(path="fixture.jar",sha256=gate.digest(artifact.read_bytes())),
            runtime_image="sha256:"+"1"*64,java="/opt/java/openjdk/bin/java",
            command_template=gate.COMMAND,max_elapsed_seconds=300,qualified=False,
            production_controller_receipt=False)
        self.path=self.root/"binding.json"
        self.path.write_text(json.dumps(self.binding)+"\n")

    def validate(self,binding=None):
        return gate.validate(binding or self.binding,self.root)

    def test_complete_frozen_inventory(self):
        _,cases,_=self.validate()
        self.assertEqual({c["id"] for c,_ in cases},gate.REQUIRED)
        self.assertEqual(sum(c["kind"]=="refusal" for c,_ in cases),3)

    def test_mutated_case_manifest_refused(self):
        (self.root/"frozen/case-manifest.json").write_bytes(b"{}")
        with self.assertRaises(gate.Refused): self.validate()

    def test_changed_artifact_refused(self):
        (self.root/"fixture.jar").write_bytes(b"replacement")
        with self.assertRaises(gate.Refused): self.validate()

    def test_unpinned_runtime_and_invalid_deadline_refused(self):
        for key,value in (("runtime_image","java:latest"),("max_elapsed_seconds",0),
                          ("max_elapsed_seconds",True),("qualified",True)):
            b=copy.deepcopy(self.binding);b[key]=value
            with self.subTest(key=key),self.assertRaises(gate.Refused):self.validate(b)

    def test_unreviewed_binding_cannot_start(self):
        with patch.object(gate,"execute_case") as execute:
            with self.assertRaises(gate.Refused):gate.run(self.path,"0"*64,self.root/"attempt")
            execute.assert_not_called()

    def test_findings_refuse_before_candidate(self):
        p=self.root/"frozen/case-manifest.json"
        data=json.loads(p.read_text());data["all_hand_oracle_match"]=False
        p.write_text(json.dumps(data))
        self.binding["case_manifest"]["sha256"]=gate.digest(p.read_bytes())
        with self.assertRaises(gate.Refused):self.validate()

    def test_original_deadline_and_attempt_separation(self):
        deadlines=[]
        def execute(image,artifact,inputs,case,deadline,retained):
            deadlines.append(deadline)
            return dict(exit_code=7,command=[gate.COMMAND[0]],outputs=None,stderr_nonempty=True)
        sha=gate.digest(self.path.read_bytes())
        with patch.object(gate,"execute_case",side_effect=execute):
            first=gate.run(self.path,sha,self.root/"attempt1")
            second=gate.run(self.path,sha,self.root/"attempt2")
            with self.assertRaises(FileExistsError):gate.run(self.path,sha,self.root/"attempt1")
        self.assertEqual(len(set(deadlines[:10])),1)
        self.assertFalse(first["all_cases_match"] or second["all_cases_match"])
        self.assertEqual(sum(r["verdict"]=="EXPECTED_REFUSAL" for r in first["cases"]),3)
        self.assertTrue(all(r["comparison_policy"]==gate.BYTE_POLICY for r in first["cases"]))

    def test_nonzero_without_diagnostic_does_not_satisfy_refusal(self):
        with patch.object(gate,"execute_case",return_value=dict(exit_code=7,command=[],outputs=None,stderr_nonempty=False)):
            result=gate.run(self.path,gate.digest(self.path.read_bytes()),self.root/"attempt")
        self.assertTrue(all(r["verdict"]=="REFUSAL_NOT_OBSERVED" for r in result["cases"] if r["kind"]=="refusal"))

    def test_cleanup_fault_stops_later_cases(self):
        with patch.object(gate,"execute_case",side_effect=gate.Refused("container-cleanup-unconfirmed")) as execute:
            result=gate.run(self.path,gate.digest(self.path.read_bytes()),self.root/"attempt")
        self.assertEqual(execute.call_count,1)
        self.assertEqual(len(result["cases"]),10)
        self.assertTrue(all(r["verdict"]=="NOT_RUN" for r in result["cases"][1:]))

    def test_unassigned_bytes_remain_visible_and_verdict_bearing(self):
        _,cases,_=self.validate()
        _,arrays=next(c for c in cases if c[0]["kind"]=="success" and c[1]["expected"]["TRANSACT"])
        expected=arrays["expected"]
        for offset in (56,330):
            actual=dict(expected);raw=bytearray(actual["TRANSACT"])
            raw[offset]=0xC1;actual["TRANSACT"]=bytes(raw)
            output=self.root/("compare-"+str(offset));output.mkdir()
            result=gate.compare_case(expected,actual,"cp037",output)
            self.assertEqual(result["verdict"],"DIFFERENT")
            self.assertFalse(result["dataset_deltas"]["TRANSACT"]["identical"])

    def test_bad_output_inventory_is_candidate_failure(self):
        for files in ({}, {"ACCTFILE.bin":b"", "TRANSACT.bin":b"", "extra":b"x"}):
            raw=io.BytesIO()
            with tarfile.open(fileobj=raw,mode="w") as archive:
                for name,data in files.items():
                    member=tarfile.TarInfo(name);member.size=len(data)
                    archive.addfile(member,io.BytesIO(data))
            with self.subTest(files=list(files)),self.assertRaises(gate.OutputProblem):
                gate.output_tar(raw.getvalue())

    def test_candidate_output_faults_do_not_stop_later_cases(self):
        for verdict in ("OUTPUT_CONTRACT_VIOLATION","UNDECODABLE"):
            with patch.object(gate,"execute_case",side_effect=gate.OutputProblem("bad public output",verdict)) as execute:
                result=gate.run(self.path,gate.digest(self.path.read_bytes()),self.root/verdict)
            self.assertEqual(execute.call_count,10)
            self.assertTrue(all(r["verdict"]==verdict for r in result["cases"]))
            self.assertTrue(all((self.root/verdict/r["id"]/"result.json").is_file() for r in result["cases"]))

    def test_infrastructure_and_deadline_stop_attempt(self):
        for index,reason in enumerate(("docker-operation-failed:create","container-boundary-not-observed","original-deadline-expired")):
            with patch.object(gate,"execute_case",side_effect=gate.Refused(reason)) as execute:
                result=gate.run(self.path,gate.digest(self.path.read_bytes()),self.root/("infrastructure-"+str(index)))
            self.assertEqual(execute.call_count,1)
            self.assertTrue(all(r["verdict"]=="NOT_RUN" for r in result["cases"][1:]))

    def test_partial_numeric_and_non_ascii_output_have_failing_verdicts(self):
        _,cases,_=self.validate()
        _,arrays=next(c for c in cases if c[0]["kind"]=="success" and c[1]["expected"]["TRANSACT"])
        expected=arrays["expected"]
        for label,offset,value in (("partial",None,None),("numeric",132,0),("non-ascii",330,0x51)):
            actual=dict(expected);raw=bytearray(actual["TRANSACT"])
            if offset is None: raw=raw[:-1]
            else: raw[offset]=value
            actual["TRANSACT"]=bytes(raw)
            output=self.root/label;output.mkdir()
            with self.subTest(label=label),self.assertRaises(gate.OutputProblem) as caught:
                gate.compare_case(expected,actual,"cp037",output)
            self.assertEqual(caught.exception.verdict,"OUTPUT_CONTRACT_VIOLATION" if label=="partial" else "UNDECODABLE")


if __name__=="__main__":
    unittest.main()
