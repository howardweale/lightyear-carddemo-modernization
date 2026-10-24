"""Synthetic CodeQL controls and safe reduction; never executes the probes."""
import argparse
import json
import os
import re
from urllib.parse import unquote
from pathlib import Path
import sys
from tools.ci.p1_capture import capture
from tools.ci.p1_reports import codeql_rule, codeql_rules, normalize, public_summary, ReportRefused, relative_path, digest


PROBES = {
    "python": ("probe.py", "py/code-injection", 'from flask import Flask, request\napp = Flask(__name__)\n@app.route("/probe")\ndef probe():\n    return str(eval(request.args["expression"]))\n'),
    "javascript-typescript": ("probe.js", "js/code-injection", 'const express = require("express");\nconst app = express();\napp.get("/probe", (req, res) => res.send(eval(req.query.expression)));\n'),
    "java": ("Probe.java", "java/sql-injection", 'import java.sql.Connection;\nimport javax.servlet.http.HttpServletRequest;\npublic class Probe {\n public void probe(HttpServletRequest request, Connection connection) throws Exception {\n  connection.createStatement().executeQuery("SELECT * FROM synthetic WHERE id = " + request.getParameter("id"));\n }\n'),
}


def prepare(root, language):
    name, _, text = PROBES[language]
    folder = root / "p1-synthetic-codeql"
    folder.mkdir(exist_ok=False)
    (folder / name).write_text(text, encoding="utf-8")


def review_locations(payload, report, root, allowed):
    """Retain rule IDs and numeric locations only; never SARIF prose or flows.

    Critical finding details stay out of public artifacts. They still count
    and fail the unchanged gate, and require private operator review.
    """
    indexed = {(r["path"], r["fingerprint"]): r for r in report["findings"]}
    details = []
    for run in payload["runs"]:
        rules = codeql_rules(run)
        for row in run.get("results", []):
            codeql_rule(run, row, rules)
            rule = row["ruleId"]
            if not re.fullmatch(r"(?:py|java|js)/[a-z0-9][a-z0-9/-]{0,199}", rule):
                raise ReportRefused("codeql-review-identity")
            for location in row["locations"]:
                physical = location["physicalLocation"]
                path = relative_path(unquote(physical["artifactLocation"]["uri"]), root, allowed)
                region = physical.get("region", {})
                fingerprint = digest(["codeql", path, [rule, region]])
                finding = indexed[(path, fingerprint)]
                if finding["severity"] == "critical":
                    continue
                line = region.get("startLine")
                if type(line) is not int or not 1 <= line <= 100000000:
                    raise ReportRefused("codeql-review-location")
                end = region.get("endLine", line)
                if type(end) is not int or not line <= end <= 100000000:
                    raise ReportRefused("codeql-review-location")
                details.append(dict(path=path, rule_id=rule, start_line=line,
                                    end_line=end, severity=finding["severity"],
                                    fingerprint=fingerprint))
    expected = sum(r["severity"] != "critical" for r in report["findings"])
    if len(details) != expected:
        raise ReportRefused("codeql-review-inventory")
    return sorted(details, key=lambda r: (r["path"], r["start_line"], r["rule_id"], r["fingerprint"]))


def reduce(root, language, directory, output):
    files = list(directory.glob("*.sarif"))
    if len(files) != 1:
        raise ReportRefused("codeql-report-inventory")
    payload = json.loads(files[0].read_bytes())
    name, rule, _ = PROBES[language]
    probe = "p1-synthetic-codeql/" + name
    code, raw, _ = capture(["git", "ls-files", "-z"], root)
    if code:
        raise ReportRefused("source-inventory")
    allowed = set(filter(None, raw.decode("utf-8").split("\0"))) | {probe}
    probe_findings = 0
    for run in payload["runs"]:
        rules = codeql_rules(run)
        retained = []
        for row in run.get("results", []):
            codeql_rule(run, row, rules)
            locations = [x["physicalLocation"]["artifactLocation"]["uri"] for x in row["locations"]]
            if locations and all(p == probe for p in locations):
                if row["ruleId"] == rule:
                    probe_findings += 1
            else:
                retained.append(row)
        run["results"] = retained
    if not probe_findings:
        raise ReportRefused("codeql-negative-control")
    report = normalize("codeql", payload, root, allowed - {probe})
    details = review_locations(payload, report, root, allowed - {probe})
    summary = public_summary(report)
    critical = sum(r["severity"] == "critical" for r in report["findings"])
    summary["files"] = public_summary(dict(report, findings=[
        r for r in report["findings"] if r["severity"] != "critical"]))["files"]
    result = dict(schema="p1-codeql-measurement/1", language=language,
                  checkout=os.environ.get("GITHUB_SHA"), run_id=os.environ.get("GITHUB_RUN_ID"),
                  run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
                  negative_control_detected=True, summary=summary,
                  review_schema="p1-codeql-review-locations/1", review_locations=details,
                  critical_details_withheld=critical,
                  private_operator_review_required=bool(critical))
    output.mkdir(parents=True, exist_ok=True)
    with (output / (language + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    return not report["findings"]



def failure_report(language, error):
    # Closed vocabulary: arbitrary exception text can contain raw SARIF/source.
    known = {"codeql-report-inventory", "codeql-incomplete", "codeql-negative-control",
             "source-inventory", "scanner-path", "scanner-unbound-path", "scanner-schema",
             "scanner-severity", "scanner-location", "scanner-unsupported", "capture-failed",
             "capture-output-limit", "codeql-review-identity", "codeql-review-location",
             "codeql-review-inventory"}
    return dict(schema="p1-codeql-incomplete/1", language=language, completed=False,
                error_type=type(error).__name__ if type(error) in
                (ReportRefused, ValueError, KeyError, TypeError, UnicodeError) else "other",
                refusal_code=str(error) if type(error) is ReportRefused and str(error) in known else "unclassified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "reduce"))
    parser.add_argument("--language", choices=PROBES, required=True)
    parser.add_argument("--sarif", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise ReportRefused("ci-only")
        if args.mode == "prepare":
            prepare(Path.cwd(), args.language)
            return 0
        ok = reduce(Path.cwd(), args.language, args.sarif, args.output)
        print("CodeQL controls and scan passed" if ok else "CodeQL findings require review")
        return 0 if ok else 1
    except Exception as error:
        diagnostic = failure_report(args.language, error)
        if args.mode == "reduce" and args.output is not None:
            args.output.mkdir(parents=True, exist_ok=True)
            with (args.output / (args.language + "-incomplete.json")).open("x", encoding="utf-8") as stream:
                json.dump(diagnostic, stream, indent=2)
        print(json.dumps(diagnostic), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
