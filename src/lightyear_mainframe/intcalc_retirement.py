"""Fail-closed retirement boundary for all legacy INTCALC execution routes."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "spec/intcalc-retirement/2026-11-15/ENFORCEMENT.json"
REGISTRY_SHA256 = "bdb3c10c15bc9a322859e4e4efedf24ac611a41525d77a57ea6642fbdff849d9"
RECORD_SHA256 = "a4e3e799ab3780f7115b1b5cd3aeae73f27480f43eb632a5946dd919a7ae76f0"


def require_current(error_type=ValueError):
    # No parameters for an alternate registry, profile, clock or bypass.
    try:
        current = ROOT
        for part in REGISTRY.relative_to(ROOT).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError()
        raw = REGISTRY.read_bytes()
        if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA256:
            raise ValueError()
        row = json.loads(raw.decode("utf-8"))
        record = REGISTRY.with_name("RETIREMENT.json")
        if record.is_symlink() or hashlib.sha256(record.read_bytes()).hexdigest() != RECORD_SHA256:
            raise ValueError()
        if row["state"] != "LEGACY_INTCALC_CLOSED" or row["replacement_profiles"] != []:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise error_type("retirement-registry-invalid") from None
    raise error_type("retired-verifier-set")


def main():
    try:
        require_current()
    except ValueError as error:
        print(str(error))
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
