"""CI-only security scanners; raw diagnostics never leave temporary storage."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
import tomllib
from urllib.request import urlopen
from tools.ci.p1_capture import capture, CaptureRefused
from tools.ci.p1_reports import dependency_report, digest, execution_gate, normalize, public_summary, ReportRefused


GITLEAKS_URL = "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz"
GITLEAKS_SHA = "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"


def tracked(root):
    code, out, _ = capture(["git", "ls-files", "-z"], root)
    if code:
        raise CaptureRefused("inventory")
    return set(filter(None, out.decode("utf-8").split("\0")))


def write_summary(output, tool, rows, inventory):
    result = dict(schema="p1-security-measurement/1", tool=tool,
                  run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
                  checkout=os.environ.get("GITHUB_SHA"), inventory_sha256=digest(inventory),
                  inventory_count=len(inventory), results=rows)
    output.mkdir(parents=True, exist_ok=True)
    with (output / (tool + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    return all(r["completed"] and r.get("clean") for r in rows)


def diagnostic(error, stage="prepare", code=None, stdout=b"", stderr=b""):
    known = {"inventory", "report-size", "dependency-empty-resolution", "dependency-incomplete",
             "dependency-schema", "dependency-tool", "dependency-scan-incomplete", "dependency-severity",
             "scanner-execution-error", "scanner-incomplete", "scanner-path", "scanner-unbound-path",
             "scanner-schema", "scanner-severity", "scanner-unsupported", "dynamic-dependencies",
             "dependency-inventory-empty", "dependency-group-schema", "pip-negative-control",
             "maven-inventory-empty", "maven-negative-control", "base-identity", "tool-distribution",
             "tool-member", "gitleaks-negative-control", "history-inventory", "ci-only",
             "capture-output-limit", "capture-failed"}
    if isinstance(error, DependencyIncomplete):
        return error.diagnostic
    result = dict(stage=stage, exit_code=code,
                  error_type=type(error).__name__ if type(error) in
                  (ReportRefused, CaptureRefused, ValueError, KeyError, TypeError, OSError,
                   UnicodeDecodeError, json.JSONDecodeError) else "other",
                  refusal_code=str(error) if type(error) in (ReportRefused, CaptureRefused)
                  and str(error) in known else "unclassified")
    result.update(stdout_bytes=len(stdout), stdout_sha256=sha256(stdout).hexdigest(),
                  stderr_bytes=len(stderr), stderr_sha256=sha256(stderr).hexdigest())
    return result


class DependencyIncomplete(ReportRefused):
    def __init__(self, details):
        super().__init__(details["refusal_code"])
        self.diagnostic = details


def failure(path, error):
    return dict(path=path, completed=False, clean=False, error="scanner-incomplete", diagnostic=diagnostic(error))


def run_dependency(command, cwd, tool, manifest, root, allowed, report_path=None):
    stage, code, stdout, stderr = "capture", None, b"", b""
    try:
        code, stdout, stderr = capture(command, cwd, timeout=3600)
        stage = "parse"
        raw = report_path.read_bytes() if report_path is not None and report_path.is_file() else stdout
        if len(raw) > 64 * 1024 * 1024:
            raise ReportRefused("report-size")
        payload = json.loads(raw)
        if tool == "pip-audit" and not payload.get("dependencies"):
            raise ReportRefused("dependency-empty-resolution")
        if tool == "dependency-check" and payload.get("scanInfo", {}).get("analysisExceptions"):
            raise ReportRefused("dependency-incomplete")
        report = dependency_report(tool, payload, manifest, root, allowed)
        stage = "execution-gate"
        state = execution_gate(tool, code, report, True)
        # Opaque identifiers bind private triage without publishing package names,
        # versions, advisory IDs, descriptions or raw scanner streams.
        return dict(path=manifest, **state, summary=public_summary(report),
                    finding_fingerprints=sorted(row["fingerprint"] for row in report["findings"]))
    except Exception as error:
        raise DependencyIncomplete(diagnostic(error, stage, code, stdout, stderr)) from None



def python_groups(root, paths):
    groups = []
    for path in sorted(paths):
        if Path(path).name == "pyproject.toml":
            data = tomllib.loads((root / path).read_text(encoding="utf-8"))
            project = data.get("project", {})
            if "dependencies" in project.get("dynamic", []):
                raise ReportRefused("dynamic-dependencies")
            groups.append((path, "default", project.get("dependencies", [])))
            groups.extend((path, name, values) for name, values in project.get("optional-dependencies", {}).items())
            # Unresolved group includes must never be silently omitted.
            groups.extend((path, name, values) for name, values in data.get("dependency-groups", {}).items())
        elif re.fullmatch(r"requirements[^/]*\.txt", Path(path).name):
            groups.append((path, "requirements-file", None))
    if not groups:
        raise ReportRefused("dependency-inventory-empty")
    if any(values is not None and (not isinstance(values, list) or not all(isinstance(v, str) and "\n" not in v and not v.startswith("-") for v in values)) for _, _, values in groups):
        raise ReportRefused("dependency-group-schema")
    return groups


def pip_audit(root, output):
    paths = tracked(root)
    groups = python_groups(root, paths)
    rows = []
    with tempfile.TemporaryDirectory(prefix="p1-pip-") as temp:
        scratch = Path(temp)
        probe = scratch / "negative.txt"
        probe.write_text("urllib3==1.26.4\n", encoding="utf-8")
        command = [sys.executable, "-m", "pip_audit", "--format=json", "--progress-spinner=off", "--desc=off"]
        code, raw, _ = capture(command + ["--no-deps", "--disable-pip", "-r", str(probe)], root)
        report = dependency_report("pip-audit", json.loads(raw), "pyproject.toml", root, paths)
        if code != 1 or not report["findings"]:
            raise ReportRefused("pip-negative-control")
        for index, (path, group, values) in enumerate(groups):
            if values == []:
                rows.append(dict(path=path, group=group, completed=True, clean=True, declared_empty=True, findings=0))
                continue
            try:
                source = root / path
                if values is not None:
                    source = scratch / (str(index) + ".txt")
                    source.write_text("\n".join(values) + "\n", encoding="utf-8")
                row = run_dependency(command + ["-r", str(source)], root, "pip-audit", path, root, paths)
                row["group"] = group
                rows.append(row)
            except Exception as error:
                rows.append(dict(group=group, **failure(path, error)))
    return write_summary(output, "pip-audit", rows, [(p, g) for p, g, _ in groups])


def maven(root, output):
    paths = tracked(root)
    manifests = sorted(p for p in paths if p.endswith("pom.xml"))
    if not manifests:
        raise ReportRefused("maven-inventory-empty")
    rows = []
    with tempfile.TemporaryDirectory(prefix="p1-maven-") as temp:
        scratch = Path(temp)
        command = ["mvn", "-B", "-ntp", "org.owasp:dependency-check-maven:13.0.0:check", "-Dformat=JSON", "-DfailBuildOnCVSS=0", "-DfailOnError=true", "-DskipTestScope=false", "-DskipProvidedScope=false", "-DskipRuntimeScope=false", "-DskipSystemScope=false", "-DdataDirectory=" + str(scratch / "data")]
        probe = scratch / "probe.pom.xml"
        probe.write_text('<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>synthetic</groupId><artifactId>p1-probe</artifactId><version>1</version><dependencies><dependency><groupId>commons-collections</groupId><artifactId>commons-collections</artifactId><version>3.2.1</version></dependency></dependencies></project>', encoding="utf-8")
        dest = scratch / "probe-report"
        result = run_dependency(command + ["-f", str(probe), "-DoutputDirectory=" + str(dest)], root,
                                "dependency-check", manifests[0], root, paths, dest / "dependency-check-report.json")
        if not result["completed"] or result["findings"] == 0:
            raise ReportRefused("maven-negative-control")
        for index, path in enumerate(manifests):
            try:
                dest = scratch / str(index)
                rows.append(run_dependency(command + ["-f", str(root / path), "-DoutputDirectory=" + str(dest)], root,
                                           "dependency-check", path, root, paths, dest / "dependency-check-report.json"))
            except Exception as error:
                rows.append(failure(path, error))
    return write_summary(output, "dependency-check", rows, manifests)


def gitleaks(root, output, base, history):
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ReportRefused("base-identity")
    paths = tracked(root)
    rows = []
    with tempfile.TemporaryDirectory(prefix="p1-gitleaks-") as temp:
        scratch = Path(temp)
        archive = scratch / "tool.tar.gz"
        with urlopen(GITLEAKS_URL, timeout=60) as response:
            raw = response.read(8230403)
        if len(raw) != 8230402 or sha256(raw).hexdigest() != GITLEAKS_SHA:
            raise ReportRefused("tool-distribution")
        archive.write_bytes(raw)
        binary = scratch / "gitleaks"
        with tarfile.open(archive) as tar:
            member = tar.getmember("gitleaks")
            if not member.isfile() or member.size > 32 * 1024 * 1024:
                raise ReportRefused("tool-member")
            binary.write_bytes(tar.extractfile(member).read())
        binary.chmod(0o700)
        # Explicit default rules and empty ignore file prevent candidate
        # .gitleaks.toml/.gitleaksignore or inline comments hiding a finding.
        config = scratch / "rules.toml"
        config.write_text("[extend]\nuseDefault = true\n", encoding="utf-8")
        ignore = scratch / "ignore"
        ignore.write_text("", encoding="utf-8")
        common = [str(binary), "--config", str(config), "--gitleaks-ignore-path", str(ignore), "--ignore-gitleaks-allow", "--no-banner", "--no-color", "--redact=100", "--report-format=json", "--exit-code=1"]
        probe = scratch / "probe"
        probe.mkdir()
        # Synthetic, deterministic, never a credential. Constructed so the
        # repository's own text does not contain the complete planted pattern.
        (probe / "fake.txt").write_text("token = '" + "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyz" + "'\n", encoding="utf-8")
        destination = scratch / "negative.json"
        code, _, _ = capture(common + ["dir", str(probe), "--report-path", str(destination)], scratch)
        if code != 1 or not json.loads(destination.read_bytes()):
            raise ReportRefused("gitleaks-negative-control")
        ranges = [("pr-diff", base + "..HEAD")]
        if history:
            ranges.append(("full-history", "--all"))
        for label, revision in ranges:
            try:
                destination = scratch / (label + ".json")
                code, _, _ = capture(common + ["git", str(root), "--log-opts=" + revision, "--report-path", str(destination)], root, timeout=3600)
                # Include historical deleted paths in the public path allowlist.
                status, names, _ = capture(["git", "log", "--all", "--format=", "--name-only", "-z"], root)
                if status:
                    raise ReportRefused("history-inventory")
                allowed = paths | {p.lstrip("\n") for p in names.decode("utf-8").split("\0") if p.strip("\n")}
                report = normalize("gitleaks", json.loads(destination.read_bytes()), root, allowed)
                rows.append(dict(scope=label, **execution_gate("gitleaks", code, report, True), summary=public_summary(report)))
            except Exception as error:
                rows.append(dict(scope=label, **failure("repository", error)))
    return write_summary(output, "gitleaks", rows, sorted(paths))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", choices=("pip-audit", "dependency-check", "gitleaks"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise CaptureRefused("ci-only")
        root = Path.cwd()
        ok = (gitleaks(root, args.output, args.base, args.history) if args.tool == "gitleaks" else
              pip_audit(root, args.output) if args.tool == "pip-audit" else maven(root, args.output))
        print("P1 security scan complete and clean" if ok else "P1 security findings or incomplete scan; review required")
        return 0 if ok else 1
    except Exception as error:
        result = dict(schema="p1-security-incomplete/1", tool=args.tool,
                      run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
                      checkout=os.environ.get("GITHUB_SHA"), completed=False, clean=False,
                      diagnostic=diagnostic(error))
        args.output.mkdir(parents=True, exist_ok=True)
        with (args.output / (args.tool + "-incomplete.json")).open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps(result), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
