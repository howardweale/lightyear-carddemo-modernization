"""Create only synthetic/public rehearsal data; never point this at a delivery."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from carddemo_oracle.oracle import run_directory
from lightyear_mainframe.public_corpus import CARDDEMO_COMMIT
from lightyear_mainframe.records import load_copybook, to_ascii_fixed
from lightyear_mainframe.source import sha
from lightyear_mainframe.zos_bindings import ROOT, load_bindings, dataset_binding
from lightyear_mainframe.zos_bridge import INPUTS

FIXTURE = ROOT / "tests/mainframe/fixtures/arrival-rehearsal"


def build(source):
    bindings = load_bindings()
    provenance = {}

    def blob(path):
        raw = subprocess.check_output(
            ["git", "-C", str(source), "show", f"{CARDDEMO_COMMIT}:{path}"]
        )
        provenance[path] = sha(raw)
        return raw

    public = ROOT / "tests/mainframe/fixtures/public-bridge"
    public.mkdir(parents=True, exist_ok=True)
    ebcdic = {}
    names = {
        "ACCTFILE": "ACCTDATA",
        "TCATBALF": "TCATBALF",
        "DISCGRP": "DISCGRP",
        "XREFFILE": "CARDXREF",
        "DALYTRAN": "DALYTRAN",
    }
    for dd, name in names.items():
        raw = blob("app/data/EBCDIC/AWS.M2.CARDDEMO." + name + ".PS")
        ebcdic[dd] = raw
        (public / (dd + ".ebcdic")).write_bytes(raw)
        if dd in INPUTS:
            (public / INPUTS[dd]).write_bytes(blob("app/data/ASCII/" + INPUTS[dd]))
    scratch = ROOT / "work/rehearsal-build"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        tmp = Path(tmp)
        input_dir = tmp / "inputs"
        input_dir.mkdir()
        for dd, filename in INPUTS.items():
            b = dataset_binding(bindings, "INTCALC", "STEP15", dd)
            (input_dir / filename).write_bytes(
                to_ascii_fixed(load_copybook(ROOT / b["copybook"]), ebcdic[dd])
            )
        run_directory(
            input_dir,
            tmp / "outputs",
            "2022071800",
            "2022-07-18-00.00.00.000000",
            "source-faithful",
        )
        generated = {
            dd: b"".join((tmp / "outputs" / name).read_bytes().splitlines())
            .decode("ascii")
            .encode("cp037")
            for dd, name in {
                "ACCTFILE": "acctdata.txt",
                "TRANSACT": "transactions.txt",
            }.items()
        }
    for job, n in [("INTCALC", 1), ("INTCALC", 2), ("POSTTRAN", 1)]:
        root = FIXTURE / f"{job}-run{n}-2026-10-05"
        root.mkdir(parents=True, exist_ok=True)
        (root / "submitted.jcl").write_bytes(blob("app/jcl/" + job + ".jcl"))
        program = "CBACT04C" if job == "INTCALC" else "CBTRN02C"
        (root / "job-output.txt").write_text(
            f"JOBNAME={job} JOB0000{n}\nSTART_UTC=2026-10-05T10:00:00Z\nEND_UTC=2026-10-05T10:01:00Z\nz/OS 2.5 JES2 Language Environment (SYNTHETIC REHEARSAL)\nSYSOUT:START OF EXECUTION OF PROGRAM {program}\n",
            encoding="utf-8",
            newline="\n",
        )
        (root / "return-codes.txt").write_text(
            f"STEP STEP15 PGM={program} RC=0000\n", encoding="utf-8", newline="\n"
        )
        (root / "compiler.lst").write_text(
            "Enterprise COBOL synthetic banner; NUMPROC(PFD) TRUNC(STD) ARITH(COMPAT)\n",
            encoding="utf-8",
            newline="\n",
        )
        (root / "note.txt").write_text(
            "Public-fixture rehearsal only. After-images are locally simulated, not z/OS observations.\n",
            encoding="utf-8",
            newline="\n",
        )
        meta = dict(
            schema="zos-delivery-run/1",
            job=job,
            system_datetime="2026-10-05T10:00:00Z",
            processing_date="2022071800" if job == "INTCALC" else None,
            candidate_timestamp="2022-07-18-00.00.00.000000",
            starting_state_id="public-restored-v1",
            datasets=[],
            evidence_class="synthetic-public-rehearsal",
        )
        before = (
            {k: v for k, v in ebcdic.items() if k != "DALYTRAN"}
            if job == "INTCALC"
            else {
                k: ebcdic[k] for k in ["ACCTFILE", "TCATBALF", "XREFFILE", "DALYTRAN"]
            }
        )
        before.update(
            {"TRANSACT": b""}
            if job == "INTCALC"
            else {"TRANFILE": b"", "DALYREJS": b""}
        )
        after = dict(before)
        if job == "INTCALC":
            after.update(generated)
            if n == 2:
                layout = load_copybook(
                    ROOT
                    / dataset_binding(bindings, job, "STEP15", "TRANSACT")["copybook"]
                )
                field = next(
                    f for f in layout.fields if f.path.endswith(".TRAN-PROC-TS")
                )
                raw = bytearray(after["TRANSACT"])
                for start in range(0, len(raw), layout.record_length):
                    raw[start + field.offset : start + field.offset + field.length] = (
                        "2022-07-18-00.00.01.000000".encode("cp037")
                    )
                after["TRANSACT"] = bytes(raw)
        else:
            daily_layout = load_copybook(
                ROOT / dataset_binding(bindings, job, "STEP15", "DALYTRAN")["copybook"]
            )
            after["DALYREJS"] = ebcdic["DALYTRAN"][
                : daily_layout.record_length
            ] + "0100Synthetic reject for decoding rehearsal only".ljust(80).encode(
                "cp037"
            )
        for phase, images in [("before", before), ("after", after)]:
            (root / phase).mkdir(exist_ok=True)
            for dd, raw in images.items():
                b = dataset_binding(bindings, job, "STEP15", dd)
                file = f"{phase}/{dd}.bin"
                (root / file).write_bytes(raw)
                meta["datasets"].append(
                    dict(
                        file=file,
                        phase=phase,
                        step="STEP15",
                        dd=dd,
                        dsn=b["dsn"],
                        recfm="F",
                        lrecl=b["record_length"],
                        blksize=0,
                        codec="cp037",
                    )
                )
        (root / "run.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    manifest = dict(
        schema="public-zos-rehearsal-provenance/1",
        commit=CARDDEMO_COMMIT,
        source_files=provenance,
        generated_after_images="Python source-faithful local oracle, never native z/OS evidence",
        timestamp_plant="Only TRAN-PROC-TS differs between the two INTCALC after-images",
        files={
            p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
            for tree in (public, FIXTURE)
            for p in sorted(tree.rglob("*"))
            if p.is_file()
        },
    )
    (ROOT / "tests/mainframe/fixtures/PROVENANCE.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    build(parser.parse_args().source)
