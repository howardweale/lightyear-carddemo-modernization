from __future__ import annotations

from types import ModuleType
import importlib.util
import json
from pathlib import Path
import sys


def policy_checks(candidate: ModuleType) -> dict[str, bool]:
    compact = candidate.format_date("1", "20260821", "1")
    hyphenated = candidate.format_date("2", "2026-08-21", "2")
    invalid_type = candidate.format_date("9", "20260821", "1")
    invalid_pair = candidate.format_date("1", "20260821", "2")
    source_quirk = candidate.format_date("2", "2026/08/21", "2")
    return {
        "program_identity": candidate.PROGRAM_ID == "COBDATFT",
        "dsect_lengths": (
            candidate.INPUT_DATE_LENGTH,
            candidate.OUTPUT_DATE_LENGTH,
            candidate.ERROR_LENGTH,
        ) == (20, 20, 38),
        "compact_to_hyphenated": compact["output_date"] == "2026-08-21".ljust(20),
        "hyphenated_to_compact": hyphenated["output_date"] == "20260821".ljust(20),
        "invalid_type_fails_closed": invalid_type["error_message"].strip() == "INVALID INPUT",
        "invalid_direction_fails_closed": invalid_pair["error_message"].strip() == "INVALID INPUT",
        "commented_separator_check_is_preserved": source_quirk["output_date"] == "20260821".ljust(20),
    }


def all_checks_pass(candidate: ModuleType) -> bool:
    return all(policy_checks(candidate).values())


def main() -> int:
    path = Path(__file__).resolve().parents[2] / "factory/benchmarks/asm_date_candidate.py"
    spec = importlib.util.spec_from_file_location("factorydark_asm_candidate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("ASM candidate cannot be loaded")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    checks = policy_checks(candidate)
    print(json.dumps({"checks": checks, "status": "passed" if all(checks.values()) else "failed"}, indent=2, sort_keys=True))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
