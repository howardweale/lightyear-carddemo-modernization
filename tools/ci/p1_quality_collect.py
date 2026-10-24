"""CI-only measurement; never auto-approve or enlarge a quality baseline."""
import argparse
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import sys
from tools.ci.p1_capture import CaptureRefused, capture
from tools.ci.p1_reports import ReportRefused, digest, execution_gate, normalize, public_summary


def decode_json_lines(raw):
    try:
        return [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeError, ValueError):
        raise ReportRefused("mypy-output-schema") from None


def format_report(raw, root, paths):
    from tools.ci.p1_reports import relative_path
    found = []
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        raise ReportRefused("format-output-schema") from None
    summaries = []
    for line in lines:
        if line.startswith("Would reformat: "):
            path = relative_path(line[len("Would reformat: "):], root, paths)
            found.append(dict(path=path, severity="warning", fingerprint=digest(["ruff-format", path])))
        else:
            summary = re.fullmatch(r"(?:(\d+) files? would be reformatted(?:, )?)?(?:(\d+) files? already formatted)?", line)
            if not summary or not line:
                raise ReportRefused("format-output-schema")
            summaries.append(tuple(int(v or 0) for v in summary.groups()))
    if len(found) != len({r["path"] for r in found}):
        raise ReportRefused("format-duplicates")
    if len(summaries) != 1 or summaries[0][0] != len(found) or sum(summaries[0]) != len(paths):
        raise ReportRefused("format-incomplete-inventory")
    return dict(schema="p1-normalized-findings/1", tool="ruff-format", findings=sorted(found, key=lambda r: r["path"]))


def format_json_report(raw, root, paths):
    """Pinned Ruff JSON: one unformatted diagnostic per explicitly named file."""
    from tools.ci.p1_reports import relative_path
    try:
        rows = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ReportRefused("format-output-schema") from None
    if not paths or not isinstance(rows, list):
        raise ReportRefused("format-output-schema")
    found = []
    for row in rows:
        if not isinstance(row, dict) or row.get("code") != "unformatted":
            raise ReportRefused("format-output-schema")
        path = relative_path(row.get("filename"), root, paths)
        found.append(dict(path=path, severity="warning", fingerprint=digest(["ruff-format", path])))
    if len(found) != len({r["path"] for r in found}):
        raise ReportRefused("format-duplicates")
    return dict(schema="p1-normalized-findings/1", tool="ruff-format", findings=sorted(found, key=lambda r: r["path"]))


def collect(root, output):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise CaptureRefused("ci-only")
    if output.exists():
        raise CaptureRefused("output-exists")
    tools = {name: version(name) for name in ("ruff", "mypy")}
    if tools != {"ruff": "0.17.2", "mypy": "2.4.0"}:
        raise CaptureRefused("tool-version")
    code, raw, _ = capture(["git", "ls-files", "-z"], root)
    if code:
        raise CaptureRefused("source-inventory")
    try:
        allowed = set(p for p in raw.decode("utf-8").split("\0") if p)
        paths = sorted(p for p in allowed if p.startswith("src/") and p.endswith((".py", ".pyi")))
    except UnicodeError:
        raise CaptureRefused("source-inventory") from None
    if not paths or any((root / p).is_symlink() or not (root / p).is_file() for p in paths):
        raise CaptureRefused("source-inventory")
    # Explicit files prevent an ignore/config change from silently reducing scope.
    commands = {
        "ruff": [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--output-format=json", *paths],
        "ruff-format": [sys.executable, "-m", "ruff", "format", "--isolated", "--no-cache", "--check", "--output-format=json", *paths],
        "mypy": [sys.executable, "-m", "mypy", "--config-file=", "--no-incremental", "--no-error-summary", "--output=json", "src/"],
    }
    results, baselines = [], {}
    public_codes = {"format-output-schema", "format-duplicates", "format-incomplete-inventory",
                    "scanner-path", "scanner-unbound-path", "scanner-execution-error",
                    "scanner-incomplete", "capture-output-limit", "capture-failed"}
    for tool, command in commands.items():
        diagnostic = {"stage": "capture"}
        try:
            code, stdout, stderr = capture(command, root)
            diagnostic.update(stage="parse", exit_code=code, stdout_bytes=len(stdout),
                              stderr_bytes=len(stderr), stdout_sha256=sha256(stdout).hexdigest(),
                              stderr_sha256=sha256(stderr).hexdigest())
            if tool == "ruff-format":
                report = format_json_report(stdout, root, set(paths))
                if stderr.strip():
                    raise ReportRefused("format-output-schema")
            elif tool == "mypy":
                report = normalize(tool, decode_json_lines(stdout), root, allowed)
            else:
                report = normalize(tool, json.loads(stdout), root, set(paths))
            diagnostic["stage"] = "execution-gate"
            state = execution_gate(tool, code, report, True)
            results.append(dict(tool=tool, state=state, summary=public_summary(report)))
            baselines[tool] = report
        except (CaptureRefused, ReportRefused, ValueError) as error:
            # Do not serialize exception text: JSON errors can quote source.
            diagnostic.update(error_type=type(error).__name__,
                              refusal_code=str(error) if str(error) in public_codes else "unclassified")
            results.append(dict(tool=tool, state=dict(completed=False, error="scanner-incomplete"),
                                diagnostic=diagnostic))
    commit_code, commit, _ = capture(["git", "rev-parse", "HEAD"], root)
    if commit_code or not re.fullmatch(rb"[0-9a-f]{40}\s*", commit):
        raise CaptureRefused("checkout-identity")
    report = dict(schema="p1-quality-measurement/1", commit=commit.decode().strip(),
                  run_id=os.environ.get("GITHUB_RUN_ID"), run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
                  tools=tools, scope="tracked Python source under src/", file_count=len(paths),
                  source_sha256=digest({p: sha256((root / p).read_bytes()).hexdigest() for p in paths}),
                  results=results, baseline_approved=False)
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Only quality paths/severity/opaque fingerprints; no raw scanner messages.
    (output / "baseline-proposal.json").write_text(json.dumps(baselines, indent=2) + "\n", encoding="utf-8")
    return all(r["state"]["completed"] for r in results)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        complete = collect(Path.cwd(), args.output)
        print("P1 quality measurement complete; baseline approval remains required" if complete else "P1 quality measurement incomplete")
        return 0 if complete else 1
    except Exception:
        print("P1 quality measurement refused; no baseline accepted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
