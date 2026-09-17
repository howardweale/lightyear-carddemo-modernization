from contextlib import closing
import sqlite3
from datetime import datetime, timedelta, timezone
import json
import importlib.util
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from lightyear_control_tower.decisions import DecisionUnauthorized, canonical, verify_envelope
from lightyear_data.oracle_number_native import EXPECTED, number_cases, probes
from lightyear_workflow import campaign_engine as engine
from lightyear_workflow.campaign_service import CampaignService, history, initialize, list_runs
from lightyear_workflow.paired_number import PROFILE, compare, parse_observation, plan, postgres_case
from lightyear_workflow.run_store import RunStore

ROOT = Path(__file__).resolve().parents[1]


class SimulatedRunner:
    evidence_class = "simulated"
    def __init__(self, root, run_id, proposed, emit): self.emit = emit
    def prepare(self): pass
    def identities(self):
        return {lane: {"evidence_class": self.evidence_class, "version": "test-only"} for lane in ("oracle", "alloydb")}
    def observe(self, lane, case):
        result = {p: EXPECTED[p] for p in probes(case)}
        if lane == "alloydb" and "overflow_code" in result: result["overflow_code"] = "22003"
        return result
    def cleanup(self): return {"complete": True, "resources": {"test": "simulated"}}


class PairedCampaignTests(unittest.TestCase):
    def setUp(self):
        if importlib.util.find_spec("cryptography") is None:
            self.skipTest("Install .[control-tower] to run signing tests; dedicated decision CI requires it")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for path in ("src", "data-modernization/oracle-core-sql-coverage", "data-modernization/oracle-native-execution-gate/cases"):
            shutil.copytree(ROOT / path, self.root / path, ignore=shutil.ignore_patterns("__pycache__"))
        credential = initialize(self.root, "operator", "Test Operator")
        self.service = CampaignService(self.root, dispatcher=lambda *_: None)
        self.addCleanup(self.service.close)
        self.token = self.service.login(credential.read_text(encoding="utf-8").strip())["token"]
        (self.root / PROFILE).write_text(json.dumps({"oracle_image": "container-registry.oracle.com/database/free@sha256:" + "1"*64,
                 "budget_usd": 10, "estimated_hourly_usd": 2, "max_seconds": 3600, "runner_zone": "us-west1-a"}), encoding="utf-8")

    def request(self):
        return {"plan_sha256": plan(self.root)["plan_sha256"], "request_id": str(uuid.uuid4()),
                "accept_terms": True, "reason": "Approve the exact synthetic test contract"}

    def start(self): return self.service.start(self.token, self.request())["run_id"]

    def test_oracle_output_enabled_in_selected_container(self):
        from lightyear_workflow.campaign_gcp import GcpRunner
        case = number_cases(self.root)[0]
        with patch('lightyear_workflow.campaign_gcp.shutil.which', return_value='gcloud'):
            runner = GcpRunner(self.root, 'number-' + '1'*32, plan(self.root), lambda *_: None)
        def container_scoped_output(lane, sql):
            self.assertEqual(lane, 'oracle')
            if sql.index('SET SERVEROUTPUT ON') < sql.index('ALTER SESSION SET CONTAINER'):
                return ''  # Root package state does not enable PDB output.
            return 'LY_NUMBER_OBSERVATION=' + json.dumps({'case_id': case['id'], 'observations': {p: EXPECTED[p] for p in probes(case)}})
        with patch.object(runner, 'sql', side_effect=container_scoped_output):
            self.assertEqual(runner.observe('oracle', case), {p: EXPECTED[p] for p in probes(case)})

    def test_roles_scope_terms_and_duplicate_submission(self):
        request = self.request()
        with self.assertRaises(ValueError): self.service.start(self.token, {**request, "accept_terms": False})
        with self.assertRaises(ValueError): self.service.start(self.token, {**request, "plan_sha256": "0"*64})
        with self.assertRaises(DecisionUnauthorized): self.service.start("not-a-session", request)
        self.service.authority.sessions[self.token]["roles"] = ["normalization-approver"]
        with self.assertRaises(DecisionUnauthorized): self.service.start(self.token, request)
        self.service.authority.sessions[self.token]["roles"] = ["campaign-approver"]
        with patch.object(self.service, "dispatcher") as dispatch:
            first = self.service.start(self.token, request)
            second = self.service.start(self.token, request)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(dispatch.call_count, 1)
        with self.assertRaisesRegex(ValueError, "active"):
            self.service.start(self.token, self.request())

    def test_simulated_receipt_never_acquires_native_status_and_reads_do_not_write(self):
        run_id = self.start()
        result = engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        self.assertEqual(result["status"], "passed-simulated")
        self.assertEqual(result["matched"], 20)
        self.assertEqual(result["source_completed"], 20)
        self.assertNotEqual(result["evidence_class"], "native-database-observed")
        journal = engine.run_path(self.root, run_id) / "events.sqlite3"
        before = journal.read_bytes()
        self.assertEqual(engine.read_run(self.root, run_id)["status"], "passed-simulated")
        self.assertEqual(journal.read_bytes(), before)
        with patch.object(RunStore, "events", side_effect=AssertionError("History must not open journals")):
            self.assertEqual(history(self.root)["runs"][0]["status"], "passed-simulated")
            self.assertTrue(verify_envelope(history(self.root)["runs"][0], engine.public_key(self.root)))
            self.assertEqual(len(list_runs(self.root)["runs"]), 1)
        self.assertEqual(engine.execute(self.root, run_id, runner_factory=SimulatedRunner)["status"], "passed-simulated")
        self.assertEqual(journal.read_bytes(), before)

    def test_failed_case_still_cleans_up_and_does_not_report_equivalence(self):
        class Broken(SimulatedRunner):
            def observe(self, lane, case): raise TimeoutError("test client timeout")
        result = engine.execute(self.root, self.start(), runner_factory=Broken)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["cleanup"]["complete"])
        self.assertEqual(result["matched"], 0)

    def test_cleanup_failure_overrides_passing_comparisons_and_blocks_next_run(self):
        class Dirty(SimulatedRunner):
            def cleanup(self): return {"complete": False, "resources": {"alloydb": "unconfirmed"}}
        result = engine.execute(self.root, self.start(), runner_factory=Dirty)
        self.assertEqual(result["matched"], 20)
        self.assertEqual(result["status"], "cleanup-required")
        with self.assertRaisesRegex(ValueError, "cleanup"):
            self.start()

    def test_changed_implementation_never_starts_resources(self):
        run_id = self.start()
        path = self.root / "src/lightyear_workflow/paired_number.py"
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
        with patch.object(SimulatedRunner, "prepare") as prepare:
            result = engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        prepare.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertIn("changed", result["error"])

    def test_expired_authorization_never_starts_resources(self):
        run_id = self.start()
        auth = engine.get_authorization(self.root, run_id)
        body = {k:v for k,v in auth.items() if k not in ('signature','content_sha256')}
        body['start_before'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        expired = engine.Signer(self.root).sign(body)
        with closing(engine.database(self.root)) as db, db:
            db.execute('UPDATE runs SET authorization=? WHERE run_id=?', (canonical(expired).decode(),run_id))
        with patch.object(SimulatedRunner, 'prepare') as prepare:
            result = engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        prepare.assert_not_called()
        self.assertIn('expired',result['error'])
        self.assertEqual(result['source_completed'],0)

    def test_one_simulated_lane_prevents_native_promotion(self):
        class Mixed(SimulatedRunner):
            evidence_class = 'native-database-observed'
            def identities(self):
                result = super().identities()
                result['alloydb']['evidence_class'] = 'simulated'
                return result
        result = engine.execute(self.root,self.start(),runner_factory=Mixed)
        self.assertEqual(result['matched'],20)
        self.assertEqual(result['status'],'passed-simulated')

    def test_journal_resealing_without_authority_signature_is_rejected(self):
        from lightyear_data.contracts import seal
        run_id = self.start()
        engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        store = RunStore(engine.run_path(self.root, run_id), read_only=True)
        events = store.events()
        events[-1]["payload"]["status"] = "passed-bounded-native"
        events[-1] = seal(events[-1])
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("UPDATE events SET envelope=? WHERE sequence=?", (json.dumps(events[-1]), len(events)))
        self.assertEqual(engine.read_run(self.root, run_id)["status"], "invalid")

    def test_raw_diagnostics_preserved_and_only_exact_mapping_passes(self):
        case = next(c for c in number_cases(self.root) if "overflow_code" in probes(c))
        runner = SimulatedRunner(None, None, None, None)
        source, target = runner.observe("oracle", case), runner.observe("alloydb", case)
        self.assertTrue(compare(case, source, target)["equivalent"])
        self.assertEqual(source["overflow_code"], -1438)
        self.assertEqual(target["overflow_code"], "22003")
        self.assertFalse(compare(case, source, {**target, "overflow_code": "XX000"})["equivalent"])
        self.assertIn("ROLLBACK", postgres_case(case))
        with self.assertRaises(ValueError): parse_observation("", case, "alloydb")

    def test_no_browser_get_origin_or_normalization_session_can_launch(self):
        from lightyear_knowledge_graph.explorer import ExplorerServer, GraphExplorerIndex
        from lightyear_knowledge_graph.model import load_graph
        server = ExplorerServer(('127.0.0.1', 0), GraphExplorerIndex(load_graph(ROOT / 'knowledge/graph.snapshot.json.gz')), ROOT / 'knowledge/viewer')
        server.campaign_service = self.service
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'
        with urlopen(origin + '/api/campaign/status') as response:
            self.assertTrue(json.load(response)['enabled'])
        for headers, body in [({}, None), ({'Origin': 'https://attacker.invalid', 'Authorization': 'Bearer ' + self.token}, self.request()),
                              ({'Origin': origin, 'Authorization': 'Bearer invalid'}, self.request())]:
            req = Request(origin + '/api/campaign/start', data=canonical(body) if body else None, headers={'Content-Type':'application/json', **headers})
            with self.assertRaises(HTTPError) as result: urlopen(req)
            self.assertEqual(result.exception.code, 401)
        self.assertEqual(engine.records(self.root), [])

    def test_unconfirmed_dispatch_recovery_never_runs_sql(self):
        run_id = self.start()
        with patch('lightyear_workflow.campaign_gcp.GcpRunner.prepare', side_effect=AssertionError('No SQL retry')):
            result = engine.recover(self.root, run_id)
        self.assertTrue(result['cleanup']['complete'])
        self.assertFalse(result['sql_retried'])
        self.assertEqual(engine.read_run(self.root, run_id)['status'], 'failed')
        self.assertTrue(self.start())

    def test_pruned_journal_does_not_become_a_new_queued_run(self):
        run_id = self.start()
        engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        (engine.run_path(self.root, run_id) / 'events.sqlite3').unlink()
        self.assertEqual(engine.read_run(self.root, run_id)['status'], 'unavailable')
        with self.assertRaisesRegex(ValueError, 'cannot execute again'):
            engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        self.assertEqual(history(self.root)['runs'][0]['status'], 'passed-simulated')

    def test_gcp_adapter_refuses_running_shared_instance_and_keeps_password_off_argv(self):
        from lightyear_workflow.campaign_gcp import GcpRunner
        run_id = self.start()
        engine.run_path(self.root, run_id).mkdir(parents=True)
        with patch('lightyear_workflow.campaign_gcp.shutil.which', return_value='gcloud'):
            runner = GcpRunner(self.root, run_id, plan(self.root), lambda *_: None)
        with patch.object(runner, 'instance', return_value={'name':'unexpected','state':'READY'}), patch.object(runner, 'command') as command:
            with self.assertRaises(ValueError): runner.prepare()
            command.assert_not_called()
        runner.password = 'test-only-password'
        runner.address = '10.0.0.1'
        with patch.object(runner, 'ssh', return_value=json.dumps({'returncode':0,'stdout':'{}','stderr':''})) as ssh:
            runner.sql('alloydb', 'SELECT 1;')
        self.assertNotIn(runner.password, ssh.call_args.args[0])
        self.assertIn(runner.password, ssh.call_args.kwargs['input'])

    def test_cleanup_does_not_delete_unowned_vm_and_still_stops_its_database(self):
        from lightyear_workflow.campaign_gcp import GcpRunner
        run_id = self.start()
        engine.run_path(self.root, run_id).mkdir(parents=True)
        with patch('lightyear_workflow.campaign_gcp.shutil.which', return_value='gcloud'):
            runner = GcpRunner(self.root, run_id, plan(self.root), lambda *_: None)
        runner.state.update(vm_create_requested=True,alloydb_start_requested=True)
        def command(args, **kwargs):
            if args[:3] == ['compute','instances','list']: return '[{"labels":{"lightyear-campaign":"someone-else"}}]'
            if args[:3] == ['compute','instances','delete']: self.fail('Deleted foreign runner')
            return '{}'
        with patch.object(runner,'command',side_effect=command) as calls, patch.object(runner,'instance',side_effect=[{'state':'READY'}, {'state':'STOPPED','activationPolicy':'NEVER'}]):
            result = runner.cleanup()
        self.assertFalse(result['complete'])
        self.assertEqual(result['resources']['alloydb'],'stopped')
        self.assertTrue(any('--activation-policy=NEVER' in call.args[0] for call in calls.call_args_list))

    def test_completed_recovery_cannot_stop_a_later_campaign(self):
        run_id = self.start()
        engine.execute(self.root, run_id, runner_factory=SimulatedRunner)
        self.start()
        with patch('lightyear_workflow.campaign_gcp.GcpRunner.cleanup', side_effect=AssertionError('Old run must not stop new run')):
            self.assertEqual(engine.recover(self.root, run_id)['status'], 'already-clean')

    def test_gcloud_stdin_disables_putty_replacement_input(self):
        from lightyear_workflow.campaign_gcp import GcpRunner
        from subprocess import CompletedProcess
        with patch('lightyear_workflow.campaign_gcp.shutil.which', return_value='gcloud'):
            runner = GcpRunner(self.root, 'number-' + '1'*32, plan(self.root), lambda *_: None)
        with patch('lightyear_workflow.campaign_gcp.subprocess.run', return_value=CompletedProcess([],0,'ok','')) as command:
            runner.command(['compute','ssh','test'], input='private-input')
        self.assertEqual(command.call_args.kwargs['env']['CLOUDSDK_SSH_PUTTY_FORCE_CONNECT'], 'false')
        self.assertEqual(command.call_args.kwargs['input'], 'private-input')
        self.assertNotIn('private-input', str(command.call_args.args))

    def test_alloydb_identity_binds_api_endpoint_and_checks_version_separately(self):
        from lightyear_workflow.campaign_gcp import GcpRunner
        with patch('lightyear_workflow.campaign_gcp.shutil.which', return_value='gcloud'):
            runner = GcpRunner(self.root, 'number-' + '1'*32, plan(self.root), lambda *_: None)
        runner.state['alloydb_name'] = 'bound-resource'
        source = 'LY_NUMBER_IDENTITY=' + json.dumps({'banner':'Oracle Database 26ai Free','version_full':'23.26.0.0.0','container_name':'FREEPDB1','dbid':'test','session':{'isolation_level':None}})
        target = {'version':'PostgreSQL 16.3','server_version':'16.3','server_address':'192.0.2.2','database':'postgres','user':'postgres'}
        resource = {'name':'bound-resource','state':'READY','ipAddress':'192.0.2.1'}
        with patch.object(runner,'instance',return_value=resource), patch.object(runner,'sql',side_effect=[source,json.dumps(target)]):
            identity = runner.identities()
        self.assertEqual(runner.address,resource['ipAddress'])
        self.assertTrue(identity['alloydb']['endpoint_verified'])
        self.assertFalse(identity['alloydb']['server_address_matches_endpoint'])
        self.assertNotIn('192.0.2.',json.dumps(identity))
        with patch.object(runner,'instance',return_value=resource), patch.object(runner,'sql',side_effect=[source,json.dumps({**target,'server_version':'17.1'})]):
            with self.assertRaisesRegex(ValueError,'PostgreSQL 16'): runner.identities()
        with patch.object(runner,'instance',return_value={**resource,'name':'other-resource'}), patch.object(runner,'sql') as sql:
            with self.assertRaises(ValueError): runner.identities()
            sql.assert_not_called()
