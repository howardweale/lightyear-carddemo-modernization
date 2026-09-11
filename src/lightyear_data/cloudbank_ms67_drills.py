"""Measured MS67 rolling, controlled node evacuation and cutover/rollback drills.

Candidates are signed packaging revisions, not a new application implementation.
Node drains use the eviction API and respect PodDisruptionBudgets. Intent is
uploaded and read back before mutation. Recovery is an explicit separate action.
"""
from __future__ import annotations

import copy
import json
import re
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .cloudbank_journeys import SERVICES, SCENARIOS, JourneyFailure, execute_journeys, hashed, require, journey_contract
from .cloudbank_journeys_gke import GkeRuntime
from .cloudbank_platform_qualification import CUTOVER_STATES
from .cloudbank_sql_recovery import SNAPSHOT_SQL, invoke, normalize_snapshot, verified, write_signed
from .contracts import sign
from .cloudbank_image_security import ImageJournal

STATE_TYPE = "lightyear-ms67-final-drills-recovery"
OBSERVATION_TYPE = "lightyear-ms67-final-drills-observation"
PASS = "passed-ms67-final-platform-drills"
LABEL = "lightyear.ai/ms67-final-target"
LEASE = "ly-ms67-final-drills"
HEX = r"[0-9a-f]{64}"

# Only metadata is returned. The already initialized release keeps its schema;
# serving replicas must not execute the destructive customer fixture again.
CUSTOMER_MIGRATIONS_SQL = r"""
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';
SELECT json_build_object('customer_changesets', count(*),
 'expected_changesets', count(*) FILTER (WHERE (id IN ('1','2') AND filename LIKE '%/table.sql')
 OR (id='3' AND filename LIKE '%/data.sql')),
 'successful_changesets', count(*) FILTER (WHERE exectype IN ('EXECUTED','RERAN') AND md5sum IS NOT NULL))
FROM public.databasechangelog WHERE author='customer';
SELECT json_build_object('locks', count(*), 'unlocked', count(*) FILTER (WHERE locked=false))
FROM public.databasechangeloglock;
COMMIT;
"""


def verify_customer_failure(state):
    comparisons = state.get('evacuation_comparisons', [])
    require(bool(comparisons), 'customer-reseed-comparison-required')
    row = comparisons[-1]
    before, after = row.get('pre_state', {}), row.get('post_state', {})
    difference = snapshot_difference(before, after)
    require(row.get('kind') == 'failure-domain' and difference == row.get('difference')
            and difference['detail_available'] and not difference['state_matches']
            and [r['name'] for r in difference['changed_objects']] ==
            ['cloudbank_customer.customers', 'public.databasechangelog']
            and all(r['before']['rows'] == r['after']['rows'] for r in difference['changed_objects']),
            'exact-customer-reseed-failure-required')


def occupied_node_plan(nodes, occupied):
    # Keep the ordinary node readiness/region/capacity checks, then avoid a
    # domain emptied by the previous failed attempt.
    node_plan(nodes)
    records = [{'name': n['metadata']['name'], 'uid': n['metadata']['uid'],
                'zone': n['metadata']['labels']['topology.kubernetes.io/zone']}
               for n in nodes if not n.get('spec', {}).get('unschedulable', False)]
    for first in sorted(records, key=lambda n: n['name']):
        if first['name'] not in occupied:
            continue
        for zone in sorted({n['zone'] for n in records} - {first['zone']}):
            domain = sorted([n for n in records if n['zone'] == zone], key=lambda n: n['name'])
            if len(records) - len(domain) >= 2 and any(n['name'] in occupied for n in domain):
                return {'node': [first], 'failure-domain': domain}
    raise JourneyFailure('two-occupied-distinct-evacuation-domains-required')


def detailed_snapshot(raw):
    # The shared SQL emits only metadata, row counts and digests. Preserve those
    # records without changing the existing whole-database hash or acceptance.
    result = normalize_snapshot(raw)
    result["objects"] = [json.loads(line) for line in raw.splitlines() if line.strip()][1:]
    return result


def snapshot_difference(before, after):
    def objects(value):
        return {(r.get("relation") or r.get("sequence") or "<schema>"): r for r in value.get("objects", [])}
    left, right = objects(before), objects(after)
    return {"state_matches": before == after, "pre_state_sha256": before["state_sha256"],
            "post_state_sha256": after["state_sha256"],
            "detail_available": bool(left and right),
            "changed_objects": [{"name": name, "before": left.get(name), "after": right.get(name)}
                                for name in sorted(left.keys() | right.keys()) if left.get(name) != right.get(name)],
            "scope": "all persistent application tables, sequences and column schema; counts and hashes only"}


def verify_availability(row, minimum):
    require(type(row.get("samples")) is int and row["samples"] >= 2
            and 0 <= row.get("maximum_observation_gap_seconds", 46) <= 45
            and set(row.get("minimum_available_by_service", {})) == set(SERVICES)
            and all(type(n) is int and n >= minimum for n in row["minimum_available_by_service"].values()),
            "drill-availability-measurement-invalid")


def verify_continuation(state, key, bindings, images, candidates, environment, *, cutover=False, rollback=False):
    """Validate the measured prefix from the specified restored failure."""
    verified(state, key)
    require(not rollback or cutover, 'rollback-continuation-requires-cutover-prefix')
    require(state.get("state_type") == STATE_TYPE and state.get("bindings") == bindings
            and state.get("environment") == environment and state.get("baseline_images") == images
            and state.get("candidate_images") == candidates and state.get("credentials_persisted") is False
            and state.get("phase") == "baseline-restored" and state.get("cleanup_required") is False
            and state.get("pending") is None and (cutover or state.get("canaries") == {})
            and state.get("recovery") == {"status": "restored", "errors": []}
            and state.get("failure") == ("operator-command-failed" if rollback else
                                         "target-cutover-business-journeys-failed" if cutover else
                                         "evacuation-normalized-database-state-changed"),
            "restored-cutover-checkpoint-required" if cutover else "restored-failure-domain-checkpoint-required")
    done = state.get("completed", {})
    require(set(done) == {"rolling", "resilience"} and set(done["resilience"]) ==
            ({"node", "failure-domain"} if cutover else {"node"}),
            "retained-rolling-and-both-evacuations-required" if cutover else "retained-rolling-and-node-only-required")
    rolling = done["rolling"]
    require(rolling.get("baseline_restored") is True
            and [r.get("service") for r in rolling.get("rows", [])] == list(SERVICES), "retained-eight-rollouts-required")
    for row in rolling["rows"]:
        service = row["service"]
        require(row.get("previous_image") == images[service] and row.get("candidate_image") == candidates[service]
                and row.get("completed") is True and row.get("maximum_unavailable") == 0, "retained-rollout-invalid")
        verify_availability(row["availability"], 2)
    for kind, node in done["resilience"].items():
        require(node.get("pre_state") == node.get("post_state") and node.get("affected_pods", 0) > 0
            and re.fullmatch(HEX, node.get("pre_state", {}).get("state_sha256", ""))
            and node.get("all_services_recovered") is True and node.get("node_scheduling_restored") is True
            and node.get("nodes_sha256") == hashed(state["node_plan"][kind]), "retained-node-evacuation-invalid")
        verify_availability(node["availability"], 1)
    return state


def verify_rollback_failure(state, key, bindings, images, candidates, environment):
    """Retain the signed passed journeys; an unfinished rollback is still failed."""
    from .cloudbank_ms65_rehearsal_gke import validate_shared_journeys
    verify_continuation(state, key, bindings, images, candidates, environment, cutover=True, rollback=True)
    verify_customer_mode(state.get('customer_startup'))
    require(state.get('customer_startup') is not None, 'retained-customer-startup-proof-required')
    journeys = state.get('target_journeys') or {}
    validate_shared_journeys(journeys, key, ms64_sha256=bindings['ms64_receipt_sha256'],
                            image_lock_sha256=bindings['candidate_image_lock_sha256'], environment=environment)
    verify_cutover_attempt(state, journeys, state.get('cutover_attempt') or {}, state.get('checks_isolation') or {})
    before = state.get('pre_rollback_state') or {}
    require(bool(before.get('objects')) and before == detailed_snapshot('\n'.join(
        json.dumps(row) for row in [{'unsupported': 0}, *before['objects']])),
        'retained-pre-rollback-database-snapshot-required')
    return state


