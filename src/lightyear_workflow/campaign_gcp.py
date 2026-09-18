"""Bounded, fixed-resource GCP adapter for synthetic paired datatype campaigns."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from lightyear_data.oracle_number_native import IDENTITY_SQL, render_case
from .campaigns import PROJECT, REGION
from .paired_number import parse_observation, postgres_case

CLUSTER = "cloudbank-ms71-alloydb"
INSTANCE = "primary"
SOURCE = "ly-number-oracle"
IAP_RANGE = "35.235.240.0/20"

# Input, including the database password, travels over SSH stdin. Neither the
# cloud command line nor the journal contains it. Remote output is bounded.
REMOTE = r'''
import json,os,subprocess,sys
p=json.load(sys.stdin)
if p['lane']=='oracle':
 # Free Lite's initialized SID can differ in case from image ORACLE_SID.
 # Read the installed instance name, rather than connecting to an idle SID.
 connect="sid=$(awk -F: 'toupper($1)==\"FREE\" {print $1; exit}' /etc/oratab); case \"$sid\" in FREE|free) export ORACLE_SID=\"$sid\";; *) exit 64;; esac; exec sqlplus -L -S / as sysdba"
 a=['sudo','docker','exec','-i','ly-number-oracle','bash','-lc',connect]
 e=os.environ.copy()
else:
 a=['psql','-X','-w','-q','-A','-t','--set=ON_ERROR_STOP=1']
 e={**os.environ,'PGHOST':p['host'],'PGUSER':'postgres','PGDATABASE':'postgres','PGPASSWORD':p['password'],'PGSSLMODE':'require','PGCONNECT_TIMEOUT':'10'}
r=subprocess.run(a,input=p['sql'],text=True,encoding='utf-8',capture_output=True,env=e,timeout=25)
print(json.dumps({'returncode':r.returncode,'stdout':r.stdout[:65536],'stderr':r.stderr[:65536]}))
'''


class GcpRunner:
    evidence_class = "native-database-observed"

    def __init__(self, root: Path, run_id: str, plan: dict, emit):
        if not re.fullmatch(r"(?:number|core100|types260)-[a-f0-9]{32}", run_id):
            raise ValueError("Invalid campaign run ID")
        self.root, self.plan, self.emit = root, plan, emit
        self.run_id = run_id
        self.vm = ('ly-types-' if run_id.startswith(('core100-', 'types260-')) else 'ly-number-') + run_id.split('-', 1)[1][:20]
        self.firewall = self.vm + "-iap"
        self.zone = plan["profile"]["runner_zone"]
        self.deadline = time.monotonic() + plan["profile"]["max_seconds"]
        self.gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
        if not self.gcloud:
            raise ValueError("Google Cloud CLI unavailable")
        from .campaign_engine import run_path
        self.state_path = run_path(root, run_id) / 'resource-state.json'
        self.state = {"run_id": run_id, "vm": self.vm, "firewall": self.firewall, "zone": self.zone,
                      "alloydb_start_requested": False, "vm_create_requested": False, "firewall_create_requested": False}
        self.password = None
        self.address = None

    def save(self):
        self.state_path.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        self.emit("resource-state", {"state": dict(self.state)})

    def command(self, args, *, input=None, timeout=60, cleanup=False):
        if not cleanup:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Campaign runtime budget exhausted")
            timeout = max(1, min(timeout, remaining))
        try:
            r = subprocess.run([self.gcloud, *args, "--project", PROJECT, "--quiet"], input=input,
                               text=True, encoding="utf-8", capture_output=True, timeout=timeout,
                               # gcloud's legacy PuTTY auto-confirmation supplies
                               # its own stdin and otherwise discards our JSON.
                               env={**os.environ, **({"CLOUDSDK_SSH_PUTTY_FORCE_CONNECT": "false"} if input is not None else {})})
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("GCP command failed or timed out; inspect resource cleanup status") from exc
        if r.returncode:
            # Raw stderr may include connection details; persist neither stream.
            raise RuntimeError("GCP operation failed: " + " ".join(args[:3]))
        return r.stdout

    def instance(self, *, cleanup=False):
        return json.loads(self.command(["alloydb", "instances", "describe", INSTANCE, "--cluster", CLUSTER,
                                       "--region", REGION, "--format=json"], cleanup=cleanup))

    def ssh(self, command, *, input=None, timeout=60, cleanup=False):
        return self.command(["compute", "ssh", self.vm, "--zone", self.zone, "--tunnel-through-iap",
                             "--command", command, "--ssh-flag=-T"], input=input, timeout=timeout, cleanup=cleanup)

    def wait(self, predicate, description, *, timeout=300):
        until = min(self.deadline, time.monotonic() + timeout)
        while time.monotonic() < until:
            try:
                if predicate():
                    return
            except RuntimeError:
                pass
            time.sleep(3)
        raise TimeoutError(description + " timed out")

    def prepare(self):
        before = self.instance()
        expected_name = f"projects/{PROJECT}/locations/{REGION}/clusters/{CLUSTER}/instances/{INSTANCE}"
        if before["name"] != expected_name or before["state"] != "STOPPED" or before.get("activationPolicy") != "NEVER":
            raise ValueError("Pilot requires the exact stopped AlloyDB primary; shared running resources are not taken over")
        self.address = before["ipAddress"]
        self.state.update(alloydb_before="STOPPED", alloydb_name=expected_name)
        self.save()
        # Refuse to adopt any existing VM/firewall with our proposed names.
        for kind, name in (("instances", self.vm), ("firewall-rules", self.firewall)):
            rows = json.loads(self.command(["compute", kind, "list", "--filter=name=" + name, "--format=json"]))
            if rows:
                raise ValueError("Campaign resource name already exists")
        self.emit("stage", {"stage": "environment-start", "message": "Resuming the bound AlloyDB primary and preparing an owned runner."})
        self.state["alloydb_start_requested"] = True
        self.save()
        self.command(["alloydb", "instances", "update", INSTANCE, "--cluster", CLUSTER, "--region", REGION,
                      "--activation-policy=ALWAYS"], timeout=600)
        self.state["firewall_create_requested"] = True
        self.save()
        self.command(["compute", "firewall-rules", "create", self.firewall, "--network=cloudbank-ms67",
                      "--allow=tcp:22", "--source-ranges=" + IAP_RANGE, "--target-tags=" + self.vm,
                      "--description=" + self.run_id])
        self.state["vm_create_requested"] = True
        self.save()
        self.command(["compute", "instances", "create", self.vm, "--zone", self.zone,
                      "--machine-type=e2-standard-2", "--subnet=cloudbank-ms67", "--tags=" + self.vm,
                      "--image-family=debian-12", "--image-project=debian-cloud", "--boot-disk-size=20GB",
                      "--no-service-account", "--no-scopes", "--labels=lightyear-campaign=" + self.run_id,
                      "--max-run-duration=" + str(self.plan["profile"]["max_seconds"]) + "s", "--instance-termination-action=DELETE"], timeout=240)
        self.wait(lambda: self.ssh("true").strip() == "", "Runner SSH", timeout=180)
        if self.ssh("python3 -c \"import sys;print(sys.stdin.read())\"", input="lightyear-stdin-check").strip() != "lightyear-stdin-check":
            raise ValueError("SSH did not preserve request input")
        self.emit("stage", {"stage": "oracle-install", "message": "Installing SQL clients and the authorized Oracle image on the owned runner."})
        self.ssh("sudo apt-get update -qq && sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io postgresql-client", timeout=300)
        image = self.plan["profile"]["oracle_image"]
        self.ssh("sudo docker pull " + image, timeout=300)
        # OS-authenticated SQL on a container with no published ports. The random
        # boot password is generated remotely and never reaches the controller.
        boot = "import secrets,subprocess,os; e=dict(os.environ,ORACLE_PWD=secrets.token_urlsafe(32)); subprocess.run(['sudo','--preserve-env=ORACLE_PWD','docker','run','-d','--name','ly-number-oracle','--memory=3g','--cpus=2','-e','ORACLE_PWD','" + image + "'],env=e,check=True)"
        self.ssh("python3 -c \"" + boot + "\"", timeout=60)
        self.emit("stage", {"stage": "oracle-startup", "message": "Waiting for the Oracle container health check; no cases have executed."})
        self.wait(lambda: "healthy" == self.ssh("sudo docker inspect --format='{{.State.Health.Status}}' ly-number-oracle").strip(), "Oracle startup", timeout=600)
        actual = self.ssh("sudo docker inspect --format='{{.Config.Image}}' ly-number-oracle").strip()
        if actual != image:
            raise ValueError("Oracle runtime image differs from authorized digest")
        self.wait(lambda: self.instance()["state"] == "READY", "AlloyDB startup", timeout=300)
        self.emit("stage", {"stage": "identity", "message": "Verifying fresh source and target database identities."})
        # The credential resource name is fixed and already belongs to this lab.
        secret = json.loads(self.command(["secrets", "versions", "access", "latest", "--secret=cloudbank-ms71-alloydb-admin"]))
        if secret.get("resource") != f"projects/{PROJECT}/locations/{REGION}/clusters/{CLUSTER}" or secret.get("username") != "postgres":
            raise ValueError("AlloyDB credential resource binding invalid")
        self.password = secret.get("password") or secret.get("PASSWORD")
        if not isinstance(self.password, str) or not self.password:
            raise ValueError("AlloyDB admin credential has an unsupported format")

    def sql(self, lane, sql):
        payload = {"lane": lane, "sql": sql}
        if lane == "alloydb":
            payload.update(host=self.address, password=self.password)
        encoded = base64.b64encode(REMOTE.encode()).decode()
        command = "python3 -c \"import base64;exec(base64.b64decode('" + encoded + "'))\""
        result = json.loads(self.ssh(command, input=json.dumps(payload), timeout=45))
        if result["returncode"]:
            codes = sorted(set(re.findall(r"\b(?:ORA|SP2|TNS)-[0-9]{4,5}\b", result['stdout'] + result['stderr'])))
            raise ValueError(lane + " SQL client failed (exit " + str(result['returncode']) + "; " + (", ".join(codes) or "no public error code") + "); raw diagnostics are not published")
        return result["stdout"] + "\n" + result["stderr"]

    def identities(self):
        current = self.instance()
        if current.get("name") != self.state["alloydb_name"] or current.get("state") != "READY":
            raise ValueError("The bound AlloyDB resource is not ready for identity verification")
        # The GCP API supplies the connection endpoint. Managed routing can
        # expose a different socket address through inet_server_addr().
        self.address = current["ipAddress"]
        prefix = "SET ECHO OFF FEEDBACK OFF HEADING OFF PAGESIZE 0 VERIFY OFF\nSET LONG 100000 LONGCHUNKSIZE 100000 LINESIZE 32767\nWHENEVER SQLERROR EXIT SQL.SQLCODE\nALTER SESSION SET CONTAINER=FREEPDB1;\n"
        raw = self.sql("oracle", prefix + IDENTITY_SQL + "\nEXIT\n")
        rows = [line.split("LY_NUMBER_IDENTITY=", 1)[1] for line in raw.splitlines() if "LY_NUMBER_IDENTITY=" in line]
        if len(rows) != 1:
            raise ValueError("Oracle identity is incomplete")
        source = json.loads(rows[0])
        if not re.search(r"26\s*ai", source["banner"], re.I) or not source["version_full"].startswith("23.26.") or source["container_name"] != "FREEPDB1":
            raise ValueError("Oracle runtime is not the authorized 26ai Free PDB")
        target_sql = "SELECT json_build_object('version',version(),'server_address',inet_server_addr()::text,'database',current_database(),'user',current_user,'server_version',current_setting('server_version'),'timezone',current_setting('TimeZone'));"
        target = json.loads(self.sql("alloydb", target_sql).strip())
        if not target["server_version"].startswith("16."):
            raise ValueError("Target SQL version is not PostgreSQL 16: " + target["server_version"][:32])
        if target["database"] != "postgres" or target["user"] != "postgres":
            raise ValueError("Target SQL database or user differs from the authorized connection")
        return {"oracle": {"version": source["version_full"], "banner": source["banner"], "container": source["container_name"],
                            "image": self.plan["profile"]["oracle_image"], "dbid_sha256": hashlib.sha256(source["dbid"].encode()).hexdigest(),
                            "session": source["session"], "evidence_class": self.evidence_class},
                "alloydb": {"version": target["server_version"], "resource": self.state["alloydb_name"],
                            "database": target["database"], "endpoint_verified": True,
                            "endpoint_binding": "PGHOST from fresh fixed-resource GCP API readback",
                            "version_banner": target["version"],
                            "server_address_matches_endpoint": target["server_address"] == self.address,
                            "server_address_sha256": hashlib.sha256(target["server_address"].encode()).hexdigest() if target["server_address"] else None,
                            "evidence_class": self.evidence_class}}

    def observe(self, lane, case):
        from . import paired_types, paired_types260
        suite = paired_types260 if self.plan['campaign_id'] == paired_types260.CAMPAIGN else paired_types
        core = self.plan['campaign_id'] in (paired_types.CAMPAIGN, paired_types260.CAMPAIGN)
        body = suite.render(case, lane) if core else postgres_case(case) if lane == 'alloydb' else render_case(case, '26ai')
        sql = body if lane == "alloydb" else (
            # DBMS_OUTPUT package state belongs to the selected container.
            # Enable it after switching from the root to FREEPDB1.
            "SET ECHO OFF FEEDBACK OFF HEADING OFF PAGESIZE 0 VERIFY OFF DEFINE OFF\nSET LINESIZE 32767\nWHENEVER SQLERROR EXIT SQL.SQLCODE\nALTER SESSION SET CONTAINER=FREEPDB1;\nSET SERVEROUTPUT ON SIZE UNLIMITED\n" + body + "\nEXIT\n")
        return (suite.parse if core else parse_observation)(self.sql(lane, sql), case, lane)

    def cleanup(self):
        results = {}
        # Attempt every cleanup independently, even when an earlier one fails.
        for name, requested in (("vm", "vm_create_requested"), ("firewall", "firewall_create_requested"), ("alloydb", "alloydb_start_requested")):
            if not self.state[requested]:
                results[name] = "not-created"
                continue
            try:
                if name == "vm":
                    rows = json.loads(self.command(["compute", "instances", "list", "--filter=name=" + self.vm, "--format=json"], cleanup=True))
                    if rows:
                        if len(rows) != 1 or rows[0].get("labels", {}).get("lightyear-campaign") != self.run_id:
                            raise ValueError("Runner ownership mismatch")
                        self.command(["compute", "instances", "delete", self.vm, "--zone", self.zone], cleanup=True, timeout=180)
                    results[name] = "deleted"
                elif name == "firewall":
                    rows = json.loads(self.command(["compute", "firewall-rules", "list", "--filter=name=" + self.firewall, "--format=json"], cleanup=True))
                    if rows:
                        if len(rows) != 1 or rows[0].get("description") != self.run_id:
                            raise ValueError("Firewall ownership mismatch")
                        self.command(["compute", "firewall-rules", "delete", self.firewall], cleanup=True)
                    results[name] = "deleted"
                else:
                    state = self.instance(cleanup=True)
                    if state["state"] != "STOPPED" and state["state"] != "STOPPING":
                        self.command(["alloydb", "instances", "update", INSTANCE, "--cluster", CLUSTER, "--region", REGION,
                                      "--activation-policy=NEVER"], cleanup=True, timeout=600)
                    until = time.monotonic() + 300
                    while time.monotonic() < until:
                        state = self.instance(cleanup=True)
                        if state["state"] == "STOPPED" and state.get("activationPolicy") == "NEVER":
                            break
                        time.sleep(3)
                    results[name] = "stopped" if state["state"] == "STOPPED" and state.get("activationPolicy") == "NEVER" else "unconfirmed"
            except (ValueError, RuntimeError, KeyError, TypeError, OSError):
                results[name] = "unconfirmed"
        self.password = None
        self.state["cleanup"] = results
        self.save()
        return {"complete": "unconfirmed" not in results.values(), "resources": results}
