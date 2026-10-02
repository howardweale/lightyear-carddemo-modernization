"""Disposable decision-only UI fixture. No engine, database pair or model client."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from tests.test_decision_console import ConsoleTests
from lightyear_control_tower.server import create_server
from lightyear_control_tower.decisions import canonical

fixture = ConsoleTests("test_provision_no_roles_and_role_changes_journaled")
fixture.setUp()
folder = fixture.root / "control-tower"
folder.mkdir(exist_ok=True)
source = ROOT / "tests/fixtures/decision-console/b04"
(folder / "campaigns.json").write_bytes(
    canonical(
        {
            "campaigns": [
                {
                    "scope": "demo",
                    "id": "B04 archive fixture — VOID",
                    "adapter": "ms94-stage-b",
                    "root": str(source),
                    "published_directory": str(source / "published"),
                    "work_directory": str(source / "work/ms94/stage-b-04"),
                    "trusted_public_key": str(source / "authority.public.pem"),
                }
            ]
        }
    )
)
# Safe URL identifier; display labels are presentation, never path input.
registry = json.loads((folder / "campaigns.json").read_bytes())
registry["campaigns"][0]["id"] = "b04-archive-fixture"
(folder / "campaigns.json").write_bytes(canonical(registry))
server = create_server(fixture.service, port=0)
print(
    json.dumps({"port": server.server_port, "credential": fixture.credential}),
    flush=True,
)
try:
    server.serve_forever()
finally:
    server.server_close()
    fixture.doCleanups()
