from __future__ import annotations

import argparse
from pathlib import Path

from .trust import audit_receipt_claims, audit_script_catalog, validate_upstream_fixture


def _report(label: str, errors: list[str]) -> int:
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"{label}: passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LIGHTYEAR repository trust-boundary controls")
    parser.add_argument("command", choices=("doctor", "prerequisites", "receipt-claims", "scripts"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    checks = {
        "prerequisites": lambda: validate_upstream_fixture(args.project_root),
        "receipt-claims": lambda: audit_receipt_claims(args.project_root),
        "scripts": lambda: audit_script_catalog(args.project_root),
    }
    if args.command == "doctor":
        errors = []
        for check in checks.values():
            errors.extend(check())
        return _report("Repository trust doctor", errors)
    return _report(args.command, checks[args.command]())


if __name__ == "__main__":
    raise SystemExit(main())
