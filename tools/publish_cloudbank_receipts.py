#!/usr/bin/env python3
"""Build or verify public receipt projections. No cloud operations or new runs."""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lightyear_data.cloudbank_publication import load_publication  # noqa: E402

START = "<!-- BEGIN CLOUDBANK EXECUTION RECEIPTS -->"
END = "<!-- END CLOUDBANK EXECUTION RECEIPTS -->"
NOTE = "MS67 qualifies the bound synthetic nonproduction platform. Customer IdP, representative customer data and workload, customer approval, production deployment and final production readiness remain MS68."


def local_link(path: str) -> str:
    return path.removeprefix("docs/receipts/")


def website_block(p: dict) -> str:
    s = p["summary"]
    return f'''{START}
  <div class="band"><div class="wrap">
    <div class="eyebrow">CloudBank execution evidence · {p['published_on']}</div>
    <h2 style="margin:16px 0 20px">MS67 complete. Nonproduction platform qualified.</h2>
    <p class="lead">All {s['platform_scenarios']} platform scenarios passed across {s['services']} services and {s['ready_replicas']} ready replicas. The published chain retains the MS54–66 results and the accepted load and database recovery evidence.</p>
    <div class="grid4">
      <div class="stat"><div class="n">{s['load_requests']:,}</div><div class="l">requests · {s['load_duration_seconds']} seconds<br>{s['load_vus']} virtual users · {s['load_errors']} errors</div></div>
      <div class="stat"><div class="n">{s['load_p95_ms']:.1f} ms</div><div class="l">aggregate HTTP p95<br>bounded regional load</div></div>
      <div class="stat"><div class="n">{s['pitr_rto_seconds']} s</div><div class="l">PITR recovery<br>approved limit {s['pitr_limit_seconds']} seconds</div></div>
      <div class="stat"><div class="n">{s['business_journeys']}</div><div class="l">business journeys<br>bounded whole-application equivalence</div></div>
    </div>
    <p><a href="receipts/">Read all MS54–67 receipts and measured results →</a></p>
    <p class="note">{NOTE} Aggregate p95 includes all operations; chat p95 was {s['chat_p95_ms']/1000:.2f} seconds.</p>
  </div></div>
{END}'''


