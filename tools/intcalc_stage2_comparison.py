"""H3-B2 comparator. Production remains closed until a separately reviewed runtime route."""
import time

from tools import intcalc_hidden_answer_receiver as receiver
from tools import intcalc_stage2_admission as admission


BLOCKED = "stage2-private-clock-route-unqualified"
CHANNELS = receiver.writer.CHANNELS
FILES = ("ACCTFILE", "TRANSACT")
OUTPUT_BYTES = 8 * 1024 * 1024


class Refused(ValueError):
    pass


def check(ok):
    if not ok:
        raise Refused("stage2-comparison-refused")


def frame(raw, index):
    row=receiver.strict(raw, receiver.writer.CASE_CAP)
    check(receiver.writer.checked_case(row,index)==raw)
    return row


def matches(actual,expected):
    check(type(actual) is dict and set(actual)==set(CHANNELS)|{"exit","timed_out","output_capped"})
    check(type(actual["exit"]) is int and all(type(actual[k]) is bool for k in ("timed_out","output_capped")))
    for k in CHANNELS:
        v=actual[k]
        check((v is None and k in FILES) or (type(v) is bytes and len(v)<=OUTPUT_BYTES))
    if actual["timed_out"] or actual["output_capped"] or actual["exit"]!=expected["exit"]:
        return False
    relevant=CHANNELS if expected["compare_output_files"] else ("stdout","stderr")
    return all(actual[k]==bytes.fromhex(expected["outputs"][k]) for k in relevant)


def compare_all(frames, run_case, end, *, clock=time.monotonic):
    """Trusted in-memory routine. run_case accepts only a case's four inputs, clock strings and deadline."""
    try:
        check(type(frames) is list and 1<=len(frames)<=64)
        size=0
        for i,raw in enumerate(frames):
            check(clock()<end and type(raw) is bytes)
            size+=8+len(raw)
            check(size<=receiver.writer.STREAM_CAP)
            frame(raw,i)
        passed=True
        for i,raw in enumerate(frames):
            check(clock()<end)
            row=frame(raw,i)
            inputs={dd:bytes.fromhex(value) for dd,value in row["inputs"].items()}
            observed=run_case(inputs,row["timestamp"],row["processing_date"],end)
            check(clock()<end)
            if not matches(observed,row):
                passed=False
        check(clock()<end)
        return passed
    except (Exception, KeyboardInterrupt):
        raise Refused("stage2-comparison-refused") from None


def aggregate(passed):
    return admission.decision(passed)


class PrivateEvaluator:
    """Permanent refusal for the old #585 Docker command route. No switches or worker injection."""
    def preflight(self, material):
        raise Refused(BLOCKED)

    def compare(self, frames, material, end):
        raise Refused(BLOCKED)


def evaluate_private(raw, expected, evidence, host, age_binary):
    # Preserve the named reason at the outer edge; no call to B1 or any private IO.
    raise Refused(BLOCKED)