def verify_cutover_failure(state, journeys, key, bindings, images, candidates, environment):
    """Admit only the restored, fully evacuated prefix and its exact failed journey."""
    verify_continuation(state, key, bindings, images, candidates, environment, cutover=True)
    verify_customer_mode(state.get('customer_startup'))
    require(state.get('customer_startup') is not None, 'retained-customer-startup-proof-required')
    verified(journeys, key)
    require(journeys.get('observation_type') == 'lightyear-cloudbank-shared-journey-execution'
            and journeys.get('run_id') == state['run_id'] and journeys.get('status') == 'failed'
            and journeys.get('bindings') == {
                'ms64_receipt_sha256': bindings['ms64_receipt_sha256'],
                'image_lock_sha256': bindings['candidate_image_lock_sha256'],
                'environment': environment, 'lane': 'gke-postgresql-target',
                'journey_contract_sha256': journey_contract()['content_sha256']}
            and journeys.get('recovery') == {'status': 'restored', 'errors': [], 'remaining_stopped_services': []}
            and journeys.get('credentials_persisted') is False
            and journeys.get('scenario_count') == 18
            and [r.get('id') for r in journeys.get('scenarios', [])] == [i for i, _ in SCENARIOS],
            'retained-cutover-journey-binding-invalid')
    failed = False
    for row, (identifier, normalized) in zip(journeys['scenarios'], SCENARIOS, strict=True):
        if identifier == 'checks-restart-redelivers-inflight':
            require(row.get('status') == 'failed' and row.get('reason') == 'inflight-claim-not-observed',
                    'retained-inflight-claim-failure-required')
            failed = True
        elif not failed:
            require(row.get('status') == 'passed' and row.get('normalized_result') == normalized
                    and row.get('evidence_sha256') == hashed(row.get('evidence')), 'retained-journey-prefix-invalid')
        else:
            require(row.get('status') == 'not-run', 'retained-journey-suffix-invalid')
    return state


def remaining_node_plan(nodes, saved, completed, occupied):
    current = node_plan(nodes)  # Keeps the existing ready/region/capacity checks.
    if "node" not in completed:
        return occupied_node_plan(nodes, occupied)
    require("node" in saved and bool(saved["node"]), "retained-node-plan-required")
    result = copy.deepcopy(saved)
    if "failure-domain" in completed:
        return result
    # Uncordoning does not move evacuated pods back. Choose a currently occupied
    # domain different from the already-qualified single-node domain.
    avoid = {n["zone"] for n in saved["node"]}
    groups = {}
    for node in nodes:
        meta = node["metadata"]
        zone = meta["labels"]["topology.kubernetes.io/zone"]
        groups.setdefault(zone, []).append({"name": meta["name"], "uid": meta["uid"], "zone": zone})
    choices = [sorted(group, key=lambda n: n["name"]) for zone, group in groups.items()
               if zone not in avoid and len(nodes)-len(group) >= 2 and any(n["name"] in occupied for n in group)]
    require(bool(choices), "occupied-failure-domain-with-two-survivors-required")
    result["failure-domain"] = min(choices, key=lambda group: (len(group), group[0]["zone"]))
    return result


def main_container(deployment, service):
    rows = deployment["spec"]["template"]["spec"].get("containers", [])
    matches = [(i, row) for i, row in enumerate(rows) if row.get("name") == service]
    require(len(matches) == 1, "final-drill-main-container-invalid")
    return matches[0]


def safe_candidate_env(row):
    # These two existing switches contain TOKEN in their names but their values
    # are public booleans. Unknown token/secret/password values remain forbidden.
    if row.get('name') in {'CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED', 'CLOUDBANK_SECURITY_REQUIRE_INTERNAL_TOKEN'}:
        return 'value' not in row or row['value'] in {'true', 'false'}
    return 'value' not in row or not re.search(r'PASSWORD|SECRET|TOKEN|PRIVATE_KEY', row.get('name', ''), re.I)


def candidate_name(service, run_id):
    require(service in SERVICES and re.fullmatch(r"ms67-final-[0-9a-f]{32}", run_id), "final-run-identity-invalid")
    return "ly-final-" + service + "-" + run_id[-10:]


def guarded_patch(resource, operations):
    return [{"op": "test", "path": "/metadata/uid", "value": resource["metadata"]["uid"]},
            {"op": "test", "path": "/metadata/resourceVersion", "value": resource["metadata"]["resourceVersion"]},
            *operations]


def node_plan(nodes):
    """Select two separate controlled disruptions, each with two surviving nodes."""
    eligible = []
    for node in nodes:
        meta, spec, status = node["metadata"], node.get("spec", {}), node.get("status", {})
        require(not spec.get("unschedulable"), "preexisting-cordoned-node-needs-review")
        require(any(c.get("type") == "Ready" and c.get("status") == "True" for c in status.get("conditions", [])),
                "all-workers-must-be-ready")
        zone = meta.get("labels", {}).get("topology.kubernetes.io/zone", "")
        require(re.fullmatch(r"us-west1-[a-z]", zone), "final-drill-node-region-invalid")
        require(not any(k.startswith("node-role.kubernetes.io/control-plane") for k in meta.get("labels", {})),
                "control-plane-node-not-a-drill-target")
        eligible.append({"name": meta["name"], "uid": meta["uid"], "zone": zone})
    eligible.sort(key=lambda r: (r["zone"], r["name"]))
    zones = sorted({r["zone"] for r in eligible})
    require(len(eligible) >= 3 and len(zones) >= 2, "three-workers-two-domains-required")
    first = eligible[0]
    choices = [[r for r in eligible if r["zone"] == z] for z in zones if z != first["zone"]]
    choices = [group for group in choices if len(eligible) - len(group) >= 2]
    require(bool(choices), "failure-domain-evacuation-needs-two-surviving-workers")
    return {"node": [first], "failure-domain": min(choices, key=len)}


class Availability:
    """Sample the whole deployment set during the measured mutation window."""
    def __init__(self, runtime, minimum, *, interval=1):
        self.runtime, self.minimum, self.interval = runtime, minimum, interval
        self.stop_event, self.thread = threading.Event(), None
        self.samples, self.minimum_seen, self.errors = 0, {s: 2 for s in SERVICES}, []
        self.maximum_gap_seconds, self.last_sample = 0.0, None

    def sample(self):
        now = time.monotonic()
        if self.last_sample is not None:
            self.maximum_gap_seconds = max(self.maximum_gap_seconds, now - self.last_sample)
        self.last_sample = now
        rows = {r["metadata"]["name"]: r for r in self.runtime.get("deployments").get("items", [])}
        for service in SERVICES:
            value = rows.get(service, {})
            require(value.get("metadata", {}).get("uid") == self.runtime.original[service]["uid"],
                    "availability-deployment-identity-drift")
            count = value.get("status", {}).get("availableReplicas", 0)
            self.minimum_seen[service] = min(self.minimum_seen[service], count)
            require(count >= self.minimum, "measured-service-availability-below-limit-" + service)
        self.samples += 1

    def loop(self):
        while not self.stop_event.wait(self.interval):
            try:
                self.sample()
            except Exception as exc:
                self.errors.append(str(exc) if isinstance(exc, JourneyFailure) else "availability-observation-failed")
                return

    def __enter__(self):
        self.sample()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join(timeout=40)
        require(not self.thread.is_alive(), "availability-reader-did-not-stop")
        self.sample()

    def result(self):
        require(not self.errors and self.samples >= 2 and self.maximum_gap_seconds <= 45,
                "availability-observation-incomplete")
        return {"samples": self.samples, "minimum_available_by_service": self.minimum_seen,
                "maximum_observation_gap_seconds": round(self.maximum_gap_seconds, 3),
                "requested_interval_seconds": self.interval,
                "scope": "Kubernetes deployment availability sampled during this mutation window"}


