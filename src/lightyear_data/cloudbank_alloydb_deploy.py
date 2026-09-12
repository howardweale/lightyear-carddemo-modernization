"""Materialize an isolated AlloyDB target from a bound synthetic Cloud SQL deployment."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import secrets
import re
import time

from .cloudbank_journeys import require, hashed
from .cloudbank_managed_target import ManagedGkeRuntime, PROVIDERS, observe_target, resolve_database, validate_profile
from .cloudbank_ms66_dual_lane import image_rows
from .cloudbank_whole_application_equivalence import SERVICES
from .contracts import seal, content_hash

PROBE_IMAGE = ("us-west1-docker.pkg.dev/lightyear-ms67-nonproduction/cloudbank-ms67/"
               "journey-probe@sha256:b5b4b05dfceede8b8e081f7881b6030e87ba9cf77793c06d48cd9f310a0ccc40")


def grant_secret_access(project, namespace, reader, command):
    if reader:
        require(re.fullmatch(r"[a-z][a-z0-9-]+@" + re.escape(project) + r"\.iam\.gserviceaccount\.com", reader)
                is not None, "ms71-secret-reader-identity-invalid")
        member = "serviceAccount:" + reader
    else:
        number = command(["gcloud", "--quiet", "--project=" + project, "projects", "describe", project,
                          "--format=value(projectNumber)"]).strip()
        require(number.isdigit(), "ms71-project-number-invalid")
        member = ("principal://iam.googleapis.com/projects/" + number +
                  "/locations/global/workloadIdentityPools/" + project + ".svc.id.goog/subject/ns/" +
                  namespace + "/sa/cloudbank-secret-reader")
    for service in SERVICES:
        command(["gcloud", "--quiet", "--project=" + project, "secrets", "add-iam-policy-binding",
                 "cloudbank-ms71-alloydb-" + service, "--member=" + member,
                 "--role=roles/secretmanager.secretAccessor", "--condition=None"])


def copy_resource(value, namespace, source_address, target_address):
    value = copy.deepcopy(value)
    value.pop("status", None)
    meta = value["metadata"]
    value["metadata"] = {k: v for k, v in meta.items() if k in {"name", "labels", "annotations"}}
    value["metadata"]["namespace"] = namespace
    annotations = value["metadata"].get("annotations", {})
    for key in list(annotations):
        if key in {"kubectl.kubernetes.io/last-applied-configuration", "deployment.kubernetes.io/revision"}:
            del annotations[key]
    if value["kind"] == "Service":
        for field in ("clusterIP", "clusterIPs", "ipFamilies", "ipFamilyPolicy", "healthCheckNodePort"):
            value["spec"].pop(field, None)
        require(value["spec"].get("type", "ClusterIP") == "ClusterIP", "ms71-service-type-unsupported")
    if value["kind"] == "Deployment":
        value["spec"]["replicas"] = 0
    if value["kind"] == "NetworkPolicy":
        for rule in value["spec"].get("egress", []):
            for peer in rule.get("to", []):
                if peer.get("ipBlock", {}).get("cidr") == source_address + "/32":
                    peer["ipBlock"]["cidr"] = target_address + "/32"
    return value


def application_secret(values, address, database, username, password):
    values = dict(values)
    for prefix in ("SPRING_DATASOURCE_", "LIQUIBASE_DATASOURCE_"):
        values.update({prefix + "URL": f"jdbc:postgresql://{address}:5432/{database}?sslmode=require",
                       prefix + "USERNAME": username, prefix + "PASSWORD": password})
    return values


SEED_SCRIPT = r'''set -eu
export PGCONNECT_TIMEOUT=15
export PGPASSWORD="$SOURCE_PASSWORD"
pg_dump --host="$SOURCE_HOST" --username="$SOURCE_USER" --dbname="$DATABASE" \
  --no-owner --no-acl --format=plain --file=/tmp/cloudbank.sql
export PGHOST="$TARGET_HOST" PGUSER=postgres PGPASSWORD="$ADMIN_PASSWORD" PGSSLMODE=require
psql -X --no-password --set=ON_ERROR_STOP=1 --dbname=postgres <<'SQL'
\getenv app_password APP_PASSWORD
\getenv app_user APP_USER
\getenv database DATABASE
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:'app_user') \gexec
GRANT :"app_user" TO postgres;
SELECT format('CREATE DATABASE %I OWNER %I', :'database', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname=:'database') \gexec
SQL
psql -X --no-password --set=ON_ERROR_STOP=1 --dbname="$DATABASE" <<'SQL'
\getenv app_user APP_USER
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";
SQL
export PGUSER="$APP_USER" PGPASSWORD="$APP_PASSWORD"
tables="$(psql -X --no-password --set=ON_ERROR_STOP=1 --dbname="$DATABASE" -Atc \
  "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE c.relkind IN ('r','p') AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
   AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
     AND d.objid=c.oid AND d.refclassid='pg_extension'::regclass AND d.deptype='e')")"
[ "$tables" = 0 ] || { echo MS71_SEED_REQUIRES_EMPTY_TARGET; exit 1; }
# An earlier empty-target attempt can have created this schema before its first table.
# No CASCADE: a nonempty schema or any existing application table still blocks replay.
psql -X --no-password --set=ON_ERROR_STOP=1 --dbname="$DATABASE" \
  -c 'DROP SCHEMA IF EXISTS cloudbank_customer; DROP SCHEMA IF EXISTS user_repo' >/dev/null
psql -X --no-password --set=ON_ERROR_STOP=1 --single-transaction --dbname="$DATABASE" --file=/tmp/cloudbank.sql >/dev/null
rm /tmp/cloudbank.sql
echo MS71_SEED_COMPLETE
'''


def seed_pod(namespace, source_address, target_address, database, image):
    env = [{"name": name, "value": value} for name, value in (
        ("SOURCE_HOST", source_address), ("TARGET_HOST", target_address), ("DATABASE", database))]
    for name in ("SOURCE_USER", "SOURCE_PASSWORD", "ADMIN_PASSWORD", "APP_USER", "APP_PASSWORD"):
        env.append({"name": name, "valueFrom": {"secretKeyRef": {"name": "ms71-seed-credentials", "key": name}}})
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "ms71-seed", "namespace": namespace,
        "labels": {"app.kubernetes.io/name": "ms71-seed", "lightyear.ai/milestone": "ms71"}},
        "spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
        "activeDeadlineSeconds": 1800, "securityContext": {"runAsNonRoot": True, "runAsUser": 70,
            "runAsGroup": 70, "seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [{"name": "seed", "image": image, "command": ["sh", "-c", SEED_SCRIPT], "env": env,
            "securityContext": {"readOnlyRootFilesystem": True, "allowPrivilegeEscalation": False,
                                 "capabilities": {"drop": ["ALL"]}},
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1", "memory": "512Mi"}},
            "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}],
        "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "512Mi"}}]}}


def deploy(source_profile, target_profile, image_lock, *, admin_secret, output: Path, command,
           probe_image=PROBE_IMAGE, progress=print, resume=False):
    for p in (source_profile, target_profile):
        validate_profile(p)
    require(source_profile["provider"] == PROVIDERS[0] and target_profile["provider"] == PROVIDERS[1]
            and all(source_profile[k] == target_profile[k] for k in ("project", "region", "cluster", "databases"))
            and source_profile["namespace"] != target_profile["namespace"], "ms71-deployment-targets-invalid")
    images = image_rows(image_lock)
    require(re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", probe_image) is not None, "ms71-immutable-seed-image-required")
    project = target_profile["project"]
    context = f"gke_{project}_{target_profile['region']}_{target_profile['cluster']}"
    namespace = target_profile["namespace"]
    base = ["gcloud", "--quiet", "--project=" + project]
    def kube(*args, **kwargs):
        return command(["kubectl", "--context", context, "--request-timeout=60s", *args], **kwargs)
    def apply(obj):
        return kube("apply", "-f", "-", data=json.dumps(obj), timeout=180)
    source = ManagedGkeRuntime(**{k: source_profile[k] for k in ("project", "region", "cluster", "namespace")},
                        images=images, run_id="ms71-deploy", output=output)
    source_identity = observe_target(source, source_profile, command)
    target_db = resolve_database(target_profile, command)
    require(source_identity["database"]["address"] != target_db["address"], "ms71-target-isolation-invalid")
    existing = kube("get", "namespace", namespace, "--ignore-not-found", "-o", "json").strip()
    if resume:
        state = json.loads((output / "deployment-state.json").read_text(encoding="utf-8"))
        require(state.get("content_sha256") == content_hash(state), "ms71-deployment-state-hash-invalid")
        current = json.loads(existing) if existing else {}
        require(current.get("metadata", {}).get("uid") == state["namespace_uid"]
                and current["metadata"].get("labels", {}).get("lightyear.ai/managed-by") == "ms71-alloydb-deploy"
                and state["profile_sha256"] == target_profile["content_sha256"]
                and state["database"] == target_db, "ms71-deployment-resume-identity-drift")
        require(state["phase"] in {"resources-created-services-stopped", "seed-started", "seeded",
            "seeded-and-temporary-credentials-removed", "eight-services-ready"}, "ms71-deployment-manual-recovery-required")
        state.pop("content_sha256", None)
    else:
        require(not existing, "ms71-fresh-target-namespace-required")
        output.mkdir(parents=True, exist_ok=False)
        progress("MS71_DEPLOY_PHASE=create-isolated-namespace")
        apply({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace,
            "labels": {"environment": "non-production", "lightyear.ai/milestone": "ms71",
                       "lightyear.ai/managed-by": "ms71-alloydb-deploy"}}})
        uid = json.loads(kube("get", "namespace", namespace, "-o", "json"))["metadata"]["uid"]
        state = {"namespace": namespace, "namespace_uid": uid, "profile_sha256": target_profile["content_sha256"],
                 "database": target_db, "phase": "namespace-created", "MS71_COMPLETE": False}
    seeded = state["phase"] in {"seeded", "seeded-and-temporary-credentials-removed", "eight-services-ready"}
    def checkpoint(phase):
        state["phase"] = phase
        (output / "deployment-state.json").write_text(json.dumps(seal(state), indent=2) + "\n", encoding="utf-8")
    if not resume:
        checkpoint("namespace-created")
    admin = json.loads(command(base + ["secrets", "versions", "access", "latest", "--secret=" + admin_secret]))
    require(admin.get("resource") == target_profile["resource"].split("/instances/")[0], "ms71-admin-secret-binding-invalid")
    app_user, app_password = "cloudbank_ms71", secrets.token_urlsafe(36)
    if resume:
        saved = json.loads(command(base + ["secrets", "versions", "access", "latest",
                                           "--secret=cloudbank-ms71-alloydb-checks"]))
        require(saved.get("SPRING_DATASOURCE_USERNAME") == app_user, "ms71-resume-application-user-drift")
        app_password = saved["SPRING_DATASOURCE_PASSWORD"]
    source_credentials = source.secret_json("cloudbank-checks-external")
    databases = {d for d in target_profile["databases"].values() if d is not None}
    require(len(databases) == 1, "ms71-seed-shared-database-required")
    database = next(iter(databases))
    progress("MS71_DEPLOY_PHASE=store-isolated-application-secrets")
    for service in (() if resume else SERVICES):
        values = source.secret_json("cloudbank-" + service + "-external")
        if target_profile["databases"][service] is not None:
            values = application_secret(values, target_db['address'], database, app_user, app_password)
        name = "cloudbank-ms71-alloydb-" + service
        # Do not overwrite another attempt's credential or append to an existing secret.
        command(base + ["secrets", "create", name, "--replication-policy=automatic"])
        command(base + ["secrets", "versions", "add", name, "--data-file=-"], data=json.dumps(values))
    if not resume:
        checkpoint("application-secrets-created")
    resources = []
    for kind in ("serviceaccounts", "configmaps", "secretstores", "externalsecrets", "services", "poddisruptionbudgets", "networkpolicies", "deployments"):
        rows = json.loads(kube("-n", source_profile["namespace"], "get", kind, "-o", "json"))["items"]
        for row in rows:
            if row["metadata"]["name"] in {"default", "kube-root-ca.crt"}:
                continue
            item = copy_resource(row, namespace, source_identity["database"]["address"], target_db["address"])
            if item["kind"] == "Deployment":
                service = item["metadata"]["name"]
                require(service in SERVICES and next(c["image"] for c in item["spec"]["template"]["spec"]["containers"]
                    if c["name"] == service) == images[service], "ms71-cloned-image-drift")
            if item["kind"] == "ExternalSecret":
                service = item["metadata"]["name"].removeprefix("cloudbank-")
                require(service in SERVICES, "ms71-external-secret-scope-invalid")
                item["spec"]["dataFrom"] = [{"extract": {"key": "cloudbank-ms71-alloydb-" + service}}]
            if item["kind"] == "ServiceAccount":
                gsa = item["metadata"].get("annotations", {}).get("iam.gke.io/gcp-service-account")
                if gsa:
                    command(base + ["iam", "service-accounts", "add-iam-policy-binding", gsa,
                        "--role=roles/iam.workloadIdentityUser", "--member=serviceAccount:" + project +
                        ".svc.id.goog[" + namespace + "/" + item["metadata"]["name"] + "]"])
                if item["metadata"]["name"] == "cloudbank-secret-reader":
                    grant_secret_access(project, namespace, gsa, command)
            resources.append(item)
    require({r["metadata"]["name"] for r in resources if r["kind"] == "Deployment"} == set(SERVICES),
            "ms71-eight-deployments-required")
    apply({"apiVersion": "v1", "kind": "List", "items": resources})
    if not seeded:
        checkpoint("resources-created-services-stopped")
    # Only this disposable seed pod can reach both databases. Applications can reach AlloyDB only.
    policy = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "ms71-seed-only", "namespace": namespace},
        "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "ms71-seed"}}, "policyTypes": ["Egress"],
            "egress": [{"to": [{"ipBlock": {"cidr": address + "/32"}} for address in
                (source_identity["database"]["address"], target_db["address"])], "ports": [{"protocol": "TCP", "port": 5432}]}]}}
    if not seeded:
        apply(policy)
    secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "ms71-seed-credentials", "namespace": namespace},
        "stringData": {"SOURCE_USER": source_credentials["SPRING_DATASOURCE_USERNAME"],
            "SOURCE_PASSWORD": source_credentials["SPRING_DATASOURCE_PASSWORD"], "ADMIN_PASSWORD": admin["password"],
            "APP_USER": app_user, "APP_PASSWORD": app_password}}
    if not seeded:
        kube("create", "-f", "-", data=json.dumps(secret))
        pod = seed_pod(namespace, source_identity["database"]["address"], target_db["address"], database, probe_image)
        kube("create", "-f", "-", data=json.dumps(pod))
        checkpoint("seed-started")
        progress("MS71_DEPLOY_PHASE=copy-consistent-synthetic-database-snapshot")
        try:
            deadline = time.monotonic() + 1800
            while True:
                pod_state = json.loads(kube("-n", namespace, "get", "pod/ms71-seed", "-o", "json"))["status"]["phase"]
                require(pod_state != "Failed", "ms71-seed-pod-failed")
                if pod_state == "Succeeded":
                    break
                require(time.monotonic() < deadline, "ms71-seed-timeout")
                time.sleep(5)
            require(kube("-n", namespace, "logs", "ms71-seed").strip().endswith("MS71_SEED_COMPLETE"), "ms71-seed-incomplete")
            checkpoint("seeded")
        finally:
            kube("-n", namespace, "delete", "pod/ms71-seed", "secret/ms71-seed-credentials", "networkpolicy/ms71-seed-only", "--wait=true", "--ignore-not-found")
    else:
        kube("-n", namespace, "delete", "pod/ms71-seed", "secret/ms71-seed-credentials", "networkpolicy/ms71-seed-only", "--wait=true", "--ignore-not-found")
    checkpoint("seeded-and-temporary-credentials-removed")
    model_policy = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
        "metadata": {"name": "ms71-alloydb-model-ingress", "namespace": "cloudbank-model"},
        "spec": {"podSelector": {"matchLabels": {"app.kubernetes.io/name": "ollama"}}, "policyTypes": ["Ingress"],
            "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": namespace}},
                "podSelector": {"matchLabels": {"app.kubernetes.io/name": "chatbot"}}}],
                "ports": [{"protocol": "TCP", "port": 11434}]}]}}
    apply(model_policy)
    kube("-n", namespace, "wait", "externalsecret", "--all", "--for=condition=Ready", "--timeout=5m", timeout=330)
    for service in SERVICES:
        progress("MS71_DEPLOY_PHASE=start-" + service)
        kube("-n", namespace, "scale", "deployment/" + service, "--replicas=2")
        kube("-n", namespace, "rollout", "status", "deployment/" + service, "--timeout=10m", timeout=630)
    checkpoint("eight-services-ready")
    return {**state, "status": "target-deployed", "MS71_COMPLETE": False}
