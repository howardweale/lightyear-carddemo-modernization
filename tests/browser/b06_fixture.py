"""Disposable zero-model B06 integration fixture, never a native qualification."""

import json
import sys
import threading
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from tests.test_b06_tower import B06Tests
from lightyear_control_tower.server import create_server
from lightyear_control_tower.status_export import StatusWriter
from lightyear_control_tower.decisions import canonical

fixture = B06Tests(
    "test_controller_publishes_pause_to_queue_and_consumes_exact_decision"
)
fixture.setUp()
fixture.launch()
for journey in ("J1", "J2", "J3"):
    fixture.finish(
        fixture.trial("cohort-" + journey + "-01", journey=journey, state="passed")
    )
fixture.pause("browser-equipment-pause")
exports = fixture.engine / "generic-export"
writer = StatusWriter(exports, fixture.sign, fixture.public, scope="ms94-b06")
writer.emit(
    {
        "campaign_id": "generic-demo",
        "at_utc": (fixture.now - timedelta(minutes=46)).isoformat(),
        "bindings": {"plan": fixture.bindings["plan"]},
        "state": "running",
        "active_trial": {"id": "sample-1"},
        "fixture": True,
        "limits": {"items": 10},
        "used": {"items": 1},
        "details": {},
    }
)
registry = fixture.root / "control-tower/campaigns.json"
config = json.loads(registry.read_bytes())
config["campaigns"].append(
    {
        "id": "generic-demo",
        "scope": "ms94-b06",
        "adapter": "tower-status-export",
        "producer_profile": "generic",
        "read_mode": "write-once-status",
        "export_directory": str(exports),
        "trusted_public_key": config["campaigns"][0]["trusted_public_key"],
        "bindings": {"plan": fixture.bindings["plan"]},
    }
)
registry.write_bytes(canonical(config))
server = create_server(fixture.s, port=0)
print(
    json.dumps({"port": server.server_port, "credential": fixture.f.credential}),
    flush=True,
)


def stop():
    sys.stdin.readline()
    server.shutdown()


threading.Thread(target=stop, daemon=True).start()
try:
    server.serve_forever()
finally:
    server.server_close()
    fixture.doCleanups()
