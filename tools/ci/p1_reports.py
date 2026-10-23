"""Reduce CI scanner results without publishing source, messages or secrets.

This module does not invoke scanners. Unknown output schemas and paths fail
closed; an unavailable scan must never become an empty successful result.
"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import PurePosixPath
from urllib.parse import unquote


class ReportRefused(ValueError):
    """A fixed error code, never the rejected scanner payload."""


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def relative_path(value, root, allowed):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ReportRefused("scanner-path")
    value = value.replace("\\", "/")
    root = str(root).replace("\\", "/").rstrip("/")
    if value.startswith(root + "/"):
        value = value[len(root) + 1:]
    if value.startswith("./"):
        value = value[2:]
    path = PurePosixPath(value)
    if path.is_absolute() or ":" in value or any(p in ("", ".", "..") for p in value.split("/")):
        raise ReportRefused("scanner-path")
    if value not in allowed:
        raise ReportRefused("scanner-unbound-path")
    return value


def normalize(tool, payload, root, allowed):
    """Return only bound paths, severity and opaque finding fingerprints.

    Raw scanner payloads belong in temporary runner storage, never artifacts.
    Fingerprints are for quality-baseline comparison, not a secret inventory.
    """
    found = []

    def add(path, severity, identity):
        path = relative_path(path, root, allowed)
        severity = str(severity).lower()
        if severity not in {"critical", "high", "medium", "low", "warning", "error", "note", "unknown"}:
            raise ReportRefused("scanner-severity")
        found.append(dict(path=path, severity=severity,
                          fingerprint=digest([tool, path, identity])))

    try:
        if tool == "ruff":
            if not isinstance(payload, list):
                raise ReportRefused("scanner-schema")
            for row in payload:
                add(row["filename"], "warning", [row["code"], row["location"], row["message"]])
        elif tool == "mypy":
            if not isinstance(payload, list):
                raise ReportRefused("scanner-schema")
            for row in payload:
                add(row["file"], row["severity"], [row["code"], row["line"], row["column"], row["message"]])
        elif tool == "gitleaks":
            if not isinstance(payload, list):
                raise ReportRefused("scanner-schema")
            for row in payload:
                # Deliberately never read or retain Match, Secret, Message,
                # Author, Email or the original source line.
                add(row["File"], "unknown", [row["RuleID"], row["StartLine"], row.get("Commit", "")])
        elif tool == "codeql":
            if payload["version"] != "2.1.0" or not isinstance(payload["runs"], list) or not payload["runs"]:
                raise ReportRefused("scanner-schema")
            for run in payload["runs"]:
                rules = {r["id"]: r for r in run["tool"]["driver"]["rules"]}
                for row in run.get("results", []):
                    rule = rules[row["ruleId"]]
                    score = rule.get("properties", {}).get("security-severity")
                    severity = row.get("level", "warning")
                    if score is not None:
                        score = float(score)
                        if not 0 <= score <= 10:
                            raise ReportRefused("scanner-severity")
                        severity = "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low"
                    locations = row["locations"]
                    if not locations:
                        raise ReportRefused("scanner-location")
                    for location in locations:
                        physical = location["physicalLocation"]
                        add(unquote(physical["artifactLocation"]["uri"]), severity,
                            [row["ruleId"], physical.get("region", {})])
        else:
            raise ReportRefused("scanner-unsupported")
    except ReportRefused:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ReportRefused("scanner-schema") from None
    return dict(schema="p1-normalized-findings/1", tool=tool,
                findings=sorted(found, key=lambda r: (r["path"], r["fingerprint"])))


def public_summary(report):
    """Allowlisted public output: counts and file paths, never finding text."""
    counts = Counter(r["severity"] for r in report["findings"])
    files = Counter(r["path"] for r in report["findings"])
    return dict(schema="p1-public-summary/1", tool=report["tool"],
                total=sum(counts.values()), severity_counts=dict(sorted(counts.items())),
                files=[dict(path=p, count=n) for p, n in sorted(files.items())])


def baseline_gate(base, proposed, observed):
    """Existing Python-quality allowances may shrink but never expand.

    Security findings do not get a baseline exemption. The caller must supply
    the baseline from the trusted base commit, not only the candidate checkout.
    """
    if any(r["tool"] not in {"ruff", "ruff-format", "mypy"} for r in (base, proposed, observed)):
        raise ReportRefused("security-baseline-forbidden")
    if len({r["tool"] for r in (base, proposed, observed)}) != 1:
        raise ReportRefused("baseline-tool-mismatch")
    def items(report):
        if report.get("schema") != "p1-normalized-findings/1":
            raise ReportRefused("baseline-schema")
        rows = [(r["path"], r["severity"], r["fingerprint"]) for r in report["findings"]]
        if len(rows) != len(set(rows)):
            raise ReportRefused("baseline-duplicates")
        return set(rows)
    trusted, candidate, current = map(items, (base, proposed, observed))
    if not candidate <= trusted:
        raise ReportRefused("baseline-expanded")
    if not current <= candidate:
        raise ReportRefused("new-quality-findings")
    return dict(passed=True, trusted=len(trusted), proposed=len(candidate), observed=len(current))


def dependency_report(tool, payload, manifest, root, allowed):
    """Map dependency findings to the tracked manifest, without descriptions.

    A skipped or unavailable package is an incomplete scan, not a clean one.
    Unknown severity is retained explicitly when the service supplies no CVSS.
    """
    manifest = relative_path(manifest, root, allowed)
    found = []
    try:
        dependencies = payload["dependencies"]
        if not isinstance(dependencies, list):
            raise ReportRefused("dependency-schema")
        for dep in dependencies:
            if tool == "pip-audit":
                if dep.get("skip_reason"):
                    raise ReportRefused("dependency-scan-incomplete")
                name, version = dep["name"], dep["version"]
                vulns = dep["vulns"]
            elif tool == "dependency-check":
                name, version = dep["fileName"], dep.get("sha256", "")
                vulns = dep.get("vulnerabilities", [])
            else:
                raise ReportRefused("dependency-tool")
            if not isinstance(vulns, list):
                raise ReportRefused("dependency-schema")
            for vuln in vulns:
                identity = vuln["id"] if tool == "pip-audit" else vuln["name"]
                severity = str(vuln.get("severity", "unknown")).lower()
                if severity not in {"critical", "high", "medium", "low", "unknown"}:
                    raise ReportRefused("dependency-severity")
                found.append(dict(path=manifest, severity=severity,
                                  fingerprint=digest([tool, name, version, identity])))
    except ReportRefused:
        raise
    except (KeyError, TypeError, ValueError):
        raise ReportRefused("dependency-schema") from None
    return dict(schema="p1-normalized-findings/1", tool=tool,
                findings=sorted(found, key=lambda r: (r["path"], r["fingerprint"])))


def execution_gate(tool, returncode, report, execution_complete):
    """A report alone does not establish that a scanner completed successfully."""
    if not execution_complete or report.get("tool") != tool:
        raise ReportRefused("scanner-incomplete")
    count = len(report["findings"])
    if tool == "codeql":
        if returncode != 0:
            raise ReportRefused("scanner-execution-error")
    elif tool in {"ruff", "ruff-format", "mypy", "gitleaks", "pip-audit", "dependency-check"}:
        # Commands are configured with exit 1 for findings. Other errors or
        # exit 1 without findings must not look like successful empty reports.
        if returncode not in (0, 1) or (returncode == 1) != bool(count):
            raise ReportRefused("scanner-execution-error")
    else:
        raise ReportRefused("scanner-unsupported")
    return dict(completed=True, findings=count, clean=count == 0)
