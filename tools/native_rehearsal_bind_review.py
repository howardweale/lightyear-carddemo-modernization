"""Offline review-draft binding. Never executes the operator command sheet."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

KEYS = ("MAC_HOSTNAME", "MAC_STD_USER", "MAC_UID", "MAC_OS_BUILD",
        "USB_WIN_ROOT", "USB_MAC_VOLUME", "USB_VOLUME_LABEL")


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("timestamp-offset-required")
    return result


def validate_values(document):
    if set(document) != {"public_values", "received_at", "slot_start"}:
        raise ValueError("binding-fields")
    values = document["public_values"]
    if set(values) != set(KEYS):
        raise ValueError("seven-public-values-required")
    for name, value in values.items():
        # Restrictive literals are intentional: no shell expansion or quoting repair.
        if not isinstance(value, str) or not 1 <= len(value) <= 200:
            raise ValueError("public-value-shape")
        if not re.fullmatch(r"[A-Za-z0-9 _./:\\-]+", value) or value != value.strip():
            raise ValueError("unsafe-or-placeholder-value")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", values["MAC_HOSTNAME"]):
        raise ValueError("hostname-shape")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", values["MAC_STD_USER"]):
        raise ValueError("account-shape")
    if not re.fullmatch(r"[1-9][0-9]*", values["MAC_UID"]):
        raise ValueError("nonroot-uid-required")
    if not re.fullmatch(r"[A-Z]:\\", values["USB_WIN_ROOT"]):
        raise ValueError("windows-root-shape")
    volume = values["USB_MAC_VOLUME"]
    if not volume.startswith("/Volumes/") or len(volume.split("/")) != 3:
        raise ValueError("named-mac-volume-required")
    if volume.split("/")[-1] in (".", ".."):
        raise ValueError("volume-traversal")
    received, start = map(timestamp, (document["received_at"], document["slot_start"]))
    if not received < start or not 0 <= (start - received).total_seconds() <= 86400:
        raise ValueError("values-window")
    return values


def render(sheet, checklist, document):
    values = validate_values(document)
    if "NOT RUNNABLE" not in sheet or "NOT RUNNABLE" not in checklist:
        raise ValueError("draft-boundary-missing")
    for name in KEYS:
        marker = "<<" + name + ">>"
        if marker not in sheet:
            raise ValueError("template-marker-missing")
        sheet = sheet.replace(marker, values[name])
    # Explicit input, never today, a default slot, or execution authority.
    start = timestamp(document["slot_start"])
    sheet = sheet.replace("<<REHEARSAL_START>>", document["slot_start"])
    sheet = sheet.replace("<<REHEARSAL_DATE>>", start.date().isoformat())
    if "<<" in sheet:
        raise ValueError("unresolved-marker")
    # Slot is supplied, never inferred from this computer's clock.
    match = re.search(r"^REHEARSAL_START = (.+)$", sheet, re.M)
    if not match or timestamp(match[1]) != timestamp(document["slot_start"]):
        raise ValueError("slot-template-mismatch")
    return sheet, checklist


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--values", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.values.read_text(encoding="utf8"))
    template = json.loads((args.template / "BINDING-VALUES.json").read_text(encoding="utf8"))
    if (template["values_not_before"] is not None or
            template["rehearsal_start"] is not None or
            template["slot_policy"]["maximum_values_age_seconds"] != 86400):
        raise ValueError("readiness-template-mismatch")
    sheet = (args.template / "COMMAND-SHEET.txt").read_text(encoding="utf8")
    checklist = (args.template / "RETURN-CHECKLIST.txt").read_text(encoding="utf8")
    sheet, checklist = render(sheet, checklist, document)
    args.output.mkdir()  # Exclusive directory; never overwrite or remove partials.
    hashes = {}
    for name, text in (("COMMAND-SHEET.txt", sheet), ("RETURN-CHECKLIST.txt", checklist)):
        raw = text.encode("utf8")
        with (args.output / name).open("xb") as stream:
            stream.write(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    review = dict(schema="no-key-bound-review-draft/1", execution_approved=False,
                  ready=False, native_proof=False, values=document, sha256=hashes,
                  next="Exact new-head Claude review, then Howard approval; no execution")
    with (args.output / "binding-review.json").open("x", encoding="utf8") as stream:
        json.dump(review, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