class CandidateRuntime(GkeRuntime):
    """Run the unchanged 18 journeys against the isolated candidate deployments."""
    def kubectl(self, *args, **kwargs):
        mapped = list(args)
        names = {s: candidate_name(s, self.run_id) for s in SERVICES}
        for i, arg in enumerate(mapped):
            for kind in ("deployment", "deployments"):
                if arg.startswith(kind + "/") and arg.split("/", 1)[1] in names:
                    mapped[i] = kind + "/" + names[arg.split("/", 1)[1]]
            if i and mapped[i-1] in {"deployment", "deployments"} and arg in names:
                mapped[i] = names[arg]
        return super().kubectl(*mapped, **kwargs)

    def direct_candidate_health(self, service, pod):
        """Positively contact a known ready canary while the Service is mixed."""
        self.close_forward(service)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(["kubectl", "--context", self.context, "-n", self.namespace,
            "port-forward", "--address=127.0.0.1", "pod/" + pod["metadata"]["name"], f"{port}:8080"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.forwards[service] = (process, port)
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        break
                except OSError:
                    require(process.poll() is None and time.monotonic() < deadline, "canary-port-forward-failed")
                    time.sleep(.2)
            response = self.send(service, "GET", "/actuator/health/readiness", None, {})
            require(response.status == 200 and response.json().get("status") == "UP", "candidate-health-probe-failed")
            return {"pod_uid_sha256": hashed(pod["metadata"]["uid"]), "http_status": 200,
                    "scope": "direct positive request to a candidate included in the mixed Service endpoints"}
        finally:
            self.close_forward(service)


class FinalDrills:
    def __init__(self, runtime, candidates, bindings, key, signer, prefix, *, state=None,
                 cloud=invoke, pause=time.sleep, clock=time.monotonic):
        self.r, self.candidates, self.bindings = runtime, candidates, bindings
        self.key, self.signer, self.prefix = key, signer, prefix.rstrip("/")
        self.cloud, self.pause, self.clock = cloud, pause, clock
        require(self.prefix == f"gs://{runtime.project}-ms67-evidence/final-drills/{runtime.run_id}",
                "final-drill-evidence-prefix-invalid")
        require(set(candidates) == set(SERVICES) and all(
            re.fullmatch(r"us-west1-docker.pkg.dev/" + re.escape(runtime.project) +
                         r"/cloudbank-ms67/" + re.escape(s) + r"@sha256:" + HEX, candidates[s])
            and candidates[s].split("@")[-1] != runtime.images[s].split("@")[-1] for s in SERVICES),
            "eight-distinct-candidate-digests-required")
        self.baseline_images = copy.deepcopy(runtime.images)
        self.s = state or {"schema_version": "1.0", "state_type": STATE_TYPE, "run_id": runtime.run_id,
            "environment": runtime.environment(), "bindings": bindings,
            "baseline_images": self.baseline_images, "candidate_images": candidates,
            "phase": "prepared", "baseline": {}, "nodes": {}, "canaries": {}, "completed": {},
            "pending": None, "lease_uid": None, "cleanup_required": False, "credentials_persisted": False,
            "ms67_complete": False}
        if state is not None:
            verified(state, key)
            require(state.get("state_type") == STATE_TYPE and state.get("run_id") == runtime.run_id
                    and state.get("environment") == runtime.environment() and state.get("bindings") == bindings
                    and state.get("baseline_images") == self.baseline_images
                    and state.get("candidate_images") == candidates, "final-recovery-context-mismatch")
        uri = self.prefix + "/final-drills.recovery.json"
        generation = "0"
        if state is not None:
            generation = cloud(["gcloud", "storage", "objects", "describe", uri, "--project", runtime.project,
                                "--format=value(generation)"]).strip()
            require(json.loads(cloud(["gcloud", "storage", "cat", uri + "#" + generation,
                                      "--project", runtime.project])) == state, "final-recovery-latest-state-required")
            runtime.original = {s: {"uid": row["uid"], "replicas": 2} for s, row in state["baseline"].items()}
        self.journal = ImageJournal(runtime.output / "final-drills.recovery.json", uri, runtime.project,
                                    key, signer, generation=generation, invoke=cloud)
        runtime.recovery_sink = self.journey_checkpoint

    def save(self, phase):
        self.s["phase"] = phase
        self.journal.write(self.s)
        self.r.progress("MS67_FINAL_PHASE=" + phase)

    def intent(self, phase, detail):
        self.s.update(pending={"phase": phase, **detail}, cleanup_required=True)
        self.save(phase + "-intent")

    def patch(self, kind, name, current, operations):
        self.r.kubectl("patch", kind + "/" + name, "--type=json", "--patch",
                       json.dumps(guarded_patch(current, operations)))

    def preflight(self):
        require(not self.s["cleanup_required"] and not self.s["pending"], "recover-incomplete-final-drill-first")
        require(not self.r.kubectl("get", "lease/" + LEASE, "--ignore-not-found", "-o", "name").strip(),
                "another-final-drill-lease-exists")
        self.r.ready()
        self.s["node_plan"] = remaining_node_plan(self.r.get("nodes")["items"], self.s.get("node_plan", {}),
            self.s["completed"].get("resilience", {}),
            {p["spec"].get("nodeName") for s in SERVICES for p in self.r.pods(s)})
        for service in SERVICES:
            d, svc = self.r.deployment(service), self.r.get("service", service)
            index, container = main_container(d, service)
            require(d["spec"].get("strategy", {}).get("type") == "RollingUpdate"
                    and d["spec"]["strategy"].get("rollingUpdate", {}).get("maxUnavailable") == 0,
                    "baseline-zero-unavailable-strategy-required")
            require(container["image"] == self.baseline_images[service] and svc["spec"].get("selector"),
                    "final-baseline-image-or-selector-invalid")
            require("pod-template-hash" not in svc["spec"]["selector"] and LABEL not in svc["spec"]["selector"],
                    "service-already-has-a-final-route-selector")
            pods = self.r.pods(service)
            hashes = {p["metadata"]["labels"].get("pod-template-hash") for p in pods}
            require(len(hashes) == 1 and None not in hashes, "stable-baseline-replicaset-required")
            baseline = {"uid": d["metadata"]["uid"], "container_index": index,
                "spec_sha256": hashed(d["spec"]), "service_uid": svc["metadata"]["uid"],
                "selector": svc["spec"]["selector"], "strategy": d["spec"]["strategy"],
                "baseline_pod_hash": hashes.pop()}
            old = self.s["baseline"].get(service)
            require(old is None or all(old.get(k) == v for k, v in baseline.items() if k != "baseline_pod_hash"),
                    "retained-baseline-identity-or-spec-drift")
            self.s["baseline"][service] = baseline
        for verb, resource in (("patch", "nodes"), ("create", "pods/eviction"), ("patch", "services"),
                               ("create", "deployments"), ("patch", "deployments"), ("create", "leases")):
            require(self.r.kubectl("auth", "can-i", verb, resource).strip() == "yes",
                    "final-drill-permission-required-" + verb + "-" + resource.replace("/", "-"))
        self.save("preflight-passed")

    def claim(self):
        self.intent("claim-lease", {})
        manifest = {"apiVersion": "coordination.k8s.io/v1", "kind": "Lease", "metadata": {
            "name": LEASE, "namespace": self.r.namespace, "labels": {LABEL: self.r.run_id}},
            "spec": {"holderIdentity": self.r.run_id}}
        value = json.loads(self.r.kubectl("create", "-f", "-", "-o", "json", data=json.dumps(manifest)))
        self.s["lease_uid"] = value["metadata"]["uid"]
        self.s["pending"] = None
        self.save("lease-claimed")

    def assert_lease(self):
        value = self.r.get("lease", LEASE)
        require(value["metadata"].get("labels", {}).get(LABEL) == self.r.run_id
                and value["spec"].get("holderIdentity") == self.r.run_id
                and (self.s["lease_uid"] is None or value["metadata"]["uid"] == self.s["lease_uid"]),
                "final-lease-identity-drift")

    def set_image(self, service, image):
        current = self.r.get("deployment", service)
        saved = self.s["baseline"][service]
        index, container = main_container(current, service)
        require(current["metadata"]["uid"] == saved["uid"] and index == saved["container_index"]
                and container["image"] in {self.baseline_images[service], self.candidates[service]},
                "final-rollout-baseline-drift")
        normalized = copy.deepcopy(current["spec"])
        normalized["template"]["spec"]["containers"][index]["image"] = self.baseline_images[service]
        require(hashed(normalized) == saved["spec_sha256"], "final-deployment-spec-changed-by-another-operator")
        if container["image"] != image:
            self.intent("image-" + service, {"service": service, "from": container["image"], "to": image})
            self.patch("deployment", service, current, [
                {"op": "test", "path": f"/spec/template/spec/containers/{index}/image", "value": container["image"]},
                {"op": "replace", "path": f"/spec/template/spec/containers/{index}/image", "value": image}])
        self.r.images[service] = image
        self.r.wait_ready(service)
        self.s["pending"] = None
        self.save("image-ready-" + service)

    def rolling(self):
        retained = {r['service']: r for r in self.s.get('rolling_reuse', [])}
        rows = []
        for service in SERVICES:
            if service in retained:
                rows.append(copy.deepcopy(retained[service]))
                self.r.progress('MS67_FINAL_REUSED=rolling-' + service)
                continue
            self.assert_lease()
            with Availability(self.r, 2) as monitor:
                self.set_image(service, self.candidates[service])
            measured = monitor.result()
            rows.append({"service": service, "previous_image": self.baseline_images[service],
                         "candidate_image": self.candidates[service], "maximum_unavailable":
                         max(0, 2 - measured["minimum_available_by_service"][service]),
                         "completed": True, "availability": measured})
            self.s["rolling_progress"] = rows
            self.save("rolling-measured-" + service)
        # Return to the retained release before the separate traffic cutover.
        for service in reversed(SERVICES):
            if service in retained:
                continue
            with Availability(self.r, 2) as monitor:
                self.set_image(service, self.baseline_images[service])
            monitor.result()
        self.s["completed"]["rolling"] = {"rows": rows, "baseline_restored": True,
            "candidate_scope": "OCI packaging revision; application layers and configuration retained"}
        self.save("rolling-passed")

    def database_query(self, sql):
        """Hash all tables/sequences with the existing read-only SQL statement."""
        urls = set()
        for service in SERVICES:
            jdbc = self.r.secret_json("cloudbank-" + service + "-external").get("SPRING_DATASOURCE_URL")
            if jdbc:
                urls.add(jdbc)
        require(len(urls) == 1, "final-snapshot-requires-one-shared-application-database")
        deadline = self.clock() + 120
        while True:
            raw = self.r.kubectl("get", "pod/" + self.r.probe_name, "--ignore-not-found", "-o", "json")
            if not raw.strip():
                break
            pod = json.loads(raw)
            require(pod["metadata"].get("labels", {}).get("lightyear.run") == self.r.run_id
                    and pod["metadata"].get("deletionTimestamp"), "previous-probe-still-active-or-unowned")
            require(self.clock() < deadline, "previous-probe-deletion-incomplete")
            self.pause(1)
        self.r.create_probe()
        try:
            raw = invoke(["kubectl", "--context", self.r.context, "-n", self.r.namespace,
                          "exec", "-i", self.r.probe_name, "--", "psql", "-X", "-qAt", "--no-password",
                          "--set=ON_ERROR_STOP=1"], data=sql, timeout=180, sensitive=True)
            return raw
        finally:
            recovery = self.r.close()
            require(recovery["status"] == "restored", "snapshot-probe-cleanup-failed")

    def snapshot(self):
        return detailed_snapshot(self.database_query(SNAPSHOT_SQL))

    def adopt_customer_mode(self):
        """Resolve an interrupted guarded patch without reverting to reseeding."""
        mode = self.s.get('customer_startup')
        if not mode:
            return
        current = self.r.deployment('customer')
        require(current['metadata']['uid'] == self.s['baseline']['customer']['uid'],
                'customer-startup-deployment-identity-drift')
        index, container = main_container(current, 'customer')
        require(index == mode['container_index'] and container['image'] in
                {self.baseline_images['customer'], self.candidates['customer']}, 'customer-startup-image-drift')
        normalized = copy.deepcopy(current['spec'])
        normalized['template']['spec']['containers'][index]['image'] = self.baseline_images['customer']
        actual = hashed(normalized)
        require(actual in {mode['old_spec_sha256'], mode['new_spec_sha256']},
                'customer-startup-unexpected-deployment-spec')
        self.s['baseline']['customer']['spec_sha256'] = actual
        if actual == mode['new_spec_sha256']:
            mode['applied'] = True

    def repair_customer_startup(self):
        mode = self.s.get('customer_startup')
        if mode and mode.get('status') == 'passed':
            return
        if mode is None:
            metadata = [json.loads(line) for line in self.database_query(CUSTOMER_MIGRATIONS_SQL).splitlines() if line.strip()]
            require(metadata == [{'customer_changesets': 3, 'expected_changesets': 3, 'successful_changesets': 3},
                                 {'locks': 1, 'unlocked': 1}], 'initialized-unlocked-customer-schema-required')
            current = self.r.deployment('customer')
            require(hashed(current['spec']) == self.s['baseline']['customer']['spec_sha256'],
                    'customer-startup-baseline-spec-drift')
            index, container = main_container(current, 'customer')
            env = container.get('env', [])
            indexes = [i for i, r in enumerate(env) if r.get('name') == 'LIQUIBASE_ENABLED']
            require(len(indexes) <= 1 and (not indexes or env[indexes[0]] == {'name': 'LIQUIBASE_ENABLED', 'value': 'true'})
                    and 'env' in container
                    and not any(r.get('name') == 'SPRING_LIQUIBASE_ENABLED' for r in env)
                    and not any('liquibase' in a.lower() for a in container.get('args', []) + container.get('command', [])),
                    'explicit-customer-liquibase-true-without-override-required')
            new_spec = copy.deepcopy(current['spec'])
            new_env = new_spec['template']['spec']['containers'][index]['env']
            if indexes:
                new_env[indexes[0]]['value'] = 'false'
            else:
                new_env.append({'name': 'LIQUIBASE_ENABLED', 'value': 'false'})
            mode = {'status': 'prepared', 'applied': False, 'service': 'customer',
                    'setting': 'LIQUIBASE_ENABLED', 'before': 'true' if indexes else 'absent-default-true', 'after': 'false',
                    'container_index': index, 'env_index': indexes[0] if indexes else None, 'migration_metadata': metadata,
                    'old_spec_sha256': hashed(current['spec']), 'new_spec_sha256': hashed(new_spec),
                    'pre_state': self.stable_snapshot(),
                    'previous_completed': copy.deepcopy(self.s['completed']),
                    'scope': 'existing initialized nonproduction database; future schema changes require explicit migration'}
            self.s['customer_startup'] = mode
        current = self.r.deployment('customer')
        self.adopt_customer_mode()
        with Availability(self.r, 2) as monitor:
            if not mode['applied']:
                self.intent('customer-startup-mode', {'service': 'customer', 'setting': 'LIQUIBASE_ENABLED', 'value': 'false'})
                path = f"/spec/template/spec/containers/{mode['container_index']}/env"
                operations = ([{'op': 'add', 'path': path + '/-', 'value': {'name': 'LIQUIBASE_ENABLED', 'value': 'false'}}]
                              if mode['env_index'] is None else [
                    {'op': 'test', 'path': path + f"/{mode['env_index']}/value", 'value': 'true'},
                    {'op': 'replace', 'path': path + f"/{mode['env_index']}/value", 'value': 'false'}])
                self.patch('deployment', 'customer', current, operations)
                self.adopt_customer_mode()
                self.s['pending'] = None
                self.save('customer-startup-mode-applied')
            self.r.wait_ready('customer')
        mode['availability'] = monitor.result()
        mode['post_state'] = self.stable_snapshot()
        mode['difference'] = snapshot_difference(mode['pre_state'], mode['post_state'])
        self.save('customer-startup-mode-comparison')
        require(mode['pre_state'] == mode['post_state'], 'customer-startup-mode-database-state-changed')
        mode['status'] = 'passed'
        # Seven deployment specs did not change. Refresh the customer's rollout
        # and both evacuation proofs under the corrected runtime configuration.
        self.s['rolling_reuse'] = [r for r in mode['previous_completed']['rolling']['rows'] if r['service'] != 'customer']
        self.s['completed'] = {}
        self.s['node_plan'] = occupied_node_plan(self.r.get('nodes')['items'],
            {p['spec'].get('nodeName') for s in SERVICES for p in self.r.pods(s)})
        self.save('customer-startup-mode-passed')

    def stable_snapshot(self):
        first = self.snapshot()
        self.pause(2)
        second = self.snapshot()
        if first != second:
            self.s["unstable_snapshot"] = snapshot_difference(first, second)
            self.save("database-snapshot-unstable")
        require(first == second, "concurrent-database-writes-prevent-exact-drill-comparison")
        return second

    def cordon(self, record, disabled):
        current = self.r.get("node", record["name"])
        require(current["metadata"]["uid"] == record["uid"], "node-identity-drift")
        actual = current.get("spec", {}).get("unschedulable", False)
        if actual == disabled:
            return
        self.intent("node-scheduling", {"node": record["name"], "unschedulable": disabled})
        self.patch("node", record["name"], current,
                   [{"op": "add", "path": "/spec/unschedulable", "value": disabled}])
        self.s["pending"] = None
        self.save("node-scheduling-updated")

    def resilience(self):
        results = copy.deepcopy(self.s["completed"].get("resilience", {}))
        for kind, nodes in self.s["node_plan"].items():
            if kind in results:
                self.r.progress("MS67_FINAL_REUSED=evacuation-" + kind)
                continue
            self.assert_lease()
            before = self.stable_snapshot()
            comparisons = self.s.setdefault("evacuation_comparisons", [])
            comparison = {"kind": kind, "nodes_sha256": hashed(nodes), "pre_state": before}
            comparisons.append(comparison)
            names = {n["name"] for n in nodes}
            affected = [p["metadata"]["uid"] for s in SERVICES for p in self.r.pods(s)
                        if p.get("spec", {}).get("nodeName") in names]
            require(bool(affected), "selected-evacuation-has-no-application-pods")
            for n in nodes:
                self.s["nodes"][n["name"]] = {**n, "original_unschedulable": False}
            self.save("evacuation-plan-" + kind)
            with Availability(self.r, 1) as monitor:
                for n in nodes:
                    self.cordon(n, True)
                for n in nodes:
                    self.intent("drain-" + kind, {"node": n["name"]})
                    # No force, no disabled eviction, and no PDB override.
                    self.r.kubectl("drain", n["name"], "--ignore-daemonsets", "--delete-emptydir-data",
                                   "--timeout=600s", timeout=630)
                    self.s["pending"] = None
                    self.save("drained-" + kind)
                for service in SERVICES:
                    self.r.wait_ready(service)
                survivors = [p for s in SERVICES for p in self.r.pods(s)]
                require(all(p["spec"].get("nodeName") not in names for p in survivors)
                        and not set(affected) & {p["metadata"]["uid"] for p in survivors},
                        "application-evacuation-not-observed")
            availability = monitor.result()
            self.r.ready()
            after = self.stable_snapshot()
            comparison.update(post_state=after, difference=snapshot_difference(before, after))
            self.save("evacuation-comparison-" + kind)
            if before != after:
                self.r.progress("MS67_FINAL_DATABASE_DIFFERENCE=" + json.dumps(comparison["difference"], sort_keys=True))
            require(before == after, "evacuation-normalized-database-state-changed")
            for n in nodes:
                self.cordon(n, False)
            results[kind] = {"scope": "controlled node drain and workload evacuation; not a power or regional outage",
                "nodes_sha256": hashed(nodes), "affected_pods": len(affected),
                "pre_state": before, "post_state": after, "availability": availability,
                "all_services_recovered": True, "node_scheduling_restored": True}
            self.s["completed"]["resilience"] = results
            self.save("evacuation-passed-" + kind)

    def route(self, service, selector):
        self.s['route_operation'] = {'service': service, 'operation': 'read-service', 'patch_attempts': 0}
        current = self.r.get("service", service)
        original = self.s["baseline"][service]
        allowed = [original["selector"], {**original["selector"], "pod-template-hash": original["baseline_pod_hash"]},
                   {LABEL: self.r.run_id, "app.kubernetes.io/name": service}]
        require(current["metadata"]["uid"] == original["service_uid"]
                and current["spec"].get("selector") in allowed and selector in allowed,
                "service-route-changed-by-another-operator")
        if current["spec"]["selector"] != selector:
            before = copy.deepcopy(current['spec'])
            desired = {**before, 'selector': copy.deepcopy(selector)}
            self.intent("route-" + service, {"service": service, "selector": selector,
                'before_spec_sha256': hashed(before), 'desired_spec_sha256': hashed(desired)})
            self.patch_route(service, original['service_uid'], before, desired)
        self.r.close_forward(service)
        self.s["pending"] = None
        self.save("route-updated-" + service)

    def patch_route(self, service, uid, before, desired):
        """Re-read after durable intent; never retry over a changed Service spec."""
        detail = self.s['route_operation']
        def read():
            detail['operation'] = 'read-service'
            value = self.r.get('service', service)
            require(value['metadata']['uid'] == uid and not value['metadata'].get('deletionTimestamp')
                    and value['spec'] in (before, desired), 'service-route-identity-or-spec-drift-' + service)
            detail['observed_resource_version'] = value['metadata']['resourceVersion']
            detail['observed_spec_sha256'] = hashed(value['spec'])
            return value
        for attempt in range(1, 4):
            detail['operation'] = 'verify-lease'
            self.assert_lease()
            # The checkpoint upload can take seconds. Do not use the version
            # captured before it. UID/resourceVersion tests remain atomic.
            current = read()
            if current['spec'] == desired:
                detail['operation'] = 'desired-route-verified'
                return
            detail.update(operation='patch-service-selector', patch_attempts=attempt,
                          patched_resource_version=current['metadata']['resourceVersion'])
            try:
                self.patch('service', service, current,
                    [{'op': 'replace', 'path': '/spec/selector', 'value': desired['selector']}])
            except JourneyFailure as exc:
                if str(exc) not in {'operator-command-failed', 'operator-command-unavailable-or-timed-out'}:
                    raise
                # An error may follow a committed update. Adopt only a readback
                # of the exact desired spec. Otherwise retry solely when the
                # version changed and the complete original spec is intact.
                observed = read()
                if observed['spec'] == desired:
                    detail['operation'] = 'desired-route-verified-after-command-error'
                    return
                changed = observed['metadata']['resourceVersion'] != current['metadata']['resourceVersion']
                detail.update(operation='patch-service-selector-failed', version_changed=changed)
                require(changed and attempt < 3, 'service-route-patch-failed-' + service)
                self.pause(.2)
                continue
            require(read()['spec'] == desired, 'service-route-readback-mismatch-' + service)
            detail['operation'] = 'desired-route-verified'
            return

    def canary_pods(self, service):
        name = candidate_name(service, self.r.run_id)
        d = self.r.get("deployment", name)
        expected = self.s["canaries"][service]
        require(d["metadata"]["uid"] == expected["uid"] and d["metadata"].get("labels", {}).get(LABEL) == self.r.run_id,
                "candidate-deployment-identity-drift")
        require(hashed(d["spec"]) == expected["spec_sha256"], "candidate-deployment-spec-drift")
        sets = self.r.get("replicasets", selector=LABEL + "=" + self.r.run_id)["items"]
        owned = {x["metadata"]["uid"] for x in sets if any(
            r.get("uid") == expected["uid"] and r.get("controller") is True for r in x["metadata"].get("ownerReferences", []))}
        pods = [p for p in self.r.get("pods", selector=LABEL + "=" + self.r.run_id)["items"]
                if any(r.get("uid") in owned and r.get("controller") is True for r in p["metadata"].get("ownerReferences", []))]
        require(len(pods) == 2 and all(not p["metadata"].get("deletionTimestamp") and any(
            c.get("name") == service and c.get("ready") and c.get("imageID", "").endswith(self.candidates[service].split("@")[-1])
            for c in p.get("status", {}).get("containerStatuses", [])) for p in pods), "candidate-pods-not-ready")
        return pods

    def endpoints(self, service, expected):
        deadline = self.clock() + 180
        while True:
            obj = self.r.get("endpoints", service)
            uids = {a.get("targetRef", {}).get("uid") for subset in obj.get("subsets", []) for a in subset.get("addresses", [])}
            if uids == expected:
                return {"ready_endpoint_count": len(uids), "pod_uids_sha256": hashed(sorted(uids))}
            require(self.clock() < deadline, "final-service-endpoint-switch-timeout-" + service)
            self.pause(1)

    def create_canaries(self):
        for service in SERVICES:
            d = self.r.deployment(service)
            pods = self.r.pods(service)
            hashes = {p["metadata"]["labels"]["pod-template-hash"] for p in pods}
            require(len(hashes) == 1, "baseline-replicaset-not-stable")
            self.s["baseline"][service]["baseline_pod_hash"] = hashes.pop()
            self.route(service, {**self.s["baseline"][service]["selector"],
                                 "pod-template-hash": self.s["baseline"][service]["baseline_pod_hash"]})
            self.endpoints(service, {p["metadata"]["uid"] for p in pods})
            template = copy.deepcopy(d["spec"]["template"])
            template["metadata"].setdefault("labels", {})[LABEL] = self.r.run_id
            template["spec"]["containers"][main_container(d, service)[0]]["image"] = self.candidates[service]
            name = candidate_name(service, self.r.run_id)
            manifest = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {
                "name": name, "namespace": self.r.namespace, "labels": {LABEL: self.r.run_id}},
                "spec": {"replicas": 2, "selector": {"matchLabels": {
                    LABEL: self.r.run_id, "app.kubernetes.io/name": service}},
                    "strategy": copy.deepcopy(d["spec"]["strategy"]), "template": template}}
            # Raw environment values are forbidden; credentials must remain secret references.
            require(all(safe_candidate_env(e) for c in template["spec"].get("containers", []) for e in c.get("env", [])),
                    "candidate-literal-credential-environment-not-supported")
            self.s["canaries"][service] = {"uid": None, "name": name, "intent_spec_sha256": hashed(manifest["spec"])}
            self.intent("create-candidate-" + service, {"service": service})
            created = json.loads(self.r.kubectl("create", "-f", "-", "-o", "json", data=json.dumps(manifest)))
            # Persist only the spec hash, not a copy of deployment configuration.
            self.s["canaries"][service].update(uid=created["metadata"]["uid"], spec_sha256=hashed(created["spec"]))
            self.s["pending"] = None
            self.save("candidate-created-" + service)
            self.r.kubectl("rollout", "status", "deployment/" + name, "--timeout=600s", timeout=630)

    def baseline_checks(self):
        current = self.r.get('deployment', 'checks')
        saved = self.s['baseline']['checks']
        normalized = copy.deepcopy(current['spec'])
        require(normalized.get('replicas') in {0, 2}, 'baseline-checks-replicas-drift')
        normalized['replicas'] = 2
        require(current['metadata']['uid'] == saved['uid']
                and hashed(normalized) == saved['spec_sha256'], 'baseline-checks-identity-or-spec-drift')
        return current

    def isolate_baseline_checks(self):
        # Service routing does not control PostgreSQL queue polling. Observe
        # candidate capacity before retiring the competing baseline consumers.
        self.assert_lease()
        candidates = {p['metadata']['uid'] for p in self.canary_pods('checks')}
        self.endpoints('checks', candidates)
        current = self.baseline_checks()
        require(current['spec']['replicas'] == 2, 'two-baseline-checks-replicas-required')
        self.s['checks_isolation'] = {'status': 'prepared', 'baseline_uid': current['metadata']['uid'],
            'baseline_spec_sha256': self.s['baseline']['checks']['spec_sha256'],
            'journey_run_id': self.s['cutover_attempt']['run_id'], 'original_replicas': 2,
            'scope': 'baseline Checks queue consumers paused while candidate Checks owns the target journeys'}
        self.intent('isolate-baseline-checks', {})
        self.r.close_forward('checks')
        self.patch('deployment', 'checks', current, [{'op': 'replace', 'path': '/spec/replicas', 'value': 0}])
        deadline = self.clock() + 180
        while self.r.pods('checks'):
            require(self.clock() < deadline, 'baseline-checks-stop-timeout')
            self.pause(1)
        require(self.baseline_checks()['spec']['replicas'] == 0, 'baseline-checks-not-stopped')
        # Reject other Checks pods, including terminating pods; a ready Service
        # endpoint count alone cannot exclude an out-of-route queue consumer.
        all_checks = [p for p in self.r.get('pods', selector='app.kubernetes.io/name=checks')['items']
                      if p['metadata'].get('labels', {}).get('app.kubernetes.io/name') == 'checks']
        require({p['metadata']['uid'] for p in all_checks} == candidates,
                'unexpected-checks-queue-consumers')
        self.endpoints('checks', candidates)
        self.s['checks_isolation'].update(status='isolated', baseline_pods_observed=0,
            candidate_pods_observed=2, candidate_pod_uids_sha256=hashed(sorted(candidates)))
        self.s['pending'] = None
        self.save('baseline-checks-isolated')

    def restore_baseline_checks(self):
        saved = self.s.get('checks_isolation')
        if not saved:
            return
        self.assert_lease()
        current = self.baseline_checks()
        require(saved['baseline_uid'] == current['metadata']['uid']
                and saved['baseline_spec_sha256'] == self.s['baseline']['checks']['spec_sha256'],
                'baseline-checks-restoration-binding-invalid')
        if current['spec']['replicas'] == 0:
            self.intent('restore-baseline-checks', {})
            self.patch('deployment', 'checks', current, [{'op': 'replace', 'path': '/spec/replicas', 'value': 2}])
        self.r.wait_ready('checks')
        pods = self.r.pods('checks')
        require(len(pods) == 2 and hashed(self.baseline_checks()['spec']) == saved['baseline_spec_sha256'],
                'baseline-checks-restoration-incomplete')
        saved.update(status='restored', restored_replicas=2,
                     restored_pod_uids_sha256=hashed(sorted(p['metadata']['uid'] for p in pods)))
        self.s['pending'] = None
        self.save('baseline-checks-restored')

    def cutover(self):
        if self.s.get('cutover_attempt'):
            self.s.setdefault('prior_cutover_attempts', []).append({k: copy.deepcopy(self.s.get(k))
                for k in ('cutover_attempt', 'target_journeys', 'checks_isolation', 'pre_rollback_state', 'failure_context')})
        for key in ('target_journeys', 'checks_isolation', 'pre_rollback_state', 'failure_context', 'route_operation'):
            self.s.pop(key, None)
        attempt = {'run_id': 'ms67-cutover-' + uuid.uuid4().hex, 'parent_run_id': self.r.run_id}
        self.s['cutover_attempt'] = attempt
        self.save('cutover-attempt-prepared')
        states = [CUTOVER_STATES[0]]
        self.create_canaries()
        candidates = {s: {p["metadata"]["uid"] for p in self.canary_pods(s)} for s in SERVICES}
        states.append("canary-ready")
        routes = {"canary": {}, "target": {}, "restored": {}}
        for service in SERVICES:
            self.route(service, self.s["baseline"][service]["selector"])
            baseline = {p["metadata"]["uid"] for p in self.r.pods(service)}
            routes["canary"][service] = self.endpoints(service, baseline | candidates[service])
        direct = CandidateRuntime(project=self.r.project, region=self.r.region, cluster=self.r.cluster,
            namespace=self.r.namespace, images=self.candidates.copy(), run_id=self.r.run_id, output=self.r.output)
        for service in SERVICES:
            routes["canary"][service]["candidate_request"] = direct.direct_candidate_health(service, self.canary_pods(service)[0])
        # The 50% value describes equal ready endpoint capacity. Actual request
        # allocation is randomized by Kubernetes and is not asserted to be exact.
        states.append("canary-traffic-observed")
        for service in SERVICES:
            self.route(service, {LABEL: self.r.run_id, "app.kubernetes.io/name": service})
            routes["target"][service] = self.endpoints(service, candidates[service])
        states.append("target-traffic-100-percent")
        self.isolate_baseline_checks()
        candidate_output = self.r.output / ('target-journeys-' + attempt['run_id'])
        candidate_output.mkdir()
        runtime = CandidateRuntime(project=self.r.project, region=self.r.region, cluster=self.r.cluster,
            namespace=self.r.namespace, images=self.candidates.copy(), run_id=self.r.run_id,
            output=candidate_output, probe_image=self.r.probe_image, signing_key=self.key, signer=self.signer,
            progress=self.r.progress, recovery_sink=self.journey_checkpoint)
        runtime.create_probe()
        bindings = {"ms64_receipt_sha256": self.bindings["ms64_receipt_sha256"],
                    "image_lock_sha256": self.bindings["candidate_image_lock_sha256"], "environment": runtime.environment(),
                    "lane": "gke-postgresql-target"}
        def checkpoint(value):
            signed = sign(copy.deepcopy(value), self.key, self.signer)
            write_signed(candidate_output / 'journeys.json', signed, self.key, self.signer)
            # Persist the nested result even on failure, before outer cleanup.
            self.s['target_journeys'] = signed
            self.save('target-journey-result')
        journeys = execute_journeys(runtime, bindings, self.key, self.signer, run_id=attempt['run_id'],
            progress=self.r.progress, checkpoint=checkpoint)
        self.s["target_journeys"] = journeys
        self.save('target-journeys-finished')
        require(journeys["status"] == "passed-shared-journeys", "target-cutover-business-journeys-failed")
        states.append("business-journeys-passed")
        # Preserve all acknowledged target transactions across rollback.
        before_rollback = self.stable_snapshot()
        self.s["pre_rollback_state"] = before_rollback
        self.save("before-rollback-state-verified")
        states.append("rollback-triggered")
        self.restore_baseline_checks()
        for service in SERVICES:
            baseline = {p["metadata"]["uid"] for p in self.r.pods(service)}
            self.route(service, {**self.s["baseline"][service]["selector"],
                                 "pod-template-hash": self.s["baseline"][service]["baseline_pod_hash"]})
            routes["restored"][service] = self.endpoints(service, baseline)
        self.remove_canaries()
        for service in SERVICES:
            self.route(service, self.s["baseline"][service]["selector"])
        states.append("previous-release-restored")
        self.r.ready()
        after = self.stable_snapshot()
        require(before_rollback == after, "rollback-normalized-database-state-changed")
        states.append("post-rollback-recovered")
        self.s["completed"]["cutover"] = {"states": states, "canary_percent": 50, "target_traffic_percent": 100,
            "canary_percent_scope": "equal ready baseline/candidate endpoint capacity, not exact request share",
            "business_journey_count": journeys["scenario_count"], "journeys_sha256": journeys["content_sha256"],
            "journey_attempt": attempt, "checks_isolation": copy.deepcopy(self.s['checks_isolation']),
            "rollback_exercised": True, "all_services_recovered": True,
            "pre_state_sha256": before_rollback["state_sha256"], "post_rollback_state_sha256": after["state_sha256"],
            "state_scope": "all application tables and sequences immediately before and after rollback; target writes retained",
            "routes": routes}
        self.save("cutover-passed")

    def journey_checkpoint(self, state):
        self.s["journey_recovery"] = state
        self.save("target-journey-checkpoint")

    def remove_canaries(self):
        for service, saved in self.s["canaries"].items():
            raw = self.r.kubectl("get", "deployment/" + saved["name"], "--ignore-not-found", "-o", "json")
            if not raw.strip():
                continue
            value = json.loads(raw)
            require(value["metadata"].get("labels", {}).get(LABEL) == self.r.run_id
                    and (saved["uid"] is None or value["metadata"]["uid"] == saved["uid"]),
                    "candidate-cleanup-identity-drift")
            # The baseline route must be positively restored before deletion.
            base = {p["metadata"]["uid"] for p in self.r.pods(service)}
            self.endpoints(service, base)
            self.intent("delete-candidate-" + service, {"service": service})
            self.r.kubectl("delete", "deployment/" + saved["name"], "--wait=true", "--timeout=180s", timeout=200)
            self.s["pending"] = None
            self.save("candidate-deleted-" + service)

    def cleanup(self):
        """Restore owned routes/images/nodes; preserve resources on identity drift."""
        raw = self.r.kubectl("get", "lease/" + LEASE, "--ignore-not-found", "-o", "json")
        if not raw.strip():
            require((self.s.get("pending") or {}).get("phase") in {"claim-lease", "release-lease"},
                    "final-drill-lock-disappeared-during-mutations")
            self.r.ready()
            self.s.update(cleanup_required=False, pending=None, recovery={"status": "restored", "errors": []})
            self.save("baseline-restored")
            return self.s["recovery"]
        self.assert_lease()
        errors = []
        try:
            self.restore_baseline_checks()
        except Exception:
            errors.append('baseline-checks-restoration-failed')
        try:
            self.adopt_customer_mode()
        except Exception:
            errors.append('customer-startup-mode-recovery-drift')
        for record in self.s["nodes"].values():
            try:
                self.cordon(record, record["original_unschedulable"])
            except Exception:
                errors.append("node-restoration-failed-" + record["name"])
        for service in self.s["baseline"]:
            try:
                self.set_image(service, self.baseline_images[service])
                pods = self.r.pods(service)
                hashes = {p["metadata"]["labels"]["pod-template-hash"] for p in pods}
                require(len(hashes) == 1, "baseline-replicaset-not-stable")
                # A rolling return may have assigned a different ReplicaSet hash.
                saved_hash = self.s["baseline"][service]["baseline_pod_hash"]
                current = self.r.get("service", service)
                require(current["metadata"]["uid"] == self.s["baseline"][service]["service_uid"],
                        "cleanup-service-identity-drift")
                self.s["baseline"][service]["baseline_pod_hash"] = hashes.pop()
                if current["spec"]["selector"] == {**self.s["baseline"][service]["selector"], "pod-template-hash": saved_hash}:
                    self.intent("repair-baseline-route-" + service, {"service": service})
                    self.patch("service", service, current, [{"op": "replace", "path": "/spec/selector", "value": {
                        **self.s["baseline"][service]["selector"], "pod-template-hash": self.s["baseline"][service]["baseline_pod_hash"]}}])
                else:
                    self.route(service, {**self.s["baseline"][service]["selector"],
                                         "pod-template-hash": self.s["baseline"][service]["baseline_pod_hash"]})
                self.endpoints(service, {p["metadata"]["uid"] for p in pods})
            except Exception:
                errors.append("baseline-restoration-failed-" + service)
        if not errors:
            try:
                self.remove_canaries()
                for service in SERVICES:
                    self.route(service, self.s["baseline"][service]["selector"])
                self.r.ready()
                require(self.r.close()["status"] == "restored", "final-probe-cleanup-failed")
                self.intent("release-lease", {})
                self.assert_lease()
                self.r.kubectl("delete", "lease/" + LEASE, "--wait=true")
            except Exception:
                errors.append("final-cleanup-incomplete")
        self.s.update(cleanup_required=bool(errors), pending=None if not errors else self.s["pending"])
        self.s["recovery"] = {"status": "failed" if errors else "restored", "errors": errors}
        self.save("recovery-incomplete" if errors else "baseline-restored")
        return self.s["recovery"]

    def run(self, *, repair_customer_startup=False):
        self.preflight()
        self.claim()
        if self.s.get("failure"):
            self.s.setdefault("prior_failures", []).append(self.s.pop("failure"))
            self.save("continuing-missing-drills")
        failure = None
        try:
            if repair_customer_startup or self.s.get('customer_startup'):
                self.repair_customer_startup()
            if "rolling" not in self.s["completed"]:
                self.rolling()
            else:
                self.r.progress("MS67_FINAL_REUSED=rolling")
            if set(self.s["completed"].get("resilience", {})) != {"node", "failure-domain"}:
                self.resilience()
            if "cutover" not in self.s["completed"]:
                self.cutover()
        except (Exception, KeyboardInterrupt) as exc:
            failure = str(exc) if isinstance(exc, JourneyFailure) else "final-drill-interrupted-or-runtime-error"
            self.s["failure"] = failure
            self.s['failure_context'] = copy.deepcopy({'phase': self.s.get('phase'),
                'pending': self.s.get('pending'), 'last_route_operation': self.s.get('route_operation')})
            self.save("drill-failed")
        finally:
            recovery = self.cleanup()
        value = {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE,
                 "run_id": self.r.run_id, "bindings": self.bindings, "environment": self.s["environment"],
                 "baseline_images": self.baseline_images, "candidate_images": self.candidates,
                 "status": PASS if failure is None and recovery["status"] == "restored" else "failed",
                 "reason": failure, "completed": self.s["completed"], "recovery": recovery,
                 "failure_context": self.s.get('failure_context'),
                 "target_journeys": self.s.get("target_journeys"),
                 "cutover_attempt": self.s.get('cutover_attempt'),
                 "checks_isolation": self.s.get('checks_isolation'),
                 "customer_startup": self.s.get('customer_startup'),
                 "credentials_persisted": False, "ms67_complete": False,
                 "limitations": ["Controlled drains qualify evacuation, not unplanned power/region failure.",
                                 "Availability is sampled; sub-sample interruptions are not ruled out.",
                                 "The 18 intentional journey failure scenarios are outside the availability sampling windows."]}
        return sign(value, self.key, self.signer)


def verify_customer_mode(mode):
    if mode is not None:
        require(mode.get('status') == 'passed' and mode.get('applied') is True
                and mode.get('service') == 'customer' and mode.get('setting') == 'LIQUIBASE_ENABLED'
                and mode.get('before') in {'true', 'absent-default-true'} and mode.get('after') == 'false'
                and mode.get('pre_state') == mode.get('post_state')
                and re.fullmatch(HEX, mode.get('pre_state', {}).get('state_sha256', ''))
                and re.fullmatch(HEX, mode.get('old_spec_sha256', ''))
                and re.fullmatch(HEX, mode.get('new_spec_sha256', ''))
                and mode['old_spec_sha256'] != mode['new_spec_sha256']
                and mode.get('migration_metadata') == [
                    {'customer_changesets': 3, 'expected_changesets': 3, 'successful_changesets': 3},
                    {'locks': 1, 'unlocked': 1}], 'customer-startup-mode-proof-invalid')
        verify_availability(mode['availability'], 2)


def verify_observation(value, key, bindings, images, candidates, environment):
    from .cloudbank_ms65_rehearsal_gke import validate_shared_journeys
    verified(value, key)
    require(value.get("observation_type") == OBSERVATION_TYPE and value.get("status") == PASS
            and value.get("bindings") == bindings and value.get("baseline_images") == images
            and value.get("candidate_images") == candidates and value.get("environment") == environment
            and value.get("recovery") == {"status": "restored", "errors": []}
            and value.get("credentials_persisted") is False, "final-drills-passing-bound-evidence-required")
    done = value.get("completed", {})
    verify_customer_mode(value.get('customer_startup'))
    require(set(done) == {"rolling", "resilience", "cutover"}, "all-final-drill-groups-required")
    rolling = done["rolling"]
    require(rolling.get("baseline_restored") is True and [r.get("service") for r in rolling.get("rows", [])] == list(SERVICES),
            "eight-measured-rollouts-required")
    for row in rolling["rows"]:
        s = row["service"]
        require(row.get("previous_image") == images[s] and row.get("candidate_image") == candidates[s]
                and images[s].split("@")[1] != candidates[s].split("@")[1]
                and row.get("completed") is True and row.get("maximum_unavailable") == 0, "measured-rollout-invalid")
        verify_availability(row["availability"], 2)
    require(set(done["resilience"]) == {"node", "failure-domain"}, "both-evacuations-required")
    for row in done["resilience"].values():
        require(row.get("affected_pods", 0) > 0 and row.get("pre_state") == row.get("post_state")
                and re.fullmatch(HEX, row.get("pre_state", {}).get("state_sha256", ""))
                and row.get("all_services_recovered") is True and row.get("node_scheduling_restored") is True,
                "evacuation-state-or-recovery-invalid")
        verify_availability(row["availability"], 1)
    cutover = done["cutover"]
    require(cutover.get("states") == CUTOVER_STATES and cutover.get("canary_percent") == 50
            and cutover.get("target_traffic_percent") == 100 and cutover.get("business_journey_count") == 18
            and cutover.get("rollback_exercised") is True and cutover.get("all_services_recovered") is True
            and re.fullmatch(HEX, cutover.get("pre_state_sha256", ""))
            and cutover["pre_state_sha256"] == cutover.get("post_rollback_state_sha256"), "cutover-state-invalid")
    for stage, count in (("canary", 4), ("target", 2), ("restored", 2)):
        rows = cutover.get("routes", {}).get(stage, {})
        require(set(rows) == set(SERVICES) and all(r.get("ready_endpoint_count") == count
                and re.fullmatch(HEX, r.get("pod_uids_sha256", "")) for r in rows.values()), "cutover-route-proof-invalid")
        if stage == "canary":
            require(all(r.get("candidate_request", {}).get("http_status") == 200 for r in rows.values()),
                    "positive-candidate-requests-required")
    journeys = value.get("target_journeys") or {}
    validate_shared_journeys(journeys, key, ms64_sha256=bindings["ms64_receipt_sha256"],
                            image_lock_sha256=bindings["candidate_image_lock_sha256"], environment=environment)
    attempt = cutover.get('journey_attempt', {})
    isolation = cutover.get('checks_isolation', {})
    require(cutover.get('journeys_sha256') == journeys['content_sha256'], 'cutover-journey-binding-invalid')
    verify_cutover_attempt(value, journeys, attempt, isolation)
    return value


def verify_cutover_attempt(value, journeys, attempt, isolation):
    require(attempt == value.get('cutover_attempt') and attempt.get('parent_run_id') == value.get('run_id')
            and re.fullmatch(r'ms67-cutover-[0-9a-f]{32}', attempt.get('run_id', ''))
            and journeys.get("run_id") == attempt['run_id'],
            "cutover-journey-binding-invalid")
    require(isolation == value.get('checks_isolation') and isolation.get('status') == 'restored'
            and isolation.get('journey_run_id') == attempt['run_id']
            and isolation.get('original_replicas') == isolation.get('restored_replicas') == 2
            and isolation.get('baseline_pods_observed') == 0 and isolation.get('candidate_pods_observed') == 2
            and bool(isolation.get('baseline_uid'))
            and all(re.fullmatch(HEX, isolation.get(k, '')) for k in
                ('baseline_spec_sha256', 'candidate_pod_uids_sha256', 'restored_pod_uids_sha256')),
            'cutover-checks-consumer-isolation-proof-invalid')
    return value