def outputs(p: dict) -> dict[Path, str]:
    s = p["summary"]
    rows = []
    for row in p["milestones"]:
        links = " · ".join(f'<a href="{local_link(f["path"])}">{"Source build" if "source-build" in f["role"] else "Oracle runtime" if "oracle-runtime" in f["role"] else "Receipt"}</a>' for f in row["receipts"])
        rows.append(f'<tr id="ms{row["number"]}"><th scope="row">MS{row["number"]}</th><td>{html.escape(row["scope"])}</td><td class="passed">{row["status"]}</td><td>{links}</td></tr>')
    evidence = []
    for f in p["files"]:
        value = f['status'] or ('passed rehearsal' if f['role'] == 'retained-ms65' else 'bound supporting evidence')
        evidence.append(f'<li><a href="{local_link(f["path"])}">{html.escape(f["role"])}</a><span> — {html.escape(value)}</span><details><summary>Hashes and original source</summary><p>Content SHA-256: <code>{f["content_sha256"]}</code></p><p>File SHA-256: <code>{f["file_sha256"]}</code></p><p>Original source: <code>{html.escape(f["source_uri"])}</code></p></details></li>')
    proof_by_hash = {f['content_sha256']: f for f in p['files']}
    scenarios = ''.join(f'<li>{html.escape(r["id"])} · <a href="{local_link(proof_by_hash[r["evidence_sha256"]]["path"])}">passed evidence</a></li>' for r in p['scenarios'])
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CloudBank MS54–67 execution receipts | LIGHTYEAR</title>
<meta name="description" content="Completed CloudBank MS67 nonproduction qualification and the original MS54–67 execution receipt chain.">
<style>
:root{{color-scheme:light;--ink:#15184d;--muted:#676985;--line:#ddd7f2;--violet:#6942d6}}
*{{box-sizing:border-box}}body{{margin:0;background:#f7f6fc;color:var(--ink);font:16px/1.6 system-ui,sans-serif}}header,main,footer{{max-width:1120px;margin:auto;padding:32px 24px}}header img{{width:130px}}nav{{display:flex;gap:24px;flex-wrap:wrap;margin-top:20px}}a{{color:var(--violet)}}h1{{font-size:clamp(2rem,5vw,3.4rem);line-height:1.12;margin:24px 0 16px}}h2{{margin-top:40px}}.kicker{{color:#456a43;font-weight:700}}.lead{{font-size:1.15rem;max-width:850px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}}.metric{{padding:18px;background:white;border:1px solid var(--line);border-radius:8px}}.metric b{{display:block;font-size:1.75rem}}.metric span,.muted{{color:var(--muted)}}.table-wrap{{overflow:auto}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{text-align:left;padding:14px;border-bottom:1px solid var(--line)}}thead{{background:#efebfb}}.passed{{color:#2a682e;font-weight:650;white-space:nowrap}}code{{overflow-wrap:anywhere;white-space:normal;font-size:.85em}}li{{margin:12px 0}}details{{font-size:.9rem;margin-top:6px}}summary{{cursor:pointer;color:var(--muted)}}.boundary{{border-left:4px solid #a7702c;padding:10px 20px;background:white}}footer{{font-size:.9rem;color:var(--muted)}}@media(max-width:700px){{.metrics{{grid-template-columns:repeat(2,1fr)}}th,td{{padding:10px}}}}
</style></head><body>
<header><a href="../"><img src="../assets/lightyear-primary.svg" alt="LIGHTYEAR"></a><nav><a href="../#proof">Website proof</a><a href="../milestones/">Milestone library</a><a href="catalog.json">Receipt catalog JSON</a></nav>
<p class="kicker">COMPLETED · {p['published_on']} · us-west1</p><h1>MS67 nonproduction qualification passed</h1>
<p class="lead">The final signed receipt closes all {s['platform_scenarios']} platform scenarios for {s['services']} services and {s['ready_replicas']} ready replicas. MS65 rehearsal and MS66 bounded whole-application equivalence are retained in the same evidence chain.</p>
<p><a href="{local_link(p['receipt_path'])}">Open the final MS67 receipt</a></p></header>
<main><div class="metrics"><div class="metric"><b>{s['load_requests']:,}</b><span>requests · {s['load_errors']} errors</span></div><div class="metric"><b>{s['load_p95_ms']:.1f} ms</b><span>aggregate HTTP p95</span></div><div class="metric"><b>{s['pitr_rto_seconds']} / {s['pitr_limit_seconds']} s</b><span>PITR recovery / limit</span></div><div class="metric"><b>{s['business_journeys']}</b><span>business journeys</span></div></div>
<p>The regional load ran for a configured {s['load_duration_seconds']} seconds with {s['load_vus']} virtual users. Aggregate p95 covers all operations; chat p95 was {s['chat_p95_ms']/1000:.2f} seconds. Backup restore took {s['backup_restore_rto_seconds']} seconds; recovery point age was {s['rpo_seconds']} seconds.</p>
<p>PITR was accepted under the owner-approved 630-second nonproduction requirement, <code>{s['sql_policy_id']}</code>. The original 622-second measurement and prior failed assessment are preserved inside the SQL receipt. No recovery measurement was changed.</p>
<p class="boundary">{NOTE}</p>
<h2>Milestone receipts</h2><p>Each result applies to the sources, images, environment and bounded scope recorded in its receipt. MS58 records plan admission; subsequent milestones provide execution evidence.</p>
<div class="table-wrap"><table><thead><tr><th>Milestone</th><th>Qualified scope</th><th>Result</th><th>Original JSON</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Verification and provenance</h2><p>The operator exporter verified HMAC signatures before upload. Publication checks the original file hashes, canonical content hashes and receipt bindings, including all 28 scenario evidence references. The public publisher does not possess or independently reverify the HMAC key.</p>
<p>Run: <code>{p['run_id']}</code><br>Final receipt content SHA-256: <code>{p['receipt_content_sha256']}</code></p>
<p><a href="{local_link(p['verification']['export_manifest_path'])}">Original export manifest</a> · <a href="catalog.json">Public catalog</a></p>
<p>These are archived execution results. They do not assert continuous live health. Historical failures and controller transitions remain referenced by the signed evidence index in private Cloud Storage. This publication contains the 31 exported current-chain documents, with their bytes unchanged.</p>
<h2>All 28 platform scenarios</h2><ol>{scenarios}</ol>
<h2>All 31 exported evidence files</h2><ul>{''.join(evidence)}</ul></main>
<footer>LIGHTYEAR · Synthetic nonproduction execution evidence · Published from GitHub</footer></body></html>
'''
    readme = f"# CloudBank execution receipts\n\nMS67 is complete for the bound synthetic nonproduction platform.\n\n[Published evidence index](https://howardweale.github.io/lightyear-carddemo-modernization/receipts/) · [Final receipt]({local_link(p['receipt_path'])}) · [Catalog](catalog.json)\n\nThe 31 original JSON files and exporter manifest are preserved byte for byte. Public verification checks file hashes, canonical content hashes and bindings. HMAC verification was performed by the operator exporter before upload; the public publisher does not have the key.\n\n{NOTE}\n\nDeterministic `factory/cloudbank/*/readiness.receipt.json` files remain admission contracts. The actual signed execution records are published here. Earlier milestones retain their own scope and flags; later qualification does not rewrite historical receipts.\n\nRebuild or verify these projections without cloud access:\n\n```bash\npython3 tools/publish_cloudbank_receipts.py build\npython3 tools/publish_cloudbank_receipts.py verify\n```\n"
    site = (ROOT / "docs/index.html").read_text()
    if site.count(START) != 1 or site.count(END) != 1:
        raise ValueError("website receipt block markers missing or duplicated")
    before, rest = site.split(START)
    _, after = rest.split(END)
    return {ROOT / "docs/receipts/catalog.json": json.dumps(p, indent=2, sort_keys=True) + "\n", ROOT / "docs/receipts/index.html": page, ROOT / "docs/receipts/README.md": readme, ROOT / "docs/index.html": before + website_block(p) + after}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args()
    publication = load_publication()
    for path, value in outputs(publication).items():
        if args.command == "build":
            path.write_text(value)
        elif not path.is_file() or path.read_text() != value:
            raise ValueError(f"stale receipt projection: {path.relative_to(ROOT)}")
    catalog = json.loads((ROOT / "docs/milestones/catalog.json").read_text())
    for row in publication['milestones']:
        entry = next(x for x in catalog['milestones'] if x['number'] == row['number'])
        if entry.get('execution_receipts') != [x['path'] for x in row['receipts']] or entry.get('status') != ('Plan admitted' if row['number'] == 58 else 'Complete — execution passed'):
            raise ValueError(f"milestone MS{row['number']} publication mismatch")
    print("MS54_MS67_PUBLICATION=VERIFIED; 31 original files; 28 bound scenarios; no new qualification run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
