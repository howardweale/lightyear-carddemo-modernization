"""Synthetic CodeQL controls and safe reduction; never executes the probes."""
import argparse
import json
import os
from pathlib import Path
import sys
from tools.ci.p1_capture import capture
from tools.ci.p1_reports import normalize, public_summary, ReportRefused


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
        if not run["tool"]["driver"]["rules"] or any(i.get("executionSuccessful") is False for i in run.get("invocations", [])):
            raise ReportRefused("codeql-incomplete")
        retained = []
        for row in run.get("results", []):
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
    result = dict(schema="p1-codeql-measurement/1", language=language,
                  checkout=os.environ.get("GITHUB_SHA"), run_id=os.environ.get("GITHUB_RUN_ID"),
                  run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT"),
                  negative_control_detected=True, summary=public_summary(report))
    output.mkdir(parents=True, exist_ok=True)
    with (output / (language + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
    return not report["findings"]


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
    except Exception:
        print("CodeQL scan incomplete; no raw diagnostic published", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
