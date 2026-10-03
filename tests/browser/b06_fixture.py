"""Disposable zero-model B06 integration fixture, never a native qualification."""

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from tests.test_b06_tower import B06Tests
from lightyear_control_tower.server import create_server

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
