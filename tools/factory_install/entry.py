"""Installed entry point: explicit commands, isolated Python, no implicit setup."""
import runpy
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / "src"))
sys.path.insert(1, str(APP))
if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in {"tower", "snapshot", "import", "check-consumer", "prepare-backfill"}:
        raise SystemExit("Choose tower, snapshot, import, or check-consumer")
    mode = sys.argv.pop(1)
    if mode == "prepare-backfill":
        import argparse
        from lightyear_control_tower.factory_import import historical_contract
        from lightyear_control_tower.decisions import canonical
        parser = argparse.ArgumentParser()
        parser.add_argument("--repository", type=Path, required=True)
        parser.add_argument("--commit", required=True)
        parser.add_argument("--output", type=Path, required=True)
        args = parser.parse_args()
        contract = historical_contract(args.repository, args.commit)
        if len(contract["details"]["records"]) != 7:
            raise SystemExit("Historical inventory changed; obtain a new review")
        with args.output.open("xb") as stream:
            stream.write(canonical(contract))
        print("Unsigned seven-record contract prepared; no authority accessed")
    elif mode == "check-consumer":
        from lightyear_factory.tower_authority import configured_authority
        authority = configured_authority()
        if authority is None or not authority.signed_only:
            raise SystemExit("Signed-only authority is not configured")
        print("Signed-only consumer verification passed")
    else:
        runpy.run_module({
            "tower": "lightyear_control_tower",
            "snapshot": "tools.import_factory_tower_snapshot",
            "import": "lightyear_control_tower.factory_import",
        }[mode], run_name="__main__")