"""Conservative JES/IEF observations; missing items never acquire defaults."""

import re
from .source import sha
from lightyear_control_tower.decisions import digest


def observe(text, compiler=""):
    job_id = re.search(r"\bJOB\d{4,8}\b", text)
    job = re.search(r"\b(?:JOBNAME\s*[=:]\s*|IEF403I\s+)([A-Z][A-Z0-9]{0,7})\b", text)
    starts = re.findall(
        r"\bSTART(?:ED)?(?:_UTC)?\s*[=:]\s*(\d{4}-\d\d-\d\d[T ][0-9:.]+(?:Z|[+-]\d\d:\d\d)?)",
        text,
    )
    ends = re.findall(
        r"\bEND(?:ED)?(?:_UTC)?\s*[=:]\s*(\d{4}-\d\d-\d\d[T ][0-9:.]+(?:Z|[+-]\d\d:\d\d)?)",
        text,
    )
    steps = []
    for line in text.splitlines():
        explicit = re.search(
            r"\bSTEP\s+([A-Z0-9]+)\s+PGM=([A-Z0-9]+)(?:\s+PROCSTEP=([A-Z0-9]+))?\s+(?:RC=(\d{1,4})|ABEND=([SU][0-9A-F]{3,4}))",
            line,
        )
        if explicit:
            steps.append(
                dict(
                    step=explicit[1],
                    program=explicit[2],
                    procstep=explicit[3],
                    return_code=int(explicit[4]) if explicit[4] else None,
                    abend=explicit[5],
                )
            )
            continue
        ief = re.search(
            r"IEF142I\s+\S+\s+(\S+)(?:\s+(\S+))?\s+-\s+STEP WAS EXECUTED\s+-\s+COND CODE\s+(\d+)",
            line,
        )
        if ief:
            steps.append(
                dict(
                    step=ief[1],
                    program=None,
                    procstep=ief[2],
                    return_code=int(ief[3]),
                    abend=None,
                )
            )
        abnormal = re.search(
            r"IEF450I\s+\S+\s+(\S+)(?:\s+(\S+))?\s+-.*ABEND[= ]([SU][0-9A-F]{3,4})",
            line,
        )
        if abnormal:
            steps.append(
                dict(
                    step=abnormal[1],
                    program=None,
                    procstep=abnormal[2],
                    return_code=None,
                    abend=abnormal[3],
                )
            )
    banners = [
        line
        for line in (text + "\n" + compiler).splitlines()
        if re.search(r"z/OS|JES[23]|Language Environment|Enterprise COBOL", line, re.I)
    ]
    options = {
        name: sorted(
            set(
                re.findall(
                    r"\b" + name + r"\s*\(\s*([A-Z0-9]+)\s*\)",
                    compiler + "\n" + text,
                    re.I,
                )
            )
        )
        for name in ("NUMPROC", "TRUNC", "ARITH")
    }
    missing = []
    result = dict(
        schema="zos-run-observation/1",
        job_name=job[1] if job else None,
        job_id=job_id[0] if job_id else None,
        start=starts[0] if len(set(starts)) == 1 else None,
        end=ends[0] if len(set(ends)) == 1 else None,
        steps=steps,
        sysout_lines=[
            line[7:] for line in text.splitlines() if line.startswith("SYSOUT:")
        ],
        retained_output_lines=text.splitlines(),
        identity_banners=banners,
        compiler_options=options,
        source_sha256=sha(text.encode()),
        compiler_sha256=sha(compiler.encode()),
    )
    for key in ("job_name", "job_id", "start", "end", "steps", "identity_banners"):
        if not result[key]:
            missing.append(key)
    missing.extend("compiler." + key for key, value in options.items() if not value)
    result["missing"] = missing
    result["fingerprint"] = digest(dict(identity=banners, compiler_options=options))
    result["findings"] = [
        dict(
            code="step-nonzero",
            reason="Step has a non-zero return code or abend; investigate before comparison.",
            step=s["step"],
        )
        for s in steps
        if s["abend"] or s["return_code"] not in (None, 0)
    ]
    return result
