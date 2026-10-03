"""Disposable public-only intake workspace; never uses an operational authority."""

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from tests.test_carddemo_zos_tower import TowerIntakeTests
from lightyear_control_tower.server import create_server

fixture = TowerIntakeTests("test_four_kinds_and_read_only_arrivals")
fixture.setUp()
fixture.propose()
credential = (
    (Path(fixture.temp.name) / "authority/authority.credential.txt").read_text().strip()
)
server = create_server(fixture.s, port=0)
print(json.dumps(dict(port=server.server_port, credential=credential)), flush=True)


def stop_on_eof():
    sys.stdin.readline()
    server.shutdown()


threading.Thread(target=stop_on_eof, daemon=True).start()
try:
    server.serve_forever()
finally:
    server.server_close()
    fixture.doCleanups()
