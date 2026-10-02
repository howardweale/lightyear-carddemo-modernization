"""Engine-side catalogue generator. Never invoked by the Tower HTTP service."""

import argparse
import hashlib
from pathlib import Path
from lightyear_control_tower.console import ConsoleService
from lightyear_control_tower.catalogue import publish_record
from lightyear_control_tower.requests import read_json, confined
from lightyear_control_tower.decisions import canonical, verify_envelope


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--authority", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    args = p.parse_args(argv)
    service = ConsoleService(args.root, args.authority)
    try:
        data = read_json(args.input)
        with service.transaction() as db:
            events = service.events(db)
            head = events[-1]["content_sha256"]
            record = publish_record(
                data["entries"],
                scope=service.scope,
                decision_head=head,
                signer=service,
                current_bindings=data["current_bindings"],
            )
            for e in record["entries"]:
                path = confined(args.root, e["record"])
                raw = path.read_bytes()
                q = read_json(path)
                if (
                    hashlib.sha256(raw).hexdigest() != e["record_sha256"]
                    or not verify_envelope(q, service.public_key)
                    or q.get("scope") != service.scope
                ):
                    raise ValueError("Invalid qualification record")
            target = confined(args.root, "catalog/lanes.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(canonical(record))
            projection = {
                "catalogue_sha256": record["content_sha256"],
                "entries": [
                    {k: e[k] for k in ("id", "source_lane", "target_lane", "status")}
                    for e in record["entries"]
                ],
            }
            for relative in (
                "docs/catalogue/lanes.public.json",
                "website-any-system/data/catalogue.json",
            ):
                path = confined(args.root, relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(canonical(projection))
        print(record["content_sha256"])
    finally:
        service.close()


if __name__ == "__main__":
    main()
