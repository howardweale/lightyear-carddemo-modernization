"""Public CardDemo fixed-record inspection; no equivalence or qualification rules.

Uses the existing strict decoder and pinned job/step/DD bindings. No business
program, provider, signing, admission or process-launch operation is performed.
"""
from collections import Counter
import hashlib
from pathlib import Path

from .records import decode_fixed, decode_text_lines, load_copybook
from .zos_bindings import ROOT, dataset_binding, load_bindings

UPSTREAM = "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e"
JOBS = ("POSTTRAN", "INTCALC", "TRANREPT")
MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10000


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _binding(job, step, dd):
    if job not in JOBS:
        raise ValueError("public-carddemo-job-required")
    bindings = load_bindings()
    if bindings["source_commit"] != UPSTREAM:
        raise ValueError("public-carddemo-source-drift")
    binding = dataset_binding(bindings, job, step, dd)
    if binding["recfm"] not in ("F", "FB"):
        raise ValueError("fixed-record-binding-required")
    return binding


def _decode(raw, binding, codec):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("bounded-binary-input-required")
    length = binding["record_length"]
    if len(raw) % length:
        raise ValueError("partial-fixed-record")
    if len(raw) // length > MAX_RECORDS:
        raise ValueError("record-count-limit")
    if codec not in ("cp037", "cp500", "cp1140"):
        raise ValueError("explicit-supported-ebcdic-codec-required")
    if binding["mode"] == "records":
        layout = load_copybook(ROOT / binding["copybook"])
        return decode_fixed(layout, raw, codec=codec)
    if binding["mode"] == "text":
        # TRANREPT is FB133, not guessed FBA or line-oriented ASCII.
        return decode_text_lines(raw, record_length=length, codec=codec, asa=False)
    raise ValueError("unsupported-dataset-mode")


def decode_dataset(job, step, dd, raw, *, codec):
    binding = _binding(job, step, dd)
    return dict(schema="public-carddemo-fixed-records/1", job=job, step=step, dd=dd,
                source_commit=UPSTREAM, dataset=binding["dataset"],
                record_length=binding["record_length"], codec=codec,
                input_sha256=digest(raw), input_bytes=len(raw),
                records=_decode(raw, binding, codec), qualified=False)


def compare_dataset(job, step, dd, before, after, *, codec, detail_limit=1000):
    """Exact keyed differences, with positional text comparison and byte identity.

    No timestamp/filler/blank/sign normalization. Duplicate keys are refused.
    Reordering is reported separately; it never becomes byte-identical.
    Detail truncation is explicit even though complete counts are retained.
    """
    if type(detail_limit) is not int or not 0 <= detail_limit <= 10000:
        raise ValueError("invalid-detail-limit")
    binding = _binding(job, step, dd)
    left, right = _decode(before, binding, codec), _decode(after, binding, codec)

    def index(records):
        result, order = {}, []
        for number, row in enumerate(records):
            fields = {f["path"]: f for f in row["fields"]}
            if len(fields) != len(row["fields"]):
                raise ValueError("duplicate-field-path")
            key = tuple(fields[k]["value"] for k in binding["keys"]) if binding["keys"] else (number,)
            if key in result:
                raise ValueError("duplicate-record-key")
            result[key] = row
            order.append(key)
        return result, order

    a, order_a = index(left)
    b, order_b = index(right)
    added, deleted = sorted(b.keys()-a.keys()), sorted(a.keys()-b.keys())
    changes, field_counts, changed = [], Counter(), 0
    omitted = 0

    def retain(row):
        nonlocal omitted
        if len(changes) < detail_limit:
            changes.append(row)
        else:
            omitted += 1

    for key in added:
        retain(dict(kind="added", key=list(key), after_record_sha256=b[key]["record_sha256"]))
    for key in deleted:
        retain(dict(kind="deleted", key=list(key), before_record_sha256=a[key]["record_sha256"]))
    for key in sorted(a.keys() & b.keys()):
        fa = {f["path"]: f for f in a[key]["fields"]}
        fb = {f["path"]: f for f in b[key]["fields"]}
        if fa.keys() != fb.keys():
            raise ValueError("field-layout-drift")
        differences = []
        for path in sorted(fa):
            x, y = fa[path], fb[path]
            if x["raw_hex"] != y["raw_hex"]:
                field_counts[path] += 1
                differences.append(dict(path=path, filler=x["filler"],
                    before_value=x["value"], after_value=y["value"],
                    before_hex=x["raw_hex"], after_hex=y["raw_hex"],
                    value_changed=x["value"] != y["value"]))
        if differences:
            changed += 1
            retain(dict(kind="changed", key=list(key),
                before_record_sha256=a[key]["record_sha256"],
                after_record_sha256=b[key]["record_sha256"], fields=differences))
    return dict(schema="public-carddemo-dataset-delta/1", source_commit=UPSTREAM,
        job=job, step=step, dd=dd, dataset=binding["dataset"], codec=codec,
        record_length=binding["record_length"], keys=binding["keys"],
        comparison="keyed-exact-field-bytes" if binding["keys"] else "positional-exact-text-bytes",
        before_sha256=digest(before), after_sha256=digest(after),
        before_records=len(left), after_records=len(right),
        added_records=len(added), deleted_records=len(deleted), changed_records=changed,
        field_change_counts=dict(sorted(field_counts.items())),
        order_changed=order_a != order_b, identical=before == after,
        keyed_identical=not added and not deleted and changed == 0,
        details=changes, omitted_detail_rows=omitted, details_complete=omitted == 0,
        qualified=False, production_controller_receipt=False,
        limits="Public data inspection; no business-program equivalence or native/P5 receipt")


def compare_snapshots(job, before, after, *, codec, detail_limit=1000):
    """Compare explicitly supplied (step, DD) maps; missing is never empty."""
    if job not in JOBS or not isinstance(before, dict) or not isinstance(after, dict):
        raise ValueError("job-and-snapshot-maps-required")
    if not before or before.keys() != after.keys():
        raise ValueError("snapshot-inventory-mismatch")
    if any(not isinstance(k, tuple) or len(k) != 2 or
           any(not isinstance(v, str) for v in k) for k in before):
        raise ValueError("step-dd-key-required")
    rows = [compare_dataset(job, step, dd, before[(step, dd)], after[(step, dd)],
                            codec=codec, detail_limit=detail_limit)
            for step, dd in sorted(before)]
    return dict(schema="public-carddemo-snapshot-delta/1", job=job, source_commit=UPSTREAM,
                datasets=rows, identical=all(r["identical"] for r in rows),
                scope="Only supplied datasets; not a complete job-output inventory",
                qualified=False, production_controller_receipt=False)
