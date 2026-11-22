"""H3-R. One native amd64 execution route for public qualification and later approved private use."""
import os
from pathlib import Path
import re
import stat
import time

from tools import intcalc_native_candidate_runtime as native
from tools import intcalc_stage2_admission as b1
from tools import intcalc_stage2_comparison as b2


ARGFILE = "/case-clock.args"
COMMAND = ("@"+ARGFILE,)
FIELDS = native.p5.INPUTS
BLOCKED = b2.BLOCKED


def check(ok):
    if not ok:
        raise b2.Refused(BLOCKED)


def template(date, stamp):
    check(type(date) is str and re.fullmatch(r"[0-9]{10}",date) and type(stamp) is str and
          re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{6}",stamp))
    return ["-Xmx256m","-jar","/candidate.jar","--input-dir","/input","--output-dir","/output",
            "--processing-date",date,"--timestamp",stamp,"--codec","cp037"]


def route_spec():
    sources=(Path(__file__),Path(native.__file__),Path(native.p5.__file__),Path(b1.__file__),Path(b2.__file__))
    return dict(schema="stage2-private-safe-route/1",platform=native.PLATFORM,
                entrypoint=[native.JAVA],cmd=list(COMMAND),argument_file=ARGFILE,
                app_arguments=template("0000000000","0000-00-00-00.00.00.000000"),
                variable_lines={"processing_date":9,"timestamp":11},encoding="ASCII/LF",
                input_destinations=["/input/"+dd+".bin" for dd in FIELDS],
                input_storage="verified-/dev/shm-tmpfs",argument_mount="individual-read-only-bind",
                isolation=list(native.ISOLATION),source_sha256={p.name:native.c.sha(p.read_bytes()) for p in sources})


def private_clock_file(mounts,args):
    check(type(args) is list and len(args)==13 and args==template(args[8],args[10]))
    required={"/output","/candidate.jar"}|{"/input/"+dd+".bin" for dd in FIELDS}
    check(set(mounts)==required)
    check(mounts["/candidate.jar"][1:]==(False,"bind") and mounts["/output"][1:]==(True,"volume"))
    dirs=set()
    for dd in FIELDS:
        value,write,kind=mounts["/input/"+dd+".bin"]
        path=Path(value)
        check(write is False and kind=="bind" and path.name==dd+".bin" and path==path.resolve(strict=True))
        dirs.add(path.parent)
    check(len(dirs)==1)
    folder=dirs.pop()
    check(folder.parent==Path("/dev/shm") and folder.stat().st_dev==Path("/dev/shm").stat().st_dev)
    leaf=folder/"case-clock.args"
    raw=("\n".join(args)+"\n").encode("ascii")
    native.p5.exclusive(leaf,raw,0o444)
    fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        check(stat.S_ISREG(os.fstat(fd).st_mode))
        os.fchmod(fd, 0o444)
    finally:
        os.close(fd)
    check(stat.S_IMODE(leaf.stat().st_mode) == 0o444 and native.p5.read(leaf,1024) == raw)
    return dict(mounts,**{ARGFILE:(str(leaf),False,"bind")})


class MemoryDocker(native.NativeDocker):
    def create(self,name,kind,mounts,entry,args):
        if entry==native.JAVA:
            mounts=private_clock_file(mounts,args)
            args=list(COMMAND)
        else:
            check(entry=="/bin/sleep")
        # #585 serializes the fixed command and exact mount map and reads Docker inspect back before start.
        return super().create(name,kind,mounts,entry,args)


class MemoryRuntime(native._Runtime):
    def _docker(self,root,end,hard):
        check(native.c.sha(native.p5.read(self.prefix[0],268435456))==self.image.cli)
        return MemoryDocker(self.prefix,root/"resources",end,hard,self.image)


def main_identity(host):
    commit, tree = native.h1.source_identity(host.commands,host.p)
    root = str(native.h1.ref.ROOT.resolve())
    main = host.commands.out(["git","-C",root,"rev-parse","refs/heads/main"]).decode("ascii").strip()
    check(main == commit)
    return {"source_commit":commit,"source_tree":tree}


def native_qualification(raw,image):
    row = native.s1.strict(raw)
    expected = dict(schema="native-candidate-public-check/1", runtime_binding_sha256=image.digest,
                    host_profile_sha256=image.host_profile, answer_key_manifest_sha256=native.KEY_HASH,
                    public_cases_matched=16, public_cases_with_parity=16, adversarial_probes_passed=3,
                    private_execution_authorized=False, limits=list(native.LIMITS))
    for field in ("fixtures_sha256","arm64_observations_sha256"):
        check(native.c.hash_ok(row[field]))
        expected[field] = row[field]
    check(native.c.canonical(row)==native.c.canonical(expected))
    return row


def public_qualification(host,image,jars,catalog_raw,catalog_sha,parity_raw,answer_root,suite_root,review,native_raw):
    """Operator-only on the qualified Intel host. All fixtures, timings and observations here are public."""
    identity = main_identity(host)
    check(review.manifest_sha256==native.KEY_HASH)
    baseline = native_qualification(native_raw,image)
    check(baseline["fixtures_sha256"] == catalog_sha and baseline["arm64_observations_sha256"] == native.c.sha(parity_raw))
    catalog=native.fixture_catalog(catalog_raw,catalog_sha,jars)
    check(native.c.sha(parity_raw)==catalog["arm64_observations_sha256"])
    parity=native.s1.strict(parity_raw)
    check(set(parity)=={"schema","jar_sha256","cases"} and parity["schema"]=="arm64-public-parity/1" and parity["jar_sha256"]==native.c.sha(jars["imperfect"])
          and set(parity["cases"])==set(native.key.CASE_IDS))
    cases,source=native.key.load(answer_root,suite_root,review)
    check(len(cases)==16 and source["manifest_sha256"]==native.KEY_HASH)
    different=False
    for label in native.FIXTURES:
        engine=MemoryRuntime(host,image,jars[label])
        deadline=time.monotonic()+600
        for cid,case in zip(native.key.CASE_IDS,cases if label in ("matches_all","imperfect") else cases[:1]):
            obs=engine.run_case(case["inputs"],case["timestamp"],case["processing_date"],deadline)
            if label=="timeout":
                check(obs["timed_out"] is True and obs["output_capped"] is False)
            elif label=="output_cap":
                check(obs["timed_out"] is False and obs["output_capped"] is True)
            elif label=="boundary":
                check(not obs["timed_out"] and not obs["output_capped"] and obs["exit"]==0
                      and obs["stdout"]==b"boundary-probe-passed\n" and obs["stderr"]==b"")
            else:
                actual=native.compared(obs,case["compare_output_files"])
                wanted=native.compared(dict(case["expected"],timed_out=False,output_capped=False),case["compare_output_files"])
                check(not actual["timed_out"] and not actual["output_capped"])
                if label=="matches_all":
                    check(actual==wanted)
                else:
                    check(actual==parity["cases"][cid])
                    different |= actual!=wanted
    check(different)
    host.observe()
    return dict(schema="stage2-memory-route-public-check/1",route_sha256=native.c.digest(route_spec()),
                native_qualification_sha256=native.c.sha(native_raw),host_profile_sha256=image.host_profile,
                image_binding_sha256=image.digest,answer_key_sha256=native.KEY_HASH,fixture_catalog_sha256=catalog_sha,
                arm64_parity_sha256=native.c.sha(parity_raw),public_matches=16,public_parity=16,probes=3,
                private_execution_authorized=False,**identity)


def verify_route(material,host):
    try:
        identity=main_identity(host)
        check(native.h1.sha(native.h1.canonical(host.p))==material.image.host_profile)
        spec=route_spec()
        check(material.runtime_policy==native.c.canonical(spec))
        baseline=native_qualification(material.native_qualification,material.image)
        wanted=dict(schema="stage2-memory-route-public-check/1",route_sha256=native.c.digest(spec),
                    native_qualification_sha256=native.c.sha(material.native_qualification),
                    host_profile_sha256=material.image.host_profile,image_binding_sha256=material.image.digest,
                    answer_key_sha256=native.KEY_HASH,fixture_catalog_sha256=baseline["fixtures_sha256"],
                    arm64_parity_sha256=baseline["arm64_observations_sha256"],public_matches=16,public_parity=16,
                    probes=3,private_execution_authorized=False,**identity)
        check(material.route_qualification==native.c.canonical(wanted))
        return True
    except Exception:
        raise b2.Refused(BLOCKED) from None


class _QualifiedEvaluator:
    def __init__(self,host):
        self.host=host
        self.used=False

    def preflight(self,material):
        return verify_route(material,self.host)

    def compare(self,frames,material,end):
        check(not self.used)
        self.used=True
        verify_route(material,self.host)
        result=native.s1.strict(material.result)
        binding=native.s1.strict(material.binding)
        # Recheck exact S1 descriptor and classpath immediately before constructing the sole runtime.
        identity=native.selected_jar(material.jar,result["retained_jar"],result["selected"],binding,result["closure_record_sha256"])
        check(result["hidden"]["selected_jar_sha256"]==identity and time.monotonic()<end)
        engine=MemoryRuntime(self.host,material.image,material.jar)
        return b2.compare_all(frames,engine.run_case,end)


def evaluate_private(raw,expected,evidence,host,age_binary):
    # No arbitrary backend, factory or mode from the caller. The independent approval pins both route documents.
    return b1.run_once(raw,expected,evidence,host,age_binary,_QualifiedEvaluator(host))
