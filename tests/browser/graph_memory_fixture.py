"""Disposable public/synthetic memory Console. No models, Docker or live authority."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
from test_graph_memory import MemoryTests
from lightyear_factory.annotations import leak_certificate
from lightyear_factory.annotation_tools import governor_requests
from lightyear_factory.knowledge_service import KnowledgeService
from lightyear_control_tower.decisions import canonical
from lightyear_control_tower.server import create_server

f = MemoryTests()
f.setUp()
try:
    a = f.create()
    cert = leak_certificate(a, [], f.judge, inventory_sha256="a" * 64)
    requests = governor_requests(f.ledger, f.root, "graph-memory", {a["id"]: cert})
    evidence = f.root / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "ledger.public.pem").write_bytes(f.signer.public)
    (evidence / "judge.public.pem").write_bytes(f.judge.public)
    (evidence / "status.json").write_bytes(
        canonical(KnowledgeService(f.ledger, f.signer, f.root).status())
    )
    (f.root / "factory").mkdir()
    (f.root / "factory/knowledge-console.json").write_bytes(
        canonical(
            dict(
                scope="graph-memory",
                status_file="evidence/status.json",
                public_key="evidence/ledger.public.pem",
                judge_public_key="evidence/judge.public.pem",
                inventory_sha256="a" * 64,
            )
        )
    )
    server = create_server(f.console, port=0)
    credential = (
        f.console.authority_path.with_suffix(".credential.txt").read_text().strip()
    )
    print(
        json.dumps(
            dict(
                port=server.server_port,
                credential=credential,
                request_id=requests[0]["id"],
            )
        ),
        flush=True,
    )
    server.serve_forever()
finally:
    f.doCleanups()
