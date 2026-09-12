"""Explicit managed PostgreSQL identities for MS71; no business-comparator changes."""
from __future__ import annotations

import ipaddress
import base64
import json
import re
from urllib.parse import parse_qsl, urlsplit

from .cloudbank_journeys import require, hashed
from .cloudbank_journeys_gke import GkeRuntime
from .cloudbank_whole_application_equivalence import SERVICES
from .contracts import content_hash, seal

PROVIDERS = ("cloud-sql-postgresql", "alloydb-postgresql")
PROFILE_TYPE = "lightyear-cloudbank-managed-target"
LABEL = re.compile(r"[a-z][a-z0-9-]{0,61}[a-z0-9]$|[a-z]$")
DATABASE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}$")


class ManagedGkeRuntime(GkeRuntime):
    """Resolve credentials from this namespace's deployed External Secret targets."""

    def secret_json(self, name: str) -> dict:
        require(re.fullmatch(r"[a-z0-9-]{1,100}", name) is not None, "secret-reference-invalid")
        return deployed_secret_values(self.get("secret", name))


def deployed_secret_values(obj: dict) -> dict:
    try:
        return {k: base64.b64decode(v, validate=True).decode("utf-8") for k, v in obj["data"].items()}
    except (KeyError, ValueError, UnicodeError, TypeError):
        raise ValueError("ms71-deployed-secret-invalid") from None


def validate_profile(profile: dict) -> None:
    require(isinstance(profile, dict), "ms71-target-profile-object-required")
    require(set(profile) == {
        "schema_version", "profile_type", "provider", "project", "region", "cluster",
        "namespace", "resource", "database_version", "databases", "require_tls",
        "synthetic_data_only", "production_environment", "content_sha256",
    }, "ms71-target-profile-fields-invalid")
    require(profile["schema_version"] == "1.0" and profile["profile_type"] == PROFILE_TYPE
            and profile["provider"] in PROVIDERS, "ms71-target-profile-identity-invalid")
    require(profile["content_sha256"] == content_hash(profile), "ms71-target-profile-hash-invalid")
    require(all(isinstance(profile[k], str) and LABEL.fullmatch(profile[k])
                for k in ("project", "region", "cluster", "namespace")), "ms71-target-location-invalid")
    project, region = profile["project"], profile["region"]
    resource = profile["resource"]
    pattern = (rf"projects/{project}/instances/[a-z][a-z0-9-]{{0,62}}"
               if profile["provider"] == PROVIDERS[0] else
               rf"projects/{project}/locations/{region}/clusters/[a-z][a-z0-9-]{{0,62}}/instances/[a-z][a-z0-9-]{{0,62}}")
    require(isinstance(resource, str) and re.fullmatch(pattern, resource) is not None,
            "ms71-target-resource-invalid")
    require(isinstance(profile["database_version"], str)
            and re.fullmatch(r"POSTGRES_[0-9]{2}", profile["database_version"]) is not None,
            "ms71-target-version-invalid")
    databases = profile["databases"]
    require(isinstance(databases, dict) and set(databases) == set(SERVICES)
            and all(v is None or (isinstance(v, str) and DATABASE.fullmatch(v)) for v in databases.values())
            and isinstance(databases["checks"], str), "ms71-target-databases-invalid")
    require(type(profile["require_tls"]) is bool and
            (profile["provider"] != PROVIDERS[1] or profile["require_tls"]), "ms71-alloydb-tls-required")
    require(profile["synthetic_data_only"] is True and profile["production_environment"] is False,
            "ms71-nonproduction-required")


def datasource(jdbc: str) -> dict:
    """Only direct PostgreSQL URLs; no credentials or arbitrary JDBC parameters."""
    require(isinstance(jdbc, str) and jdbc.startswith("jdbc:postgresql://"),
            "ms71-postgresql-datasource-required")
    parsed = urlsplit(jdbc[5:])
    try:
        port = parsed.port or 5432
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        raise ValueError("ms71-private-database-address-required") from None
    require(address.version == 4 and address.is_private and not address.is_loopback
            and not address.is_unspecified and not address.is_link_local,
            "ms71-private-database-address-required")
    require(port == 5432 and not parsed.username and not parsed.password and not parsed.fragment
            and DATABASE.fullmatch(parsed.path[1:]) is not None, "ms71-datasource-shape-invalid")
    options = parse_qsl(parsed.query, keep_blank_values=True)
    require(options in ([], [("sslmode", "require")]), "ms71-datasource-options-invalid")
    return {"address": str(address), "port": port, "database": parsed.path[1:],
            "tls": options == [("sslmode", "require")]}


