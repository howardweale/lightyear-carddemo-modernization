"""Portable local reports. All supplied labels are escaped; no customer values copied."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
import shutil
import tempfile

from .contracts import MAX_JSON_BYTES, require


def percent(value):
    return "n/a" if value is None else f"{value * 100:.3f}%"


def esc(value):
    return html.escape(str(value), quote=True)


def markdown(report):
    s = report["summary"]
    lines = ["# Decidability report", "", esc(report["corpus_id"]), "",
             f"Decided **{s['decided_units']:,} / {s['in_scope_units']:,} in-scope units ({percent(s['decidability']['fraction'])})**.",
             f"Complete cases decided: **{s['cases']['decided']:,} / {s['cases']['total']:,} ({percent(s['cases']['decision_fraction'])})**.", "",
             f"Equivalent cases: {s['cases']['equivalent']:,}. Divergent cases: {s['cases']['divergent']:,}. Indeterminate cases: {s['cases']['indeterminate']:,}.",
             f"Excluded administrative units: {s['excluded_units']:,}. Unsupported units: {s['unsupported_units']:,}.", "",
             "Decidability counts both equivalent and divergent results. It is not a pass rate or proof of application equivalence.",
             "Scope: " + esc(report["provenance"]["scope"]),
             "Evidence mode: " + esc(report["provenance"]["mode"]) + ". No runtime invocation or source authentication is claimed.", "",
             "## Denominators by lane", "", "| Lane | All input units | Excluded | In scope | Decided | Decided / all input | Decided / in scope |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for lane, row in report["by_lane"].items():
        lines.append(f"| {esc(lane)} | {row['input_units']:,} | {row['excluded_units']:,} | {row['in_scope_units']:,} | {row['decided_units']:,} | {percent(row['decided_fraction_of_all_input_units'])} | {percent(row['decidability']['fraction'])} |")
    lines += ["", "## Causes", "", "Cause counts overlap when a unit has several blockers. The disjoint clusters in report.json account for every unresolved record exactly once.", "",
              "| Cause | Work required | Units | Sole recorded blocker | Cases |", "|---|---|---:|---:|---:|"]
    for c in report["causes"]:
        lines.append(f"| {esc(c['reason_code']).replace('|', '&#124;')} | {c['kind']} | {c['units']:,} | {c['sole_blocker_units']:,} | {c['cases']:,} |")
    lines += ["", "## Normalization proposals", "", "Drafts require domain evidence and review. No rule is applied and no gain is predicted."]
    for p in report["normalization_proposals"]:
        e, b = p["entry"], p["blast_radius"]
        lines += ["", "### " + esc(e["title"]), "", esc(e["hypothesis"]), "",
                  f"Scope: {b['scoped_units']:,} units across {b['scoped_cases']:,} cases. Targeted unresolved units: {b['targeted_unresolved_units']:,}.",
                  f"Already decided within scope: {b['already_decided_units']:,}. Known divergent units within scope: {b['known_divergent_units']:,}.",
                  f"Target units with no other recorded blocker: {b['units_with_no_other_recorded_blocker']:,}. This is not estimated lift.",
                  "", *["- Required evidence: " + esc(x) for x in e["required_evidence"]]]
    lines += ["", "## Next calibration run", "", "1. Select a cause and inspect its source-bound examples in the report.",
              "2. Narrow a draft proposal and recompute its blast radius with assess.",
              "3. Obtain domain evidence and governed review, then implement the separately tested comparator change.",
              "4. Rerun the same corpus and use compare to measure changes and surface lost divergences.", "",
              "A parser gap, missing observation or unresolved business meaning must not be hidden by a normalization.", "",
              "Corpus SHA-256: " + report["corpus_sha256"], "Report SHA-256: " + report["content_sha256"]]
    return "\n".join(lines) + "\n"


def html_report(report):
    s = report["summary"]
    rows = {r["id"]: r for r in report["records"]}
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
             '<title>Decidability report</title><style>body{font:17px/1.5 system-ui,sans-serif;max-width:1120px;margin:40px auto;padding:0 24px;color:#1d2d3f;background:#fff}h1{font-size:36px}h2{margin-top:40px}a{color:#5b36b5}table{border-collapse:collapse;width:100%;margin:18px 0}td,th{padding:10px 12px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top;overflow-wrap:anywhere}summary{cursor:pointer;font-weight:600}details{padding:12px 0;border-bottom:1px solid #ddd}code{overflow-wrap:anywhere}small{color:#526174}.metric{font-size:30px;font-weight:650}.scroll{overflow-x:auto}</style>',
             '<h1>Decidability report</h1><p>' + esc(report["corpus_id"]) + '</p>',
             f'<p class="metric">{percent(s["decidability"]["fraction"])} of in-scope units decided</p>',
             f'<p>{s["decided_units"]:,} decided / {s["in_scope_units"]:,} in scope. {s["excluded_units"]:,} administrative units excluded.</p>',
             f'<p><b>{s["cases"]["decided"]:,} / {s["cases"]["total"]:,} complete cases decided.</b> {s["cases"]["equivalent"]:,} equivalent, {s["cases"]["divergent"]:,} divergent, {s["cases"]["indeterminate"]:,} indeterminate.</p>',
             '<p>Decidability includes detected differences. It does not establish equivalence, production readiness or a customer engagement decision.</p>',
             '<p><b>Scope:</b> ' + esc(report["provenance"]["scope"]) + '<br><b>Evidence:</b> ' + esc(report["provenance"]["mode"]) + '. No runtime invocation. Source authentication is not established.</p>',
             '<p><b>Coverage threshold:</b> ' + esc(report["threshold"]["status"]) + '</p>',
             '<p><a href="report.json">Complete evidence and cluster membership</a> · <a href="proposals.json">Draft proposals</a> · <a href="report.md">Text report</a></p>',
             '<h2>Denominators by lane</h2><div class="scroll"><table><tr><th>Lane</th><th>All input</th><th>Excluded</th><th>In scope</th><th>Decided</th><th>Decided / all</th><th>Decided / in scope</th></tr>']
    for lane, c in report["by_lane"].items():
        parts.append(f'<tr><td>{esc(lane)}</td><td>{c["input_units"]:,}</td><td>{c["excluded_units"]:,}</td><td>{c["in_scope_units"]:,}</td><td>{c["decided_units"]:,}</td><td>{percent(c["decided_fraction_of_all_input_units"])}</td><td>{percent(c["decidability"]["fraction"])}</td></tr>')
    parts += ['</table></div><h2>Causes and required work</h2><p>A unit can have multiple causes. Counts in this table overlap.</p><div class="scroll"><table><tr><th>Cause</th><th>Work</th><th>Units</th><th>Sole blocker</th></tr>']
    for c in report["causes"]:
        parts.append(f'<tr><td>{esc(c["reason_code"])}</td><td>{esc(c["kind"])}</td><td>{c["units"]:,}</td><td>{c["sole_blocker_units"]:,}</td></tr>')
    parts += ['</table></div><h2>Disjoint unresolved clusters</h2>',
              f'<p>{len(report["clusters"]):,} clusters cover {report["accounting"]["unresolved_units"]:,} unresolved units. Every unresolved record appears once. Expand for up to five examples; report.json retains every membership and source range.</p>']
    for c in report["clusters"]:
        parts.append(f'<details><summary>{esc(c["kind"])}: {c["units"]:,} units in {c["cases"]:,} cases</summary><p>{esc(", ".join(c["reason_codes"]))}</p><ul>')
        for rid in c["record_ids"][:5]:
            r = rows[rid]
            loc = r["source"]
            where = str(loc.get("path") or r["case_id"])
            if "start_line" in loc:
                where += f':{loc["start_line"]}–{loc["end_line"]}'
            parts.append(f'<li>{esc(r["lane"])} — {esc(where)} <small>({r["units"]:,} units; {esc(rid)})</small></li>')
        parts.append('</ul></details>')
    parts += ['<h2>Review-only normalization proposals</h2><p>Scopes show everything a proposed rule could affect in this corpus, including existing decisions. No normalization runs and no future gain is assumed.</p>']
    if not report["normalization_proposals"]:
        parts.append('<p>No normalization opportunity is classified by the current cause catalog. Unresolved cases still appear above as parser, evidence, alignment or investigation work.</p>')
    for p in report["normalization_proposals"]:
        e, b = p["entry"], p["blast_radius"]
        parts += ['<details><summary>' + esc(e["title"]) + '</summary><p>' + esc(e["hypothesis"]) + '</p>',
                  f'<p>Scope: <b>{b["scoped_units"]:,} units / {b["scoped_cases"]:,} cases</b>. Targeted unresolved: {b["targeted_unresolved_units"]:,}. Already decided: {b["already_decided_units"]:,}. Known divergent: {b["known_divergent_units"]:,}.</p>',
                  f'<p>{b["units_with_no_other_recorded_blocker"]:,} targeted units have no other recorded blocker. This is not a forecast of gain.</p><ul>',
                  *['<li>' + esc(x) + '</li>' for x in e["required_evidence"]], '</ul>',
                  '<p>Other blockers: ' + esc(json.dumps(b["remaining_blocker_units_by_cause"], sort_keys=True)) + '</p>',
                  '<p><small>Draft. Owner and review date require assignment. No approval or ledger mutation.</small></p></details>']
    parts += ['<h2>Calibration loop</h2><p>Inspect a cause, narrow a draft scope, gather domain evidence and review the change. After a separately implemented and tested comparator change, rerun the identical corpus and compare reports. Lost divergences and reduced coverage require review.</p>',
              '<p><small>Unit basis: ' + esc(report["accounting"]["unit_basis"]) + '</small></p>',
              '<p><small>Corpus: <code>' + report["corpus_sha256"] + '</code><br>Report: <code>' + report["content_sha256"] + '</code></small></p></html>']
    return '\n'.join(parts)


def publish(report, output):
    """Stage complete evidence before reserving a fresh output directory."""
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), "Output already exists; choose a new evidence directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".calibration-", dir=output.parent))
    try:
        encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
        require(len(encoded.encode()) <= MAX_JSON_BYTES, "Report exceeds 64 MiB; split into explicit corpora")
        (temp / "report.json").write_text(encoded, encoding="utf-8")
        (temp / "proposals.json").write_text(json.dumps([p["entry"] for p in report["normalization_proposals"]], indent=2, sort_keys=True) + '\n', encoding="utf-8")
        (temp / "report.md").write_text(markdown(report), encoding="utf-8")
        (temp / "index.html").write_text(html_report(report), encoding="utf-8")
        # mkdir reserves the destination atomically; another publisher cannot be replaced.
        output.mkdir()
        for path in temp.iterdir():
            os.replace(path, output / path.name)
    except Exception:
        # Leave any published evidence alone; a racing publisher may own output.
        raise
    finally:
        shutil.rmtree(temp)
