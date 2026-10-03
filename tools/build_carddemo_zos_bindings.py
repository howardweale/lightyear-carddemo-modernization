"""Build public bindings from git blobs at the pinned commit; no arrival input."""

import argparse
import json
import re
import subprocess
from pathlib import Path

from lightyear_mainframe.public_corpus import CARDDEMO_COMMIT
from lightyear_mainframe.records import load_copybook
from lightyear_mainframe.source import sha
from lightyear_mainframe.zos_bindings import ROOT, inspect_jcl


def build(source):
    def blob(path):
        return subprocess.check_output(
            ["git", "-C", str(source), "show", f"{CARDDEMO_COMMIT}:{path}"]
        )

    artifacts = {}
    provenance = json.loads(
        (ROOT / "spec/mainframe/copybooks/PROVENANCE.json").read_text()
    )

    def save(path, raw):
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        artifacts[path] = sha(raw)

    copies = [
        "CVACT01Y",
        "CVACT02Y",
        "CVACT03Y",
        "CVCUS01Y",
        "CVTRA01Y",
        "CVTRA02Y",
        "CVTRA03Y",
        "CVTRA04Y",
        "CVTRA05Y",
        "CVTRA06Y",
        "CVTRA07Y",
        "CUSTREC",
    ]
    for name in copies:
        origin = f"app/cpy/{name}.cpy"
        raw = blob(origin)
        save(f"spec/mainframe/copybooks/{name}.cpy", raw)
        provenance["files"][origin] = sha(raw)
    save("spec/mainframe/copybooks/COSTM01.cpy", blob("app/cpy/COSTM01.CPY"))
    provenance["files"]["app/cpy/COSTM01.CPY"] = artifacts[
        "spec/mainframe/copybooks/COSTM01.cpy"
    ]
    programs = {}
    for file in [
        "CBACT04C.cbl",
        "CBTRN02C.cbl",
        "CBTRN03C.cbl",
        "CBSTM03A.CBL",
        "CBSTM03B.CBL",
    ]:
        raw = blob("app/cbl/" + file)
        programs[file] = raw.decode("utf-8")
        save("spec/mainframe/public-source/" + file, raw)
    # Expand the two source declarations into one decodable composite record.
    daily = blob("app/cpy/CVTRA06Y.cpy").decode("utf-8")
    declarations = "\n".join(
        line[:72] for line in daily.splitlines() if re.match(r"^\s+(01|05)\s", line)
    )
    trailer = re.search(
        r"        01 WS-VALIDATION-TRAILER\.[\s\S]*?(?=\n\s*01 WS-COUNTERS)",
        programs["CBTRN02C.cbl"],
    )[0]
    trailer = "\n".join(line[:72].rstrip() for line in trailer.splitlines())
    declarations = declarations.replace(
        "01  DALYTRAN-RECORD.", "01  REJECT-RECORD.\n           05 DALYTRAN-RECORD."
    )
    declarations = re.sub(
        r"(?m)^(\s*)05(  DALYTRAN-[^\n]+)", r"\g<1>10\2", declarations
    )
    declarations = re.sub(r"(?m)^(\s*)05(  FILLER[^\n]+)", r"\g<1>10\2", declarations)
    trailer = trailer.replace("01 WS-VALIDATION-TRAILER.", "05 WS-VALIDATION-TRAILER.")
    trailer = trailer.replace("05 WS-VALIDATION-FAIL", "10 WS-VALIDATION-FAIL")
    save(
        "spec/mainframe/copybooks/POSTREJS.cpy",
        (
            "      * Derived from CVTRA06Y and CBTRN02C WS-VALIDATION-TRAILER.\n"
            + declarations
            + "\n"
            + trailer
            + "\n"
        ).encode(),
    )
    provenance["derived"] = {
        "POSTREJS.cpy": {
            "sources": ["app/cpy/CVTRA06Y.cpy", "app/cbl/CBTRN02C.cbl"],
            "method": "Nest daily transaction and validation trailer; storage and elementary fields unchanged.",
        }
    }
    # The public CUSTREC's tabs push some PIC clauses past fixed-format column 72.
    # Preserve the original and derive an explicitly attributed indentation-only
    # layout instead of silently substituting the differently named CVCUS01Y fields.
    customer_lines = [
        line.strip()
        for line in blob("app/cpy/CUSTREC.cpy").decode().splitlines()
        if re.match(r"^\s*(01|05)\s", line)
    ]
    customer = (
        "      * Indentation-only extraction of pinned CUSTREC, full declarations.\n"
        + "\n".join("       " + line for line in customer_lines)
        + "\n"
    )
    save("spec/mainframe/copybooks/CUSTREC-INTAKE.cpy", customer.encode())
    provenance["derived"]["CUSTREC-INTAKE.cpy"] = {
        "sources": ["app/cpy/CUSTREC.cpy"],
        "method": "Strip leading whitespace and place each complete level-01/05 declaration at column 8; no declaration tokens changed. Original tabs retained separately.",
    }
    save(
        "spec/mainframe/copybooks/PROVENANCE.json",
        (json.dumps(provenance, indent=2) + "\n").encode(),
    )
    datasets = {}
    for name, copy, keys in [
        ("account", "CVACT01Y", ["ACCT-ID"]),
        ("card", "CVACT02Y", ["CARD-NUM"]),
        ("xref", "CVACT03Y", ["XREF-CARD-NUM"]),
        ("customer", "CVCUS01Y", ["CUST-ID"]),
        ("statement-customer", "CUSTREC-INTAKE", ["CUST-ID"]),
        ("balance", "CVTRA01Y", ["TRANCAT-ACCT-ID", "TRANCAT-TYPE-CD", "TRANCAT-CD"]),
        (
            "disclosure",
            "CVTRA02Y",
            ["DIS-ACCT-GROUP-ID", "DIS-TRAN-TYPE-CD", "DIS-TRAN-CAT-CD"],
        ),
        ("type", "CVTRA03Y", ["TRAN-TYPE"]),
        ("category", "CVTRA04Y", ["TRAN-TYPE-CD", "TRAN-CAT-CD"]),
        ("transaction", "CVTRA05Y", ["TRAN-ID"]),
        ("daily", "CVTRA06Y", ["DALYTRAN-ID"]),
        ("reject", "POSTREJS", ["DALYTRAN-ID"]),
        ("statement-transaction", "COSTM01", ["TRNX-CARD-NUM", "TRNX-ID"]),
    ]:
        path = f"spec/mainframe/copybooks/{copy}.cpy"
        layout = load_copybook(ROOT / path)
        paths = [f.path for f in layout.fields]
        resolved = []
        for key in keys:
            matches = [p for p in paths if p.split(".")[-1] == key]
            if len(matches) != 1:
                raise ValueError(f"No unique key {key}: {paths}")
            resolved.append(matches[0])
        datasets[name] = dict(
            copybook=path,
            record_length=layout.record_length,
            recfm="F",
            keys=resolved,
            mode="records",
            timestamp_fields=[
                p
                for p in paths
                if p.endswith(("TRAN-PROC-TS", "DALYTRAN-PROC-TS", "TRNX-PROC-TS"))
            ],
        )
    for name, program, field in [
        ("statement", "CBSTM03A.CBL", "FD-STMTFILE-REC"),
        ("html", "CBSTM03A.CBL", "FD-HTMLFILE-REC"),
        ("report", "CBTRN03C.cbl", "FD-REPTFILE-REC"),
        ("dateparm", "CBTRN03C.cbl", "FD-DATEPARM-REC"),
    ]:
        length = int(
            re.search(re.escape(field) + r"\s+PIC X\((\d+)\)", programs[program])[1]
        )
        datasets[name] = dict(
            copybook=None,
            record_length=length,
            recfm="FB",
            keys=[],
            mode="text",
            timestamp_fields=[],
            length_source=f"{program}:{field}",
        )
    names = {
        "ACCTFILE": "account",
        "CARDFILE": "card",
        "XREFFILE": "xref",
        "XREFFIL1": "xref",
        "CARDXREF": "xref",
        "CUSTFILE": "statement-customer",
        "TCATBALF": "balance",
        "DISCGRP": "disclosure",
        "TRANSACT": "transaction",
        "TRANFILE": "transaction",
        "DALYTRAN": "daily",
        "DALYREJS": "reject",
        "TRNXFILE": "statement-transaction",
        "STMTFILE": "statement",
        "HTMLFILE": "html",
        "TRANREPT": "report",
        "TRANTYPE": "type",
        "TRANCATG": "category",
        "DATEPARM": "dateparm",
    }
    jobs = {}
    for job in ["INTCALC", "POSTTRAN", "CREASTMT", "TRANREPT"]:
        filename = job + (".JCL" if job == "CREASTMT" else ".jcl")
        raw = blob("app/jcl/" + filename)
        save("spec/mainframe/public-source/" + filename, raw)
        rows = inspect_jcl(raw.decode())
        for row in rows:
            row["dataset"] = names.get(row["dd"])
            if row["dd"] in ("SORTIN", "PRC001.FILEIN", "PRC001.FILEOUT"):
                row["dataset"] = "transaction"
            if row["dd"] in ("SORTOUT", "INFILE", "OUTFILE"):
                row["dataset"] = (
                    "statement-transaction" if job == "CREASTMT" else "transaction"
                )
            if row["dataset"]:
                row["expected_record_length"] = datasets[row["dataset"]][
                    "record_length"
                ]
                row["record_format"] = row["dcb"].get("recfm", "F")
            row["dataset_name_pattern"] = re.escape(row["dsn"])
        jobs[job] = rows
    for file in ["TRANREPT.prc", "REPROC.prc"]:
        save("spec/mainframe/public-source/" + file, blob("app/proc/" + file))
    result = dict(
        schema="carddemo-zos-bindings/1",
        source_commit=CARDDEMO_COMMIT,
        artifacts=artifacts,
        datasets=datasets,
        jobs=jobs,
        notes=[
            "Exact DSNs at the pinned commit: renamed HLQs are findings, not silently admitted.",
            "VSAM downloads must be sequential binary copies with explicit transfer framing.",
            "TRANREPT public JCL repeats STEP05R and requires expanded submitted procedure/JCL review.",
            "CUSTREC-INTAKE preserves CUSTREC declaration tokens with explicit indentation-only extraction; originals and transformation provenance retained.",
        ],
    )
    (ROOT / "spec/mainframe/carddemo-bindings.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    build(parser.parse_args().source)