def resolve_database(profile: dict, command) -> dict:
    """Read actual provider identity; a generic PostgreSQL probe cannot establish provider."""
    validate_profile(profile)
    project, region, resource = profile["project"], profile["region"], profile["resource"]
    prefix = ["gcloud", "--quiet", "--project=" + project]
    if profile["provider"] == PROVIDERS[0]:
        raw = json.loads(command(prefix + ["sql", "instances", "describe", resource.split("/")[-1],
            "--format=json(name,region,state,databaseVersion,createTime,ipAddresses)"]))
        require(raw.get("name") == resource.split("/")[-1] and raw.get("region") == region
                and raw.get("state") == "RUNNABLE", "ms71-cloud-sql-identity-invalid")
        ips = [row.get("ipAddress") for row in raw.get("ipAddresses", []) if row.get("type") == "PRIVATE"]
        require(len(ips) == 1, "ms71-cloud-sql-private-address-required")
        address, version, created = ips[0], raw.get("databaseVersion"), raw.get("createTime")
    else:
        cluster_resource = resource.rsplit("/instances/", 1)[0]
        cluster_name = cluster_resource.split("/")[-1]
        cluster = json.loads(command(prefix + ["alloydb", "clusters", "describe", cluster_name, "--region=" + region,
            "--format=json(name,state,databaseVersion,createTime)"]))
        raw = json.loads(command(prefix + ["alloydb", "instances", "describe", resource.split("/")[-1],
            "--cluster=" + cluster_name, "--region=" + region,
            "--format=json(name,state,instanceType,ipAddress,createTime)"]))
        require(cluster.get("name") == cluster_resource and cluster.get("state") == "READY"
                and raw.get("name") == resource and raw.get("state") == "READY"
                and raw.get("instanceType") == "PRIMARY", "ms71-alloydb-primary-identity-invalid")
        address, version, created = raw.get("ipAddress"), cluster.get("databaseVersion"), raw.get("createTime")
    require(isinstance(created, str) and bool(created) and version == profile["database_version"],
            "ms71-managed-database-version-or-creation-invalid")
    datasource(f"jdbc:postgresql://{address}:5432/probe")
    return seal({"provider": profile["provider"], "resource": resource, "address": address,
                 "database_version": version, "created_at": created})


def _connection(runtime, container: dict) -> dict:
    """Resolve the datasource from the deployed container's actual configuration sources."""
    values: dict = {}
    references = []
    for row in container.get("envFrom", []):
        require(not row.get("prefix"), "ms71-prefixed-environment-unsupported")
        if "secretRef" in row:
            name = row["secretRef"]["name"]
            obj = runtime.get("secret", name)
            values.update(deployed_secret_values(obj))
        elif "configMapRef" in row:
            name = row["configMapRef"]["name"]
            obj = runtime.get("configmap", name)
            values.update(obj.get("data", {}))
        else:
            raise ValueError("ms71-environment-source-unsupported")
        references.append({"name": name, "uid": obj["metadata"]["uid"],
                           "version": obj["metadata"]["resourceVersion"]})
    for row in container.get("env", []):
        if "value" in row:
            values[row["name"]] = row["value"]
        elif "secretKeyRef" in row.get("valueFrom", {}):
            ref = row["valueFrom"]["secretKeyRef"]
            obj = runtime.get("secret", ref["name"])
            values[row["name"]] = deployed_secret_values(obj)[ref["key"]]
            references.append({"name": ref["name"], "uid": obj["metadata"]["uid"],
                               "version": obj["metadata"]["resourceVersion"]})
        elif row["name"].startswith("SPRING_DATASOURCE"):
            raise ValueError("ms71-datasource-environment-source-unsupported")
    require(not values.get("SPRING_APPLICATION_JSON"), "ms71-json-datasource-override-unsupported")
    args = " ".join(container.get("args", []) + container.get("command", []))
    options = args + " " + values.get("JAVA_TOOL_OPTIONS", "") + " " + values.get("JDK_JAVA_OPTIONS", "")
    require("datasource" not in options.lower(), "ms71-datasource-command-override-unsupported")
    jdbc = values.get("SPRING_DATASOURCE_URL")
    connection = datasource(jdbc) if jdbc else None
    auxiliary = {k: datasource(v) for k, v in values.items() if isinstance(v, str)
                 and v.startswith("jdbc:") and k != "SPRING_DATASOURCE_URL"}
    require(all(v == connection for v in auxiliary.values()), "ms71-auxiliary-database-mismatch")
    return {"connection": connection, "auxiliary_connections": auxiliary,
            "configuration_refs": references}


def observe_target(runtime, profile: dict, command) -> dict:
    validate_profile(profile)
    require(all(getattr(runtime, field) == profile[field]
                for field in ("project", "region", "cluster", "namespace")), "ms71-runtime-profile-mismatch")
    database = resolve_database(profile, command)
    environment = runtime.environment()
    connections = {}
    for service in SERVICES:
        deploy = runtime.deployment(service)
        container = next(c for c in deploy["spec"]["template"]["spec"]["containers"] if c["name"] == service)
        observed = _connection(runtime, container)
        expected_db = profile["databases"][service]
        connection = observed["connection"]
        if expected_db is None:
            require(connection is None, "ms71-unexpected-service-database")
        else:
            require(connection is not None and connection["address"] == database["address"]
                    and connection["database"] == expected_db
                    and (connection["tls"] or not profile["require_tls"]), "ms71-service-database-mismatch")
        connections[service] = observed
    # The existing journey probe deliberately reads this exact secret.
    probe = datasource(runtime.secret_json("cloudbank-checks-external")["SPRING_DATASOURCE_URL"])
    require(probe == connections["checks"]["connection"], "ms71-probe-database-mismatch")
    return seal({"profile_sha256": profile["content_sha256"], "database": database,
                 "environment": environment, "services": connections,
                 "probe_connection": probe, "images_sha256": hashed(runtime.images)})
