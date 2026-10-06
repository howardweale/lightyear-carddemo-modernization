"""Disposable public projection review; never uses a live authority."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from verify_graph_support import GraphFixture, leak_check, digest, sha
from lightyear_judge.graph_cli import request
from lightyear_control_tower.console import ConsoleService, provision
from lightyear_control_tower.server import create_server

f = GraphFixture()
f.setUp()
try:
    m = f.build()
    report = leak_check(f.out, digest(f.lane), {"ACCOUNT-FILE"}, f.signer,
                        evaluation_inventory_sha256=digest({}), approved_source="SELECT ACCOUNT-FILE")
    tower = f.root / "tower"
    tower.mkdir()
    authority = f.root / "authority" / "authority.json"
    credential = provision(authority, "verify-review-test", "reviewer", "Test reviewer").read_text().strip()
    console = ConsoleService(tower, authority)
    f.addCleanup(console.close)
    console.grant_roles("reviewer", ["operator", "qualification-approver"], reason="Synthetic browser test")
    request(tower, "verify-review-test", f.out, f.policy, f.lane, m, report)
    server = create_server(console, port=0)
    print(json.dumps(dict(port=server.server_port, credential=credential,
                         acknowledgment="source-literal:" + sha(b"ACCOUNT-FILE"))), flush=True)
    server.serve_forever()
finally:
    f.doCleanups()
