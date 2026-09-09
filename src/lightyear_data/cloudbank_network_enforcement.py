"""Live MS67 TCP enforcement with policy-equivalent, non-serving probe pods.

No deployment, existing policy, credential or database is changed. A connection
timeout qualifies only with reachable positive controls before and after it.
The run owns a small namespace, three ConfigMaps, one egress-only test policy,
and twelve temporary pods. Recovery deletes only recorded owned resources.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import time

from .cloudbank_journeys import JourneyFailure, SERVICES, hashed, require
from .cloudbank_journeys_gke import command
from .cloudbank_secret_rotation_gke import utc
from .contracts import content_hash, verify_signature

STATE_TYPE = "lightyear-cloudbank-ms67-network-recovery"
OBSERVATION_TYPE = "lightyear-cloudbank-ms67-network-enforcement-observation"
STATE_FILE = "network-enforcement.recovery.json"
OBSERVATION_FILE = "network-enforcement.observation.json"
PASS = "passed-bounded-network-enforcement"
LABEL = "lightyear.ai/network-run"
ROLE = "lightyear.ai/network-role"
INTENT = "lightyear.ai/network-intent"
LEASE = "ly-ms67-network-enforcement"
GATE = "lightyear.ai/never-serve-application-traffic"
JAVA = ["java", "-Xms8m", "-Xmx24m", "-XX:ActiveProcessorCount=1", "-XX:-UsePerfData", "-cp", "/probe", "NetworkProbe"]
RESOURCES = {"Namespace": ("v1", "namespaces"), "ServiceAccount": ("v1", "serviceaccounts"),
             "ConfigMap": ("v1", "configmaps"), "Pod": ("v1", "pods"),
             "NetworkPolicy": ("networking.k8s.io/v1", "networkpolicies"),
             "Lease": ("coordination.k8s.io/v1", "leases")}
HEX = r"[0-9a-f]{64}"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def selector_matches(selector, labels):
    require(isinstance(selector, dict) and set(selector) <= {"matchLabels", "matchExpressions"}, "network-selector-unsupported")
    if not all(labels.get(k) == v for k, v in selector.get("matchLabels", {}).items()):
        return False
    for row in selector.get("matchExpressions", []):
        op, key, values = row.get("operator"), row.get("key"), row.get("values", [])
        require(op in {"In", "NotIn", "Exists", "DoesNotExist"} and isinstance(key, str), "network-selector-unsupported")
        if op == "In" and labels.get(key) not in values:
            return False
        if op == "NotIn" and key in labels and labels[key] in values:
            return False
        if op == "Exists" and key not in labels:
            return False
        if op == "DoesNotExist" and key in labels:
            return False
    return True


def selected(policies, labels, direction=None):
    result = []
    for policy in policies:
        spec = policy["spec"]
        types = spec.get("policyTypes", ["Ingress"] + (["Egress"] if "egress" in spec else []))
        if selector_matches(spec.get("podSelector", {}), labels) and (direction is None or direction in types):
            result.append({"uid": policy["metadata"]["uid"], "spec_sha256": hashed(spec)})
    return sorted(result, key=lambda row: row["uid"])


def ipv4(value):
    try:
        parsed = ipaddress.IPv4Address(value)
    except (ValueError, TypeError):
        raise JourneyFailure("network-ipv4-target-required") from None
    require(not parsed.is_unspecified and not parsed.is_multicast, "network-unicast-target-required")
    return str(parsed)


def compiled_probe(root):
    folder = root / "factory/cloudbank/platform-qualification/gke/network-probe"
    value = json.loads((folder / "compiled.json").read_text(encoding="utf-8"))
    data = base64.b64decode(value["class_base64"], validate=True)
    require(value["release"] == 17 and value["source_sha256"] == digest((folder / "NetworkProbe.java").read_bytes())
            and value["class_sha256"] == digest(data) and data[:8] == bytes.fromhex("cafebabe0000003d"),
            "network-probe-artifact-invalid")
    return value


def mark(obj, run_id):
    obj = copy.deepcopy(obj)
    meta = obj["metadata"]
    meta.setdefault("labels", {})[LABEL] = run_id
    meta.setdefault("annotations", {})[INTENT] = hashed(obj)
    return obj


def pod_object(namespace, name, labels, image, config, nonce, run_id, role, service_account="default"):
    # A controller reference prevents a ReplicaSet from adopting a probe that
    # copies its selector labels. The unsatisfied readiness gate excludes it
    # from Services while its policy selector labels remain identical.
    return mark({"apiVersion": "v1", "kind": "Pod", "metadata": {
        "name": name, "namespace": namespace, "labels": {**labels, ROLE: role},
        "ownerReferences": [{"apiVersion": "v1", "kind": "ConfigMap", "name": config["metadata"]["name"],
                             "uid": config["metadata"]["uid"], "controller": True, "blockOwnerDeletion": False}]},
        "spec": {"serviceAccountName": service_account, "automountServiceAccountToken": False,
            "restartPolicy": "Never", "activeDeadlineSeconds": 1800, "terminationGracePeriodSeconds": 1,
            "enableServiceLinks": False, "readinessGates": [{"conditionType": GATE}],
            "securityContext": {"runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532,
                                "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [{"name": "probe", "image": image, "command": JAVA + ["serve", nonce],
                "env": [{"name": k, "value": ""} for k in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")],
                "readinessProbe": {"tcpSocket": {"port": 19067}, "periodSeconds": 2, "failureThreshold": 30},
                "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]}},
                "resources": {"requests": {"cpu": "50m", "memory": "96Mi"},
                              "limits": {"cpu": "500m", "memory": "192Mi"}},
                "volumeMounts": [{"name": "probe", "mountPath": "/probe", "readOnly": True}]}],
            "volumes": [{"name": "probe", "configMap": {"name": config["metadata"]["name"], "defaultMode": 292}}]}}, run_id)


def route_guard(pods, services, slices):
    for pod in pods:
        require(not any(c.get("type") == "Ready" and c.get("status") == "True"
                        for c in pod.get("status", {}).get("conditions", [])), "network-probe-became-ready")
        labels = pod["metadata"].get("labels", {})
        for service in services:
            selector = service.get("spec", {}).get("selector", {})
            if selector and all(labels.get(k) == v for k, v in selector.items()):
                require(service["spec"].get("publishNotReadyAddresses", False) is False,
                        "network-service-publishes-unready-probes")
        for item in slices:
            for endpoint in item.get("endpoints", []):
                if endpoint.get("targetRef", {}).get("uid") == pod["metadata"].get("uid"):
                    require(endpoint.get("conditions", {}).get("ready") is False
                            and endpoint.get("conditions", {}).get("serving", False) is False,
                            "network-probe-became-serving-endpoint")


def minimized(obj):
    return {"uid": obj["metadata"]["uid"], "spec_sha256": hashed(obj.get("spec", {}))}


def subset(expected, actual):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(subset(x, y) for x, y in zip(expected, actual))
    return expected == actual


def resource_differences(expected, actual):
    """Return bounded field paths; tolerate only EnvVar's empty-value encoding.

    Kubernetes core/v1.EnvVar.Value uses json omitempty and defaults to "".
    The signed intent remains unchanged. A valueFrom source, nonempty value,
    missing variable, changed image or changed sandbox is still a mismatch.
    """
    differences = []

    def mismatch(path):
        if len(differences) < 16:
            differences.append("/" + "/".join(str(k).replace("~", "~0").replace("/", "~1") for k in path))

    def compare(wanted, observed, path=()):
        if isinstance(wanted, dict) and isinstance(observed, dict):
            if (expected.get("kind") == "Pod" and len(path) == 5
                    and path[:2] == ("spec", "containers") and path[3] == "env" and wanted.get("value") == ""):
                if "valueFrom" in observed:
                    mismatch(path + ("valueFrom",))
                observed = {"value": "", **observed}
            for key, value in wanted.items():
                if key not in observed:
                    mismatch(path + (key,))
                else:
                    compare(value, observed[key], path + (key,))
        elif isinstance(wanted, list) and isinstance(observed, list):
            if len(wanted) != len(observed):
                mismatch(path)
            else:
                for index, (left, right) in enumerate(zip(wanted, observed)):
                    compare(left, right, path + (index,))
        elif type(wanted) is not type(observed) or wanted != observed:
            mismatch(path)

    compare(expected, actual)
    return differences


class Backend:
    def __init__(self, runtime):
        self.r = runtime

    def q(self, namespace, *args, data=None, timeout=60):
        return command(["kubectl", "--context", self.r.context, "--request-timeout=" + str(timeout) + "s",
                        *(["--namespace", namespace] if namespace else []), *args], data=data, timeout=timeout + 10)

    def get(self, namespace, kind, name=None):
        raw = self.q(namespace, "get", kind, *([name, "--ignore-not-found"] if name else []), "-o", "json")
        return json.loads(raw) if raw.strip() else None

    def create(self, obj):
        return json.loads(self.q(obj["metadata"].get("namespace"), "create", "-f", "-", "-o", "json", data=json.dumps(obj)))

    def delete(self, obj):
        meta, kind = obj["metadata"], obj["kind"]
        version, plural = RESOURCES[kind]
        path = ("/api/" + version if version == "v1" else "/apis/" + version)
        if kind != "Namespace":
            path += "/namespaces/" + meta["namespace"]
        path += "/" + plural + "/" + meta["name"]
        # --raw DELETE reads the DeleteOptions file; UID prevents replacement deletion.
        payload = {"apiVersion": "v1", "kind": "DeleteOptions", "preconditions": {"uid": meta["uid"]}}
        if kind != "Pod":
            payload["preconditions"]["resourceVersion"] = meta["resourceVersion"]
        else:
            payload["gracePeriodSeconds"] = 1
        file = self.r.output / "network-delete-options.json"
        try:
            file.write_text(json.dumps(payload), encoding="utf-8")
            self.q(None, "delete", "--raw", path, "-f", str(file))
        finally:
            file.unlink(missing_ok=True)

    def namespace_snapshot(self, namespace):
        kinds = "deployments,replicasets,pods,services,networkpolicies,endpointslices,ingresses,leases"
        return self.get(namespace, kinds).get("items", [])

    def sql_instance(self, name):
        return json.loads(command(["gcloud", "sql", "instances", "describe", name, "--project", self.r.project, "--format=json"]))

    def connections(self, namespace, pod, cases):
        require(0 < len(cases) <= 32, "network-probe-batch-size-invalid")
        data = "".join(f"{row['id']} {ipv4(row['ip'])} {row['port']} 3000 {row.get('nonce', '-')}\n" for row in cases)
        raw = self.q(namespace, "exec", "-i", pod, "-c", "probe", "--", *JAVA, "connect", data=data, timeout=180)
        try:
            rows = [json.loads(line) for line in raw.splitlines()]
        except ValueError:
            raise JourneyFailure("network-probe-output-invalid") from None
        require([r.get("id") for r in rows] == [r["id"] for r in cases], "network-probe-output-incomplete")
        for row in rows:
            require(set(row) == {"id", "outcome", "elapsed_ms"} and type(row["elapsed_ms"]) is int
                    and 0 <= row["elapsed_ms"] <= 30000, "network-probe-output-invalid")
        return rows


class NetworkRun:
    def __init__(self, backend, journal, state, profile, artifact, progress=lambda _: None):
        self.b, self.j, self.s, self.profile, self.artifact, self.progress = backend, journal, state, profile, artifact, progress
        self.app = self.s["environment"]["namespace"]
        self.model = profile["model_namespace"]
        self.control = "ms67-net-" + self.s["run_id"].split("-")[-1][:20]
        self.nonce = self.s["run_id"].split("-")[-1]
        self.prefix = "ly-net-" + self.nonce[:12]

    def save(self, phase):
        self.s.update(phase=phase, updated_at=utc())
        self.j.write(self.s)

    def create(self, obj):
        # Lease acquisition itself uses the transport directly; subsequent
        # resource creates must recheck ownership in the execution controller.
        self.owned_lock()
        meta = obj["metadata"]
        identity = (obj["kind"], meta.get("namespace"), meta["name"])
        require(not any((r["object"]["kind"], r["object"]["metadata"].get("namespace"), r["object"]["metadata"]["name"]) == identity
                        for r in self.s["resources"]), "network-resource-already-planned")
        require(self.b.get(identity[1], obj["kind"], identity[2]) is None, "network-fresh-resource-required")
        row = {"object": obj, "uid": None}
        self.s["resources"].append(row)
        self.save("before-create-" + obj["kind"].lower())
        value = self.b.create(obj)
        row["uid"] = value["metadata"]["uid"]
        differences = resource_differences(obj, value)
        if differences:
            self.s["resource_mismatches"] = [{"kind": obj["kind"], "paths": differences}]
        require(not differences, "network-created-resource-mutated")
        # The next pre-mutation checkpoint commits this UID. A lost create reply
        # is recoverable from the already durable intent and exact owned object.
        return value

    def snapshot(self):
        baseline, roles, inventories = {}, {}, {}
        owned_uids = {r["uid"] for r in self.s.get("resources", []) if r.get("uid")}
        for namespace in (self.app, self.model):
            ns = self.b.get(None, "Namespace", namespace)
            require(ns and ns["metadata"].get("labels", {}).get("environment") in {"non-production", "nonprod", "test", "sandbox"},
                    "network-nonproduction-namespace-required")
            items = self.b.namespace_snapshot(namespace)
            inventories[namespace] = items
            by_kind = {kind: [o for o in items if o["kind"] == kind and o["metadata"].get("uid") not in owned_uids]
                       for kind in ("Deployment", "ReplicaSet", "Pod", "Service", "NetworkPolicy", "Ingress")}
            baseline[namespace] = {"namespace": {"uid": ns["metadata"]["uid"], "labels_sha256": hashed(ns["metadata"].get("labels", {}))},
                                  "policies": sorted([minimized(p) for p in by_kind["NetworkPolicy"]], key=lambda v: v["uid"]),
                                  "services": sorted([minimized(p) for p in by_kind["Service"]], key=lambda v: v["uid"]),
                                  "workloads": {}}
            expected = self.s["images"] if namespace == self.app else {"ollama": self.profile["model_image"]}
            for service, image in expected.items():
                deps = [d for d in by_kind["Deployment"] if d["metadata"]["name"] == service]
                require(len(deps) == 1, "network-deployment-missing")
                deploy = deps[0]
                spec, status = deploy["spec"], deploy.get("status", {})
                require(spec.get("replicas") == 2 and status.get("readyReplicas") == 2 and status.get("updatedReplicas") == 2
                        and status.get("availableReplicas") == 2 and status.get("observedGeneration", -1) >= deploy["metadata"]["generation"],
                        "network-two-ready-replicas-required")
                sets = {rs["metadata"]["uid"] for rs in by_kind["ReplicaSet"] if any(r.get("controller") is True
                        and r.get("uid") == deploy["metadata"]["uid"] for r in rs["metadata"].get("ownerReferences", []))}
                pods = [p for p in by_kind["Pod"] if any(r.get("controller") is True and r.get("uid") in sets
                                                       for r in p["metadata"].get("ownerReferences", []))]
                require(len(pods) == 2, "network-owned-pod-count-invalid")
                labels = pods[0]["metadata"].get("labels", {})
                policies = by_kind["NetworkPolicy"]
                cohort = selected(policies, labels)
                require(selected(policies, labels, "Ingress") and selected(policies, labels, "Egress"), "network-workload-not-isolated")
                for pod in pods:
                    containers = pod["spec"].get("containers", [])
                    statuses = pod.get("status", {}).get("containerStatuses", [])
                    security = pod["spec"].get("securityContext", {})
                    require(not pod["metadata"].get("deletionTimestamp") and not pod["spec"].get("hostNetwork", False)
                            and len(containers) == 1 and containers[0]["name"] == service and containers[0]["image"] == image
                            and len(statuses) == 1 and statuses[0].get("ready") is True
                            and "running" in statuses[0].get("state", {})
                            and statuses[0].get("imageID", "").endswith(image.split("@")[-1])
                            and selected(policies, pod["metadata"].get("labels", {})) == cohort,
                            "network-workload-runtime-or-policy-drift")
                    csec = containers[0].get("securityContext", {})
                    linux = statuses[0].get("user", {}).get("linux", {})
                    require(linux.get("uid") == 65532 and linux.get("gid") == 65532
                            and csec.get("allowPrivilegeEscalation") is False and csec.get("readOnlyRootFilesystem") is True
                            and csec.get("capabilities", {}).get("drop") == ["ALL"]
                            and (csec.get("seccompProfile") or security.get("seccompProfile", {})).get("type") == "RuntimeDefault",
                            "network-runtime-sandbox-invalid")
                role = "model" if service == "ollama" else service
                roles[role] = {"namespace": namespace, "labels": labels, "policies": cohort,
                               "targets": sorted(ipv4(p["status"]["podIP"]) for p in pods)}
                baseline[namespace]["workloads"][service] = {**minimized(deploy),
                    "pods_sha256": hashed(sorted((p["metadata"]["uid"], p["status"]["podIP"], p["spec"]) for p in pods)),
                    "policy_selection": cohort, "ready_replicas": 2, "uid": deploy["metadata"]["uid"]}
            owned_pods = [o for o in items if o["kind"] == "Pod" and o["metadata"].get("uid") in owned_uids]
            route_guard(owned_pods, by_kind["Service"], [o for o in items if o["kind"] == "EndpointSlice"])
        return baseline, roles, inventories

    def preflight(self):
        require(self.b.get(self.app, "lease", LEASE) is None, "network-lock-held-recover-before-another-run")
        baseline, roles, inventories = self.snapshot()
        sql = self.b.sql_instance(self.s["source_instance"])
        ips = [row["ipAddress"] for row in sql.get("ipAddresses", []) if row.get("type") == "PRIVATE"]
        require(sql.get("name") == self.s["source_instance"] and sql.get("region") == self.s["environment"]["region"]
                and sql.get("databaseVersion", "").startswith("POSTGRES_") and sql.get("state") == "RUNNABLE"
                and len(ips) == 1, "network-postgresql-instance-invalid")
        database_ip = ipv4(ips[0])
        ingress = [o for o in inventories[self.app] if o["kind"] == "Ingress"
                   and any(r.get("host") == self.profile["expected_hostname"] for r in o["spec"].get("rules", []))]
        addresses = {row.get("ip") for o in ingress for row in o.get("status", {}).get("loadBalancer", {}).get("ingress", [])}
        require(len(addresses) == 1, "network-bound-public-ingress-required")
        public_ip = ipv4(addresses.pop())
        require(ipaddress.ip_address(public_ip).is_global, "network-public-control-required")
        for namespace, items in inventories.items():
            for lease in [o for o in items if o["kind"] == "Lease"]:
                require(not lease.get("spec", {}).get("holderIdentity"), "network-other-drill-lock-held")
            for role, info in roles.items():
                if info["namespace"] != namespace:
                    continue
                probe_labels = {**info["labels"], LABEL: self.s["run_id"], ROLE: role}
                policies = [o for o in items if o["kind"] == "NetworkPolicy"]
                require(selected(policies, probe_labels) == info["policies"], "network-probe-policy-equivalence-invalid")
                route_guard([{"metadata": {"labels": probe_labels}}], [o for o in items if o["kind"] == "Service"], [])
        self.s.update(baseline=baseline, roles=roles, database_ip=database_ip, public_ip=public_ip,
                      sql_identity_sha256=hashed({"name": sql["name"], "connectionName": sql.get("connectionName"), "ip": database_ip}),
                      ingress_identity_sha256=hashed([minimized(i) for i in ingress]))

    def acquire(self):
        require(self.b.get(self.app, "lease", LEASE) is None, "network-lock-held-recover-before-another-run")
        lease = mark({"apiVersion": "coordination.k8s.io/v1", "kind": "Lease", "metadata": {
            "name": LEASE, "namespace": self.app, "annotations": {"lightyear.ai/recovery-state": self.s["recovery_uri"]}},
            "spec": {"holderIdentity": self.s["run_id"]}}, self.s["run_id"])
        self.s["lease_object"] = lease
        self.save("before-lock")
        value = self.b.create(lease)
        require(subset(lease, value), "network-lock-mismatch")
        self.s["lease_uid"] = value["metadata"]["uid"]
        self.save("lock-held")

    def owned_lock(self):
        value = self.b.get(self.app, "lease", LEASE)
        require(value and self.s.get("lease_object") and subset(self.s["lease_object"], value)
                and self.s.get("lease_uid") in {None, value["metadata"]["uid"]}, "network-lock-ownership-mismatch")
        return value

    def setup(self):
        self.progress("Creating bounded, non-serving policy probes")
        self.acquire()
        self.create(mark({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": self.control,
            "labels": {"environment": "non-production", "pod-security.kubernetes.io/enforce": "restricted"}}}, self.s["run_id"]))
        self.create(mark({"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": self.prefix, "namespace": self.control},
                          "automountServiceAccountToken": False}, self.s["run_id"]))
        configs = {}
        for namespace in (self.control, self.app, self.model):
            configs[namespace] = self.create(mark({"apiVersion": "v1", "kind": "ConfigMap", "immutable": True,
                "metadata": {"name": self.prefix, "namespace": namespace},
                "binaryData": {"NetworkProbe.class": self.artifact["class_base64"]}}, self.s["run_id"]))
        roles = {**self.s["roles"], "sink": {"namespace": self.control, "labels": {}},
                 "default": {"namespace": self.app, "labels": {}}, "wrong-service": {"namespace": self.app, "labels": {}}}
        # This policy selects only the unlabelled, run-owned negative control.
        # It cannot match any application or policy-equivalent cohort pod.
        self.create(mark({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
            "metadata": {"name": self.prefix, "namespace": self.app}, "spec": {
                "podSelector": {"matchLabels": {LABEL: self.s["run_id"], ROLE: "wrong-service"}}, "policyTypes": ["Egress"],
                "egress": [{"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": self.model}},
                                     "podSelector": {"matchLabels": {"app.kubernetes.io/name": "ollama"}}}],
                            "ports": [{"protocol": "TCP", "port": 11434}]}]}}, self.s["run_id"]))
        self.s["probes"] = {}
        for role, info in roles.items():
            namespace = info["namespace"]
            obj = pod_object(namespace, self.prefix + "-" + role, info["labels"], self.s["images"]["testrunner"],
                             configs[namespace], self.nonce, self.s["run_id"], role,
                             self.prefix if namespace == self.control else "default")
            pod = self.create(obj)
            self.s["probes"][role] = {"namespace": namespace, "name": pod["metadata"]["name"], "uid": pod["metadata"]["uid"]}
        self.save("probes-created")
        deadline = time.monotonic() + 240
        while True:
            pending = []
            for role, info in self.s["probes"].items():
                pod = self.b.get(info["namespace"], "Pod", info["name"])
                require(pod and pod["metadata"]["uid"] == info["uid"], "network-probe-identity-drift")
                status = pod.get("status", {})
                require(status.get("phase") not in {"Succeeded", "Failed"}, "network-probe-exited-before-tests")
                if status.get("phase") != "Running" or not status.get("podIP"):
                    pending.append(role)
                    continue
                statuses = status.get("containerStatuses", [])
                if len(statuses) != 1 or "running" not in statuses[0].get("state", {}) or statuses[0].get("ready") is not True:
                    pending.append(role)
                    continue
                require(statuses[0].get("imageID", "").endswith(self.s["images"]["testrunner"].split("@")[-1]), "network-probe-image-drift")
                route_guard([pod], [], [])
                info["ip"] = ipv4(status["podIP"])
            if not pending:
                break
            require(time.monotonic() < deadline, "network-probe-startup-timeout")
            time.sleep(3)
        self.save("probes-running")

    def unchanged(self):
        self.owned_lock()
        current, roles, inventories = self.snapshot()
        require(current == self.s["baseline"], "network-live-baseline-drift")
        for role, original in self.s["roles"].items():
            info = self.s["probes"][role]
            pod = next((o for o in inventories[info["namespace"]] if o["kind"] == "Pod" and o["metadata"]["uid"] == info["uid"]), None)
            require(pod is not None, "network-probe-missing")
            policies = [o for o in inventories[info["namespace"]] if o["kind"] == "NetworkPolicy"]
            require(selected(policies, pod["metadata"].get("labels", {})) == original["policies"], "network-probe-policy-selection-drift")
        require(not self.b.get(self.control, "networkpolicies").get("items"), "network-positive-control-isolated")

    def cases(self):
        cases = []

        def add(role, ident, ip, port, expected, nonce=False):
            cases.append({"role": role, "id": ident, "ip": ipv4(ip), "port": port, "expected": expected,
                          **({"nonce": self.nonce} if nonce else {})})

        for role, probe in self.s["probes"].items():
            add(role, role + "-self", "127.0.0.1", 19067, "nonce-matched", True)
        sink = self.s["probes"]["sink"]["ip"]
        add("sink", "control-listener", sink, 5432, "nonce-matched", True)
        add("sink", "control-sink-route", sink, 19067, "nonce-matched", True)
        add("sink", "control-database", self.s["database_ip"], 5432, "connected")
        add("sink", "control-public-ingress", self.s["public_ip"], 443, "connected")
        add("sink", "default-ingress-denied", self.s["probes"]["default"]["ip"], 19067, "connect-timeout")
        add("default", "default-egress-denied", sink, 19067, "connect-timeout")
        add("model", "model-cross-namespace-egress-denied", sink, 19067, "connect-timeout")
        add("model", "model-database-egress-denied", self.s["database_ip"], 5432, "connect-timeout")
        add("model", "model-public-egress-denied", self.s["public_ip"], 443, "connect-timeout")
        for service in SERVICES:
            add(service, service + "-database-allowed", self.s["database_ip"], 5432, "connected")
            add(service, service + "-other-database-denied", sink, 5432, "connect-timeout")
            add(service, service + "-application-allowed", self.s["roles"]["account"]["targets"][0], 8080, "connected")
            for index, target in enumerate(self.s["roles"]["model"]["targets"]):
                add(service, service + "-model-" + str(index), target, 11434,
                    "connected" if service == "chatbot" else "connect-timeout")
        for index, target in enumerate(self.s["roles"]["model"]["targets"]):
            add("sink", "model-wrong-namespace-" + str(index), target, 11434, "connect-timeout")
            add("wrong-service", "model-wrong-service-" + str(index), target, 11434, "connect-timeout")
        return cases

    def execute(self, cases, phase):
        self.progress("Checking TCP " + phase + " (" + str(len(cases)) + " connections)")
        self.unchanged()
        groups = {role: [row for row in cases if row["role"] == role] for role in sorted({r["role"] for r in cases})}

        def one(item):
            role, rows = item
            info = self.s["probes"][role]
            current = self.b.get(info["namespace"], "Pod", info["name"])
            require(current and current["metadata"]["uid"] == info["uid"], "network-probe-identity-drift")
            actual = self.b.connections(info["namespace"], info["name"], rows)
            return [{"id": expected["id"], "role": role, "phase": phase,
                     "target_sha256": hashed({"ip": expected["ip"], "port": expected["port"]}),
                     "expected": expected["expected"], **observed} for expected, observed in zip(rows, actual)]

        with ThreadPoolExecutor(max_workers=3) as pool:
            results = [row for group in pool.map(one, groups.items()) for row in group]
        self.s.setdefault("checks", []).extend(results)
        self.save(phase + "-observed")
        bad = [r for r in results if r["outcome"] != r["expected"]
               or r["expected"] == "connect-timeout" and r["elapsed_ms"] < 2500]
        self.s["failed_checks"] = bad
        require(not bad, "network-connection-expectation-failed")

    def recover(self):
        errors = []
        lease = self.b.get(self.app, "lease", LEASE)
        if lease is None:
            require(all(self.b.get(r["object"]["metadata"].get("namespace"), r["object"]["kind"],
                                   r["object"]["metadata"]["name"]) is None for r in self.s.get("resources", [])),
                    "network-recovery-lock-missing")
        else:
            self.owned_lock()
        # Delete pods before their ConfigMaps and all children before namespace.
        self.save("restoring")
        for row in reversed(self.s.get("resources", [])):
            obj, uid = row["object"], row.get("uid")
            meta = obj["metadata"]
            try:
                live = self.b.get(meta.get("namespace"), obj["kind"], meta["name"])
                if live is None:
                    row["removed"] = True
                    continue
                differences = resource_differences(obj, live)
                if uid not in {None, live["metadata"]["uid"]}:
                    differences = ["/metadata/uid", *differences][:16]
                if differences and not self.s.get("resource_mismatches"):
                    self.s["resource_mismatches"] = [{"kind": obj["kind"], "paths": differences}]
                require(not differences, "network-recovery-resource-ownership-mismatch")
                # Do not garbage-collect surviving pods through a ConfigMap or
                # namespace when an earlier deletion failed.
                require(not errors or obj["kind"] not in {"ConfigMap", "Namespace"}, "network-recovery-parent-preserved")
                self.b.delete(live)
                deadline = time.monotonic() + 60
                while self.b.get(meta.get("namespace"), obj["kind"], meta["name"]) is not None:
                    require(time.monotonic() < deadline, "network-recovery-removal-unconfirmed")
                    time.sleep(2)
                row["removed"] = True
            except Exception as exc:
                errors.append(str(exc) if isinstance(exc, JourneyFailure) else "network-recovery-delete-failed")
        if not errors:
            self.save("before-release")
            if lease:
                value = self.owned_lock()
                self.b.delete(value)
                require(self.b.get(self.app, "lease", LEASE) is None, "network-lock-removal-unconfirmed")
            self.s["cleanup_complete"] = True
            self.save("restored")
        else:
            self.save("recovery-required")
        return {"status": "restored" if not errors else "recovery-required", "errors": sorted(set(errors)),
                "owned_resources_removed": not errors}

    def run(self):
        self.preflight()
        self.setup()
        all_cases = self.cases()
        positive = [row for row in all_cases if row["expected"] != "connect-timeout"]
        negative = [row for row in all_cases if row["expected"] == "connect-timeout"]
        self.execute(positive, "positive-before")
        self.execute(negative, "denied-first")
        self.execute(negative, "denied-second")
        self.execute(positive, "positive-after")
        self.unchanged()
        recovery = self.recover()
        require(recovery["status"] == "restored", "network-recovery-required")
        final, _, _ = self.snapshot()
        require(final == self.s["baseline"], "network-final-baseline-drift")
        return {"schema_version": "1.0", "observation_type": OBSERVATION_TYPE, "run_id": self.s["run_id"], "status": PASS,
                "environment": self.s["environment"], "bindings": self.s["bindings"], "images": self.s["images"],
                "scope": "policy-equivalent-non-serving-probe-pods", "probe_class_sha256": self.artifact["class_sha256"],
                "probe_image": self.s["images"]["testrunner"], "baseline": self.s["baseline"], "final": final,
                "cases": [{k: v for k, v in row.items() if k not in {"ip", "port", "nonce"}} |
                          {"target_sha256": hashed({"ip": row["ip"], "port": row["port"]})} for row in all_cases],
                "checks": self.s["checks"], "recovery": recovery, "application_mutations": 0,
                "existing_policy_mutations": 0, "database_mutations": 0, "credentials_persisted": False,
                "raw_output_persisted": False, "production_environment": False, "ms67_complete": False, "production_ready": False}


def verify_observation(value, key, bindings, images, environment, artifact):
    require(value.get("content_sha256") == content_hash(value) and verify_signature(value, key), "network-observation-signature-invalid")
    require(value.get("schema_version") == "1.0" and value.get("observation_type") == OBSERVATION_TYPE
            and value.get("status") == PASS and re.fullmatch(r"ms67-network-[0-9a-f]{32}", value.get("run_id", ""))
            and value.get("scope") == "policy-equivalent-non-serving-probe-pods"
            and all(value.get(k) is False for k in ("credentials_persisted", "raw_output_persisted", "production_environment", "ms67_complete", "production_ready"))
            and all(type(value.get(k)) is int and value[k] == 0 for k in ("application_mutations", "existing_policy_mutations", "database_mutations")),
            "network-passing-bounded-observation-required")
    require(value.get("bindings") == bindings and value.get("images") == images
            and value.get("probe_image") == images["testrunner"] and value.get("probe_class_sha256") == artifact["class_sha256"]
            and all(value.get("environment", {}).get(k) == v for k, v in environment.items()), "network-observation-bindings-invalid")
    baseline = value.get("baseline", {})
    require(len(baseline) == 2 and baseline == value.get("final")
            and set(baseline.get(environment["namespace"], {}).get("workloads", {})) == set(SERVICES)
            and value.get("recovery") == {"status": "restored", "errors": [], "owned_resources_removed": True},
            "network-baseline-or-recovery-incomplete")
    for namespace, info in baseline.items():
        require(info.get("namespace", {}).get("uid") and re.fullmatch(HEX, info["namespace"].get("labels_sha256", ""))
                and info.get("policies") and info.get("services") and info.get("workloads"), "network-baseline-evidence-incomplete")
        for workload in info["workloads"].values():
            require(workload.get("ready_replicas") == 2 and workload.get("uid") and workload.get("policy_selection")
                    and re.fullmatch(HEX, workload.get("spec_sha256", ""))
                    and re.fullmatch(HEX, workload.get("pods_sha256", "")), "network-workload-evidence-incomplete")
    required = {}
    roles = [*SERVICES, "model", "default", "sink", "wrong-service"]
    for role in roles:
        required[role + "-self"] = (role, "nonce-matched")
    required.update({"control-listener": ("sink", "nonce-matched"), "control-sink-route": ("sink", "nonce-matched"),
        "control-database": ("sink", "connected"),
        "control-public-ingress": ("sink", "connected"), "default-ingress-denied": ("sink", "connect-timeout"),
        "default-egress-denied": ("default", "connect-timeout"), "model-cross-namespace-egress-denied": ("model", "connect-timeout"),
        "model-database-egress-denied": ("model", "connect-timeout"), "model-public-egress-denied": ("model", "connect-timeout")})
    for service in SERVICES:
        required[service + "-database-allowed"] = (service, "connected")
        required[service + "-application-allowed"] = (service, "connected")
        required[service + "-other-database-denied"] = (service, "connect-timeout")
        for index in range(2):
            required[service + "-model-" + str(index)] = (service, "connected" if service == "chatbot" else "connect-timeout")
    for index in range(2):
        required["model-wrong-namespace-" + str(index)] = ("sink", "connect-timeout")
        required["model-wrong-service-" + str(index)] = ("wrong-service", "connect-timeout")
    cases = value.get("cases", [])
    require(len(cases) == len(required) and {r.get("id") for r in cases} == set(required), "network-case-coverage-incomplete")
    targets = {}
    for row in cases:
        require((row.get("role"), row.get("expected")) == required[row["id"]] and re.fullmatch(HEX, row.get("target_sha256", "")),
                "network-case-invalid")
        targets[row["id"]] = row["target_sha256"]
    for service in SERVICES:
        require(targets[service + "-database-allowed"] == targets["control-database"]
                and targets[service + "-other-database-denied"] == targets["control-listener"],
                "network-database-positive-control-mismatch")
        for index in range(2):
            require(targets[service + "-model-" + str(index)] == targets["chatbot-model-" + str(index)],
                    "network-model-positive-control-mismatch")
    for index in range(2):
        require(targets["model-wrong-namespace-" + str(index)] == targets["chatbot-model-" + str(index)]
                and targets["model-wrong-service-" + str(index)] == targets["chatbot-model-" + str(index)],
                "network-model-positive-control-mismatch")
    require(targets["model-database-egress-denied"] == targets["control-database"]
            and targets["model-public-egress-denied"] == targets["control-public-ingress"]
            and targets["model-cross-namespace-egress-denied"] == targets["control-sink-route"]
            and targets["default-egress-denied"] == targets["control-sink-route"]
            and targets["chatbot-model-0"] != targets["chatbot-model-1"], "network-egress-positive-control-mismatch")
    checks = value.get("checks", [])
    require(len(checks) == 2 * len(required), "network-before-after-or-repeat-coverage-incomplete")
    phases = []
    for row in checks:
        if not phases or phases[-1] != row.get("phase"):
            phases.append(row.get("phase"))
    require(phases == ["positive-before", "denied-first", "denied-second", "positive-after"], "network-positive-control-order-invalid")
    seen = set()
    for row in checks:
        ident, phase = row.get("id"), row.get("phase")
        require(ident in required, "network-unexpected-check")
        role, outcome = required[ident]
        phases = {"denied-first", "denied-second"} if outcome == "connect-timeout" else {"positive-before", "positive-after"}
        require(phase in phases and (ident, phase) not in seen and row.get("role") == role and row.get("expected") == outcome
                and row.get("outcome") == outcome and row.get("target_sha256") == targets[ident]
                and type(row.get("elapsed_ms")) is int and 0 <= row["elapsed_ms"] <= 30000
                and (outcome != "connect-timeout" or row["elapsed_ms"] >= 2500), "network-check-not-proven")
        seen.add((ident, phase))
