"""Public synthetic fixtures only. The dedicated workflow runs on Linux amd64."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from tools import intcalc_stage2_memory_route as route


native = route.native
DATE = "2026112000"
STAMP = "2026-11-20-12.34.56.120000"


class CommandCapture(route.MemoryDocker):
    """Run the actual #585 Docker argv serializer and intercept its OS boundary."""
    def __init__(self):
        self.image = SimpleNamespace(ref="synthetic@sha256:" + "1"*64)
        self.commands = []

    def record(self, kind, name):
        pass

    def ok(self, argv):
        self.commands.append(b"\0".join(arg.encode("utf-8") for arg in argv))

    def inspect(self, name):
        return {"synthetic": name}


class MemoryRouteTests(unittest.TestCase):
    def mounts(self, folder):
        mounts = {"/output": ("public-volume", True, "volume"),
                  "/candidate.jar": ("/public/candidate.jar", False, "bind")}
        for dd in route.FIELDS:
            path = folder / (dd + ".bin")
            path.write_bytes(b"PUBLIC1")
            mounts["/input/" + path.name] = (str(path), False, "bind")
        return mounts

    def capture(self, mounts, date, stamp):
        docker = CommandCapture()
        with patch.object(native, "boundary") as inspect:
            docker.create("same-allocation", "jre", mounts, native.JAVA, route.template(date, stamp))
        _, _, checked_mounts, entry, args = inspect.call_args.args
        self.assertEqual((entry, args), (native.JAVA, list(route.COMMAND)))
        self.assertEqual(checked_mounts[route.ARGFILE][1:], (False, "bind"))
        return docker.commands[0]

    def test_serialized_commands_identical_as_raw_bytes(self):
        # Use the same fixed synthetic allocation for both observations, including bind source names.
        # No secret data, production invocation, case generator or Docker daemon is involved.
        area = Path("/dev/shm")
        if not area.is_dir():
            with tempfile.TemporaryDirectory() as tmp:
                self.assert_denied_clock_dir(Path(tmp))
            return
        with tempfile.TemporaryDirectory(dir=area, prefix="private-case-") as tmp:
            folder = Path(tmp)
            mounts = self.mounts(folder)
            argfile = folder / "case-clock.args"
            first = self.capture(mounts, DATE, STAMP)
            first_bytes = argfile.read_bytes()
            self.assertEqual(argfile.stat().st_mode & 0o777, 0o444)
            argfile.unlink()
            for dd in route.FIELDS:
                (folder / (dd + ".bin")).write_bytes(b"PUBLIC2")
            second = self.capture(mounts, "2027010100", "2027-01-01-11.11.11.990000")
            self.assertEqual(first, second)
            self.assertEqual(first.split(b"\0")[-1], b"@/case-clock.args")
            for canary in (DATE.encode(), STAMP.encode(), b"2027010100", b"PUBLIC1", b"PUBLIC2"):
                self.assertNotIn(canary, first)
            self.assertEqual(first_bytes, ("\n".join(route.template(DATE, STAMP))+"\n").encode("ascii"))
            changed = [i for i,(a,b) in enumerate(zip(first_bytes.splitlines(),argfile.read_bytes().splitlines()),1) if a!=b]
            self.assertEqual(changed, [9,11])
            self.assertEqual(len(argfile.read_bytes().splitlines()),13)
            with self.assertRaises((FileExistsError, native.p5.Refused)):
                self.capture(mounts, DATE, STAMP)

    def test_private_clock_file_sets_read_only_mode_under_private_umask(self):
        area = Path("/dev/shm")
        if not area.is_dir():
            with tempfile.TemporaryDirectory() as tmp:
                self.assert_denied_clock_dir(Path(tmp))
            return

        previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, previous_umask)
        with tempfile.TemporaryDirectory(dir=area) as tmp:
            folder = Path(tmp)
            route.private_clock_file(self.mounts(folder), route.template(DATE, STAMP))
            leaf = folder / "case-clock.args"
            expected = (
                b"-Xmx256m\n-jar\n/candidate.jar\n--input-dir\n/input\n--output-dir\n/output\n"
                b"--processing-date\n2026112000\n--timestamp\n2026-11-20-12.34.56.120000\n"
                b"--codec\ncp037\n"
            )
            self.assertEqual(stat.S_IMODE(leaf.stat().st_mode), 0o444)
            self.assertEqual(leaf.read_bytes(), expected)

    def assert_denied_clock_dir(self, folder):
        mounts = self.mounts(folder)
        with self.assertRaises(route.b2.Refused):
            route.private_clock_file(mounts, route.template(DATE,STAMP))
        self.assertFalse((folder/"case-clock.args").exists())

    def test_non_tmpfs_parent_refused_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assert_denied_clock_dir(Path(tmp))

    def test_java_argument_injection_refused_before_mount_access(self):
        for date,stamp in [(DATE+"\n", STAMP), ("０"*10, STAMP), (DATE, STAMP+" @other")]:
            with self.subTest(date=date,stamp=stamp), self.assertRaises(route.b2.Refused):
                route.template(date, stamp)
        for pos in (0,1,2,3,5,7,9,11,12):
            args = route.template(DATE,STAMP)
            args[pos] = "alternate"
            with self.assertRaises(route.b2.Refused):
                route.private_clock_file({}, args)

    def test_only_reviewed_mounts_and_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = self.mounts(Path(tmp))
            for key,value in [("/extra",("x",False,"bind")),("/candidate.jar",("x",True,"bind")),
                              ("/output",("x",True,"bind")),("/input/"+route.FIELDS[0]+".bin",("x",True,"bind"))]:
                with self.subTest(key=key), self.assertRaises(route.b2.Refused):
                    route.private_clock_file(dict(good, **{key:value}), route.template(DATE,STAMP))

    def test_collector_keeps_native_command(self):
        docker = CommandCapture()
        with patch.object(native,"boundary") as inspected:
            docker.create("collector","jre",{},"/bin/sleep",["60"])
        self.assertEqual(inspected.call_args.args[-2:],("/bin/sleep",["60"]))
        with self.assertRaises(route.b2.Refused):
            docker.create("candidate","jre",{},"unreviewed",[])

    def test_single_case_engine_and_source_identity(self):
        self.assertIs(route.MemoryRuntime.run_case,native._Runtime.run_case)
        self.assertIs(route.MemoryRuntime._case,native._Runtime._case)
        host=Mock()
        with patch.object(native.h1,"source_identity",return_value=("a"*40,"b"*40)):
            host.commands.out.return_value=("a"*40+"\n").encode()
            self.assertEqual(route.main_identity(host),dict(source_commit="a"*40,source_tree="b"*40))
            host.commands.out.return_value=b"different-main"
            with self.assertRaises(route.b2.Refused):
                route.main_identity(host)

    def test_same_engine_on_public_qualification_and_private_comparison(self):
        ids=native.key.CASE_IDS
        sample = dict(inputs={dd:b"x" for dd in route.FIELDS},timestamp=STAMP,processing_date=DATE,
                      compare_output_files=True,expected={k:b"" for k in ["stdout","stderr",*native.p5.OUTPUTS]})
        sample["expected"]["exit"]=0
        jars={label:label.encode() for label in native.FIXTURES}
        observed=dict(sample["expected"],timed_out=False,output_capped=False)
        imperfect=dict(observed, stdout=b"public difference")
        parity=dict(schema="arm64-public-parity/1",jar_sha256=native.c.sha(jars["imperfect"]),
                    cases={cid:native.compared(imperfect,True) for cid in ids})
        raw=native.c.canonical(parity)
        image=SimpleNamespace(digest="a"*64,host_profile="b"*64)
        base=dict(schema="native-candidate-public-check/1",runtime_binding_sha256=image.digest,
                  host_profile_sha256=image.host_profile,fixtures_sha256="c"*64,arm64_observations_sha256=native.c.sha(raw),
                  answer_key_manifest_sha256=native.KEY_HASH,public_cases_matched=16,public_cases_with_parity=16,
                  adversarial_probes_passed=3,private_execution_authorized=False,limits=list(native.LIMITS))
        engines={}
        def engine(host, image, jar):
            engines[jar]=Mock()
            engines[jar].run_case.return_value={
                b"matches_all":observed,b"imperfect":imperfect,b"timeout":dict(observed,timed_out=True),
                b"output_cap":dict(observed,output_capped=True),b"boundary":dict(observed,stdout=b"boundary-probe-passed\n")
            }[jar]
            return engines[jar]
        host=Mock()
        identity=dict(source_commit="1"*40,source_tree="2"*40)
        with patch.object(route,"main_identity",return_value=identity), patch.object(native,"fixture_catalog",return_value=base | {"arm64_observations_sha256":native.c.sha(raw)}), patch.object(native.key,"load",return_value=([sample]*16,{"manifest_sha256":native.KEY_HASH})), patch.object(route,"MemoryRuntime",side_effect=engine) as make:
            receipt=route.public_qualification(host,image,jars,b"public","c"*64,raw,None,None,
                        SimpleNamespace(manifest_sha256=native.KEY_HASH),native.c.canonical(base))
            self.assertEqual([engines[jars[k]].run_case.call_count for k in ["matches_all","imperfect","timeout","output_cap","boundary"]],[16,16,1,1,1])
            self.assertEqual(receipt["source_tree"],identity["source_tree"])
            self.assertIs(receipt["private_execution_authorized"],False)
            material=SimpleNamespace(result=json.dumps(dict(retained_jar={},selected={},closure_record_sha256="x",
                                      hidden={"selected_jar_sha256":"j"})).encode(),binding=b"{}",jar=jars["imperfect"],image=image)
            with patch.object(route,"verify_route",return_value=True),patch.object(native,"selected_jar",return_value="j"),patch.object(route.b2,"compare_all",return_value=True) as compare:
                evaluator=route._QualifiedEvaluator(host)
                self.assertIs(evaluator.compare([],material,float("inf")),True)
                self.assertIs(compare.call_args.args[1],engines[material.jar].run_case)
                self.assertEqual(make.call_args.args,(host,image,material.jar))
                with self.assertRaises(route.b2.Refused):
                    evaluator.compare([],material,float("inf"))

    def test_qualification_binds_every_field_and_policy_bytes(self):
        host=SimpleNamespace(p={})
        image=SimpleNamespace(host_profile=native.h1.sha(native.h1.canonical(host.p)),digest="a"*64)
        baseline=native.c.canonical(dict(schema="native-candidate-public-check/1",fixtures_sha256="c"*64,
                   arm64_observations_sha256="d"*64,host_profile_sha256=image.host_profile,
                   runtime_binding_sha256=image.digest,answer_key_manifest_sha256=native.KEY_HASH,
                   public_cases_matched=16,public_cases_with_parity=16,adversarial_probes_passed=3,
                   private_execution_authorized=False,limits=list(native.LIMITS)))
        ident=dict(source_commit="1"*40,source_tree="2"*40)
        spec=route.route_spec()
        receipt=dict(schema="stage2-memory-route-public-check/1",route_sha256=native.c.digest(spec),
                     native_qualification_sha256=native.c.sha(baseline),host_profile_sha256=image.host_profile,
                     image_binding_sha256=image.digest,answer_key_sha256=native.KEY_HASH,fixture_catalog_sha256="c"*64,
                     arm64_parity_sha256="d"*64,public_matches=16,public_parity=16,probes=3,
                     private_execution_authorized=False,**ident)
        m=SimpleNamespace(image=image,native_qualification=baseline,runtime_policy=native.c.canonical(spec))
        with patch.object(route,"main_identity",return_value=ident):
            m.route_qualification=native.c.canonical(receipt)
            self.assertTrue(route.verify_route(m,host))
            for field in receipt:
                m.route_qualification=native.c.canonical(dict(receipt,**{field:None}))
                with self.subTest(field=field), self.assertRaises(route.b2.Refused):
                    route.verify_route(m,host)
            m.route_qualification=baseline
            with self.assertRaises(route.b2.Refused):
                route.verify_route(m,host)
            m.route_qualification=native.c.canonical(receipt)
            m.runtime_policy=b"{}"
            with self.assertRaises(route.b2.Refused):
                route.verify_route(m,host)

    def test_private_entry_uses_b1_admission_first(self):
        args=[object() for _ in range(5)]
        with patch.object(route.b1,"run_once",return_value="fixture") as once:
            self.assertEqual(route.evaluate_private(*args),"fixture")
        self.assertEqual(once.call_args.args[:-1],tuple(args))
        self.assertIsInstance(once.call_args.args[-1],route._QualifiedEvaluator)
