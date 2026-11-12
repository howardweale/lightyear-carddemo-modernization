#!/usr/bin/env python3
"""Print A-F from receipts and separately approved rule/catalog digest bindings."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lightyear_factory.qualified_run_report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path, help="new JSON report; never overwritten")
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--rules-sha256", required=True, help="digest from approved dated rules")
    parser.add_argument("--catalog-sha256", help="digest from separately approved frozen behaviour catalog")
    args = parser.parse_args()
    report = write_report(args.bundle, args.output, rules_path=args.rules,
                          rules_sha256=args.rules_sha256, catalog_sha256=args.catalog_sha256)
    count = report["passed_cases"]
    print(f'{report["tier"]}. {report["tier_name"]}')
    print(f'Cases passing every frozen condition: {count}/{report["case_denominator"]}'
          if count is not None else 'Pass count unavailable or not applicable; see reasons.')
    for reason in report["reasons"]:
        print(reason)
    return 1 if report["tier"] == "F" else 0


if __name__ == "__main__":
    raise SystemExit(main())
