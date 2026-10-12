"""Disposable public Factory UI fixture; no live authority or runtime access."""
import json
import tempfile
from pathlib import Path
from lightyear_control_tower.console import provision,ConsoleService
from lightyear_control_tower.server import create_server
from lightyear_control_tower.decisions import canonical
from tests.test_decision_console_factory_views import fixture_snapshot

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)/"data";root.mkdir()
    authority=Path(folder)/"authority/authority.json"
    credential=provision(authority,"factory","fixture","Public UI fixture").read_text().strip()
    service=ConsoleService(root,authority)
    service.grant_roles("fixture",["operator"],reason="Disposable public screenshot fixture")
    pin=fixture_snapshot(root)
    (authority.parent/"factory-evidence-trust.json").write_bytes(canonical(dict(schema="factory-evidence-trust/1",index_sha256=pin)))
    server=create_server(service,port=0)
    print(json.dumps(dict(port=server.server_port,credential=credential)),flush=True)
    try:server.serve_forever()
    finally:server.server_close();service.close()
