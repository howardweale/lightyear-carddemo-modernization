#!/usr/bin/env python3
"""Render public attempt-journal metrics; no provider calls or qualification."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lightyear_factory.journal_metrics import (
    JournalBinding, MAX_JOURNAL_BYTES, MetricsError, _constant, _object,
    collect_cases, write_report,
)
from lightyear_factory.contracts import canonical_hash
from lightyear_factory.human_metrics import collect_human_events


def _read_source(root, name):
    relative = Path(name)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise MetricsError("metrics-source-path")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise MetricsError("metrics-source-outside-inventory")
    with target.open("rb") as stream:
        return stream.read(MAX_JOURNAL_BYTES + 1)


def render_inventory(inventory_path, output_path):
    inventory_path = Path(inventory_path)
    with inventory_path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise MetricsError("metrics-inventory-size")
    inventory = json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)
    required = {"schema", "case_ids", "exact_e", "journals"}
    if (not isinstance(inventory, dict) or not required <= set(inventory) or
            set(inventory) - required - {"human_events"} or
            inventory["schema"] != "factory-metrics-inventory/1" or
            not isinstance(inventory["journals"], list) or len(inventory["journals"]) > 1000):
        raise MetricsError("metrics-inventory-shape")
    root = inventory_path.resolve().parent
    sources = []
    total_bytes = 0
    for row in inventory["journals"]:
        if not isinstance(row, dict) or set(row) != {"path", "binding"}:
            raise MetricsError("metrics-inventory-journal")
        data = _read_source(root, row["path"])
        total_bytes += len(data)
        if total_bytes > 64 * 1024 * 1024:
            raise MetricsError("metrics-inventory-source-size")
        sources.append((JournalBinding(**row["binding"]), data))
    report = collect_cases(inventory["case_ids"], inventory["exact_e"], sources)
    if "human_events" in inventory:
        human = inventory["human_events"]
        if not isinstance(human, dict) or set(human) != {"path", "source_sha256", "campaign_id"}:
            raise MetricsError("metrics-human-inventory")
        data = _read_source(root, human["path"])
        if total_bytes + len(data) > 64 * 1024 * 1024:
            raise MetricsError("metrics-inventory-source-size")
        report["human_observations"] = collect_human_events(
            data, source_sha256=human["source_sha256"], campaign_id=human["campaign_id"],
            exact_e=inventory["exact_e"], case_ids=inventory["case_ids"])
        report["content_sha256"] = canonical_hash(report, {"content_sha256"})
    return write_report(Path(output_path), report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path, help="new output file; never overwritten")
    args = parser.parse_args()
    digest = render_inventory(args.inventory, args.output)
    print(json.dumps({"report_sha256": digest, "production_qualification": False}))


if __name__ == "__main__":
    main()
