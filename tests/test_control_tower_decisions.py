from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import tempfile
import threading
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lightyear_control_tower.decisions import (
    DecisionService, DecisionConflict, DecisionUnauthorized, WORKLOAD,
    initialize_authority, verify_envelope, utcnow, digest,
)
from lightyear_control_tower.cli import main
from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
from lightyear_knowledge_graph.model import load_graph

ROOT = Path(__file__).resolve().parents[1]


class DecisionTests(unittest.TestCase):
    def setUp(self):
        if importlib.util.find_spec("cryptography") is None:
            self.skipTest("Install .[control-tower] to run signing tests; dedicated decision CI requires it")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("src/lightyear_factory", "src/lightyear_common", "src/carddemo_oracle", "factory/benchmarks"):
            shutil.copytree(ROOT / directory, self.root / directory, ignore=shutil.ignore_patterns('__pycache__'))
        (self.root / "spec").mkdir()
        shutil.copyfile(ROOT / "spec/comparison-normalizations.json", self.root / "spec/comparison-normalizations.json")
        self.authority = self.root / "work/control-tower/authority.json"
        credential = initialize_authority(self.authority, "test-operator", "Test Operator")
        self.credential = credential.read_text().strip()
        self.service = DecisionService(self.root, self.authority, graph_identity=lambda: "graph-test")
        self.addCleanup(self.service.close)
        self.session = self.service.login(self.credential)
        self.token = self.session["token"]

    def approval_payload(self, entry_id=None):
        item = self.service.queue(self.token)["items"][0]
        if entry_id:
            item = next(i for i in self.service.queue(self.token)["items"] if i["id"] == entry_id)
        self.service.review(self.token, item["id"])
        return {"entry_id": item["id"], "entry_sha256": item["entry_sha256"], "ledger_sha256": item["ledger_sha256"],
                "previous_decision_sha256": (item["latest_decision"] or {}).get("content_sha256"),
                "outcome": "approved", "reason": "Test fixture: exact value semantics remain preserved.", "owner": "Test Owner",
                "review_after": (utcnow().date() + timedelta(days=2)).isoformat(), "request_id": str(uuid.uuid4())}

    def run_proof(self):
        run = self.service.dispatch(self.token, {"workload_id": WORKLOAD, "request_id": str(uuid.uuid4())})
        self.service.workers[-1].join(10)
        self.assertFalse(self.service.workers[-1].is_alive())
        return run["run_id"]

    def approve_all(self):
        for item in self.service.queue(self.token)["items"]:
            self.service.decide(self.token, self.approval_payload(item["id"]))

    def test_real_proof_cannot_pass_gate_without_all_signed_decisions(self):
        run_id = self.run_proof()
        self.assertEqual("passed", self.service.queue(self.token)["runs"][0]["status"])
        gate = self.service.gate(run_id)
        self.assertEqual("blocked", gate["status"])
        self.assertEqual(3, len(gate["reason_codes"]))
        self.approve_all()
        gate = self.service.gate(run_id)
        self.assertEqual("passed", gate["status"])
        self.assertEqual(3, len(gate["approval_records"]))
        self.assertTrue(verify_envelope(gate, self.service.public_key))
        self.assertFalse(gate["human_promotion_authorized"])
        self.assertFalse(gate["ms68_complete"])
        self.assertFalse(gate["production_ready"])

    def test_decisions_require_review_and_identity_is_not_supplied_by_browser(self):
        payload = self.approval_payload()
        other = self.service.login(self.credential)
        with self.assertRaises(DecisionConflict):
            self.service.decide(other["token"], payload)
        payload["actor"] = {"name": "Forged Approver"}
        record = self.service.decide(self.token, payload)
        self.assertEqual("Test Operator", record["actor"]["name"])
        self.assertTrue(verify_envelope(record, self.service.public_key))

    def test_role_authorization_and_expiring_sessions(self):
        self.service.sessions[self.token]["roles"] = []
        with self.assertRaises(DecisionUnauthorized):
            self.service.decide(self.token, {})
        with self.assertRaises(DecisionUnauthorized):
            self.service.dispatch(self.token, {})
        with patch('lightyear_control_tower.decisions.utcnow', return_value=utcnow() + timedelta(hours=2)):
            with self.assertRaises(DecisionUnauthorized):
                self.service.queue(self.token)

    def test_missing_reason_owner_or_date_is_rejected(self):
        for field in ("reason", "owner", "review_after"):
            payload = self.approval_payload(); payload[field] = ""
            with self.assertRaises(ValueError):
                self.service.decide(self.token, payload)

    def test_duplicate_request_returns_same_signature_and_conflicting_retry_fails(self):
        payload = self.approval_payload()
        first = self.service.decide(self.token, payload)
        self.assertEqual(first, self.service.decide(self.token, payload))
        payload["reason"] = "Different decision"
        with self.assertRaises(DecisionConflict):
            self.service.decide(self.token, payload)

    def test_concurrent_decision_does_not_overwrite_newer_record(self):
        first = self.approval_payload(); second = {**first, "request_id": str(uuid.uuid4())}
        records = []; errors = []
        def decide(payload):
            try: records.append(self.service.decide(self.token, payload))
            except DecisionConflict as error: errors.append(error)
        threads = [threading.Thread(target=decide, args=(payload,)) for payload in (first, second)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(1, len(records)); self.assertEqual(1, len(errors))

    def test_ledger_change_invalidates_approval_and_stale_form(self):
        payload = self.approval_payload(); self.service.decide(self.token, payload)
        path = self.root / 'spec/comparison-normalizations.json'
        ledger = json.loads(path.read_text()); ledger['rules'][0]['reason'] = 'A revised rationale'
        path.write_text(json.dumps(ledger))
        self.assertEqual('changed', self.service.queue(self.token)['items'][0]['status'])
        payload['request_id'] = str(uuid.uuid4())
        with self.assertRaises(DecisionConflict): self.service.decide(self.token, payload)

    def test_expiry_rejection_and_code_change_block_gate(self):
        run_id = self.run_proof(); self.approve_all()
        with patch('lightyear_control_tower.decisions.utcnow', return_value=utcnow() + timedelta(days=3)):
            self.assertEqual('blocked', self.service.gate(run_id)['status'])
        payload = self.approval_payload(); payload['outcome'] = 'rejected'; payload['review_after'] = None
        self.service.decide(self.token, payload)
        self.assertTrue(any('normalization-rejected' in reason for reason in self.service.gate(run_id)['reason_codes']))
        candidate = self.root / 'factory/benchmarks/intcalc_candidate.py'
        candidate.write_text(candidate.read_text() + '\n# changed source\n')
        self.assertIn('proof-inputs-changed', self.service.gate(run_id)['reason_codes'])

    def test_failed_proof_is_never_admitted_even_with_approvals(self):
        candidate = self.root / 'factory/benchmarks/intcalc_candidate.py'
        candidate.write_text('raise RuntimeError("test failure")\n')
        run_id = self.run_proof(); self.approve_all()
        self.assertIn('proof-not-passed', self.service.gate(run_id)['reason_codes'])

    def test_unknown_workload_and_injection_are_rejected(self):
        with self.assertRaises(ValueError):
            self.service.dispatch(self.token, {'workload_id': 'cloudbank; touch bad', 'request_id': str(uuid.uuid4()), 'command': ['true']})
        self.assertEqual([], self.service.queue(self.token)['runs'])

    def test_proof_is_idempotent_and_survives_service_restart(self):
        payload = {'workload_id': WORKLOAD, 'request_id': str(uuid.uuid4())}
        first = self.service.dispatch(self.token, payload)
        second = self.service.dispatch(self.token, payload)
        self.assertEqual(first['run_id'], second['run_id'])
        self.service.workers[-1].join(10)
        self.service.close()
        reloaded = DecisionService(self.root, self.authority, graph_identity=lambda: 'graph-test')
        self.addCleanup(reloaded.close)
        self.assertEqual('blocked', reloaded.gate(first['run_id'])['status'])
        with self.assertRaises(DecisionUnauthorized): reloaded.queue(self.token)

    def test_tampered_journal_and_wrong_public_key_fail_closed(self):
        self.service.decide(self.token, self.approval_payload())
        exported = self.service.export_session(self.token)
        changed = copy.deepcopy(exported); changed['events'][-1]['payload']['reason'] = 'tampered'
        self.assertFalse(verify_envelope(changed, self.service.public_key))
        self.assertFalse(verify_envelope(exported, b'wrong key'))
        with self.service.connect() as db:
            event = json.loads(db.execute('SELECT envelope FROM events WHERE sequence=1').fetchone()[0])
            event['actor']['name'] = 'tampered'
            db.execute('UPDATE events SET envelope=? WHERE sequence=1', (json.dumps(event),))
        with self.assertRaisesRegex(ValueError, 'integrity'): self.service.queue(self.token)

    def test_public_key_verifies_export_and_no_secret_is_exported(self):
        self.service.decide(self.token, self.approval_payload())
        record = self.service.export_session(self.token)
        self.assertNotIn(self.token, json.dumps(record)); self.assertNotIn(self.credential, json.dumps(record))
        record_path = self.root / 'session.json'; record_path.write_text(json.dumps(record))
        result = main(['verify-session', '--record', str(record_path), '--trusted-public-key', str(self.authority.with_suffix('.public.pem'))])
        self.assertEqual(0, result)
        self.service.logout(self.token)
        with self.assertRaises(DecisionUnauthorized): self.service.queue(self.token)
        with self.service.connect() as db: self.assertEqual('session_ended', self.service.events(db)[-1]['kind'])

    def test_second_writer_is_refused_but_qualification_can_read(self):
        with self.assertRaisesRegex(ValueError, 'Another decision service'):
            DecisionService(self.root, self.authority)
        verifier = DecisionService(self.root, self.authority, recover_runs=False)
        self.addCleanup(verifier.close)
        self.assertTrue(verifier.public_key)

    def test_authority_cannot_be_silently_replaced(self):
        with self.assertRaises(ValueError): initialize_authority(self.authority, 'another', 'Another Person')


class DecisionHTTPTests(unittest.TestCase):
    setUp = DecisionTests.setUp

    def test_http_authentication_origin_and_real_dispatch(self):
        index = GraphExplorerIndex(load_graph(ROOT / 'knowledge/graph.snapshot.json.gz'))
        server = ExplorerServer(('127.0.0.1', 0), index, ROOT / 'knowledge/viewer', decision_service=self.service)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'
        def call(route, data=None, headers=None):
            headers = {'Content-Type': 'application/json', **(headers or {})}
            req = Request(origin + '/api/decisions/' + route, data=json.dumps(data).encode() if data is not None else None, headers=headers)
            with urlopen(req, timeout=5) as response: return json.load(response)
        self.assertTrue(call('status')['enabled'])
        with self.assertRaises(HTTPError) as error: call('queue')
        self.assertEqual(401, error.exception.code)
        for bad_origin in ('https://attacker.invalid', None):
            with self.assertRaises(HTTPError) as error: call('session', {'credential': self.credential}, {'Origin': bad_origin} if bad_origin else {})
            self.assertEqual(401, error.exception.code)
        session = call('session', {'credential': self.credential}, {'Origin': origin})
        headers = {'Origin': origin, 'Authorization': 'Bearer ' + session['token']}
        self.assertEqual(3, len(call('queue', headers=headers)['items']))
        run = call('proof-runs', {'workload_id': WORKLOAD, 'request_id': str(uuid.uuid4())}, headers)
        self.service.workers[-1].join(10)
        gate = call('gate?run_id=' + run['run_id'], headers=headers)
        self.assertEqual('blocked', gate['status'])
        with self.assertRaises(HTTPError) as error: call('queue', headers={**headers, 'Host': 'attacker.invalid'})
        self.assertEqual(401, error.exception.code)


if __name__ == '__main__':
    unittest.main()
