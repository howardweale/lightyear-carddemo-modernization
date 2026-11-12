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
    @classmethod
    def setUpClass(cls):
        frozen = os.environ.get("C1_FROZEN")
        if not frozen or not Path(frozen).is_dir():
            raise unittest.SkipTest("C1_FROZEN directory absent; dedicated C1 CI supplies it")

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

    def test_named_report_only_regions_are_fully_reported_without_changing_verdict(self):
        _,cases,_=self.validate()
        _,arrays=next(c for c in cases if c[0]["kind"]=="success" and c[1]["expected"]["TRANSACT"])
        expected=arrays["expected"]
        actual=dict(expected);raw=bytearray(actual["TRANSACT"])
        raw[56]=0x51;raw[330]=0;actual["TRANSACT"]=bytes(raw)
        output=self.root/"report-only";output.mkdir()
        result=gate.compare_report_only_case(expected,actual,"cp037",output)
        self.assertEqual(result["verdict"],"MATCH")
        self.assertTrue(any(r["different"] for r in result["unassigned_region_observations"]))
        self.assertFalse(result["raw_artifacts_changed"])
        actual=dict(expected);raw=bytearray(actual["TRANSACT"]);raw[32]=0xC1;actual["TRANSACT"]=bytes(raw)
        output=self.root/"assigned";output.mkdir()
        result=gate.compare_report_only_case(expected,actual,"cp037",output)
        self.assertEqual(result["verdict"],"DIFFERENT")

    def test_report_only_policy_needs_exact_scope_and_expiry(self):
        self.assertIs(gate.selected_byte_policy(self.binding),gate.BYTE_POLICY)
        for policy in ({},{"name":gate.REPORT_ONLY_POLICY["name"]}):
            bound=copy.deepcopy(self.binding);bound["byte_policy"]=policy
            with self.assertRaises(gate.Refused):gate.selected_byte_policy(bound)
        bound=copy.deepcopy(self.binding)
        bound["byte_policy"]=dict(name=gate.REPORT_ONLY_POLICY["name"],
            artifact_sha256=bound["artifact"]["sha256"],case_manifest_sha256=bound["case_manifest"]["sha256"],
            expires_at="2000-01-01T00:00:00+00:00",attempt_name="one-attempt")
        with self.assertRaises(gate.Refused):gate.selected_byte_policy(bound)


    def test_candidate_exec_transport_fault_never_scores_expected_refusal(self):
        # Real execute_case control flow, mocked Docker plumbing; no container run.
        _, cases, governance = self.validate()
        cases.sort(key=lambda item: item[0]["kind"] != "refusal")
        for index, (rc, stderr, timeout, cleanup_failure) in enumerate((
                (125,b"failure",False,False),(126,b"failure",False,False),
                (127,b"failure",False,False),(1,b"Error response from daemon: unavailable",False,False),
                (0,b"Cannot connect to the Docker daemon",False,False),
                (-9,b"",True,False),(-9,b"",True,True))):
            creates = {}
            def fake_capture(argv, deadline, cap=gate.MAX_CAPTURE):
                result = dict(rc=0, stdout=b"", stderr=b"", timeout=False, overflow=False)
                if argv[1] == "create":
                    creates[argv[argv.index("--name")+1]] = argv
                elif argv[1] == "inspect":
                    args = creates[argv[2]]
                    mount = args[args.index("--mount")+1]
                    volume = mount.split("source=",1)[1].split(",",1)[0]
                    state = dict(HostConfig=dict(NetworkMode="none",ReadonlyRootfs=True),
                        Config=dict(User="65534:65534",Image=self.binding["runtime_image"]),
                        Mounts=[dict(Destination="/output",Type="volume",Name=volume,RW=True),
                                dict(Destination="/input",RW=False),dict(Destination="/candidate.jar",RW=False)])
                    result["stdout"] = json.dumps([state]).encode()
                elif argv[1] == "exec":
                    result.update(rc=rc,stderr=stderr,timeout=timeout)
                elif argv[1] == "rm" and cleanup_failure:
                    result.update(rc=1,stderr=b"cleanup denied")
                return result
            with patch.object(gate,"capture",side_effect=fake_capture), patch.object(
                    gate,"validate",return_value=(b"mock",cases,governance)):
                report=gate.run(self.path,gate.digest(self.path.read_bytes()),self.root/("transport-"+str(index)))
            first=report["cases"][0]
            self.assertEqual(first["verdict"],"TIMEOUT" if timeout else "FAULT")
            self.assertEqual(first["error_type"],"CandidateTimeout" if timeout else "Refused")
            self.assertIn("original-deadline-expired-during-candidate" if timeout else "docker-exec-infrastructure:candidate",first["error"])
            self.assertTrue(all(r["verdict"]=="NOT_RUN" for r in report["cases"][1:]))
            runtime=json.loads((self.root/("transport-"+str(index))/first["id"]/"runtime.json").read_text())
            self.assertEqual(runtime["cleanup_confirmed"],not cleanup_failure)
            self.assertEqual(runtime["cleanup_allowance_seconds"],5)
            self.assertTrue(all(r["elapsed_ms"]>=0 for r in runtime["operations"]+runtime["cleanup"]))

    def test_candidate_timeout_is_timeout_and_stops_later_cases(self):
        with patch.object(gate,"execute_case",side_effect=gate.CandidateTimeout(
                "original-deadline-expired-during-candidate")) as execute:
            report=gate.run(self.path,gate.digest(self.path.read_bytes()),self.root/"timeout")
        self.assertEqual(execute.call_count,1)
        self.assertEqual(report["cases"][0]["verdict"],"TIMEOUT")
        self.assertTrue(all(r["verdict"]=="NOT_RUN" for r in report["cases"][1:]))


class TransportMetadataTests(unittest.TestCase):
    def test_timing_retained_for_result_and_launch_exception(self):
        rows=[]
        result=dict(rc=0,stdout=b"",stderr=b"",timeout=False,overflow=False)
        with patch.object(gate,"capture",return_value=result), patch.object(
                gate.time,"monotonic_ns",side_effect=[1000000,4500000]):
            gate.timed_capture(["docker","inspect","fixture"],10,rows)
        self.assertEqual(rows[0]["elapsed_ms"],3.5)
        with patch.object(gate,"capture",side_effect=OSError("missing docker")), patch.object(
                gate.time,"monotonic_ns",side_effect=[1000000,3000000]):
            with self.assertRaises(OSError):
                gate.timed_capture(["docker","rm","fixture"],10,rows,kind="container",name="fixture")
        self.assertEqual(rows[1]["elapsed_ms"],2.0)
        self.assertEqual(rows[1]["error_type"],"OSError")
        self.assertEqual(rows[1]["kind"],"container")

    def test_collector_daemon_failure_is_infrastructure(self):
        result=dict(rc=1,stderr=b"Error response from daemon: missing container")
        with self.assertRaisesRegex(gate.Refused,"docker-exec-infrastructure:collector"):
            gate.require_exec_transport(result,"collector")



if __name__=="__main__":
    unittest.main()
