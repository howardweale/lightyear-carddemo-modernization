"""Trusted-main publisher: downloaded build artifacts are data, never code."""
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile
from tools.carddemo_release_retention import Github, REPO, match_asset, validate_release
from hashlib import sha256
MI = 1024 * 1024
def sha(raw): return sha256(raw).hexdigest()
def save(path, value):
    raw = (json.dumps(value, indent=2) + "\n").encode()
    if len(raw) >= 50000: raise ValueError("metadata-size")
    with path.open("xb") as stream: stream.write(raw)


def validate_run(run):
    if (run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/lightyear-verify-mcp.yml'
            or run.get('event') not in ('pull_request', 'push')
            or run.get('repository', {}).get('full_name') != REPO or run['repository'].get('private') is not False
            or run.get('head_repository', {}).get('full_name') != REPO
            or not re.fullmatch('[0-9a-f]{40}', run.get('head_sha', ''))):
        raise ValueError('untrusted-graph-source-run')


def payload(raw, artifact, run):
    if len(raw) != artifact['size_in_bytes'] or 'sha256:' + sha(raw) != artifact['digest']:
        raise ValueError('artifact-digest')
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) != 4 or sum(e.file_size for e in entries) > 512000:
            raise ValueError('artifact-expanded-size')
        for entry in entries:
            allowed = entry.filename in {'graph-on-acceptance.json', 'unsigned-activation-preparation.json',
                                          'ci-fixture-approval-proof.json'} or re.fullmatch(
                                              r'graph-inventory-scan-\d{4}-\d{2}-\d{2}T\d{6}Z\.json', entry.filename)
            if (not allowed or entry.filename in files or entry.file_size > 256000
                    or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG) or entry.flag_bits & 1):
                raise ValueError('artifact-entry')
            files[entry.filename] = archive.read(entry)
    scan_names = [n for n in files if n.startswith('graph-inventory-scan-')]
    if len(scan_names) != 1 or not {'graph-on-acceptance.json', 'unsigned-activation-preparation.json',
                                  'ci-fixture-approval-proof.json'} <= set(files):
        raise ValueError('artifact-closure')
    report = json.loads(files['graph-on-acceptance.json'])
    scan = json.loads(files[scan_names[0]])
    request = json.loads(files['unsigned-activation-preparation.json'])
    if (report['schema'] != 'verify-graph-on-acceptance/1' or report['status'] != 'passed'
            or (report['commit'], str(report['run_id']), str(report['run_attempt'])) !=
               (run['head_sha'], str(run['id']), str(run['run_attempt']))
            or report['authority'] != 'ephemeral-CI-fixture' or report['live_activation'] is not False
            or report['tools_exercised'] != 16 or report['actual_native_submissions'] != 5
            or report['offline_replays'] != 5 or report['model_calls'] != 0):
        raise ValueError('acceptance-provenance')
    if (scan['schema'] != 'verify-graph-inventory-scan/1' or scan['status'] != 'passed'
            or scan['all_projection_members_scanned'] is not True or scan['short_protected_values_scanned'] is not True
            or scan['nodes'] <= 0 or scan['source_excerpts'] <= 0
            or scan['authority'] != 'ephemeral-CI-fixture'
            or scan['projection_sha256'] != report['projection_sha256']):
        raise ValueError('inventory-scan')
    if (request['schema'] != 'verify-graph-activation-preparation/1'
            or request['unsigned'] is not True or request['importable'] is not False
            or request['activation_authorized'] is not False
            or request['approval_scope'] != 'ephemeral-CI-fixture-only'
            or not request['remaining']):
        raise ValueError('activation-boundary')
    for key in ('projection_sha256', 'approval_proof_sha256', 'leak_scan_sha256',
                'commit', 'run_id', 'run_attempt'):
        if request[key] != report[key]:
            raise ValueError('request-binding')
    if (request['acceptance_sha256'] != sha(files['graph-on-acceptance.json'])
            or report['leak_scan_sha256'] != sha(files[scan_names[0]])
            or report['approval_proof_sha256'] != sha(files['ci-fixture-approval-proof.json'])):
        raise ValueError('payload-hash')
    for name in (scan_names[0], 'graph-on-acceptance.json', 'unsigned-activation-preparation.json'):
        if len(files[name]) >= 50000:
            raise ValueError('report-size')
    return files


def retain(client, run_id, output):
    run = client.api(f'actions/runs/{run_id}'); validate_run(run)
    if run['id'] != run_id: raise ValueError('run-identity')
    jobs = client.pages(f'actions/runs/{run_id}/attempts/{run["run_attempt"]}/jobs', 'jobs')
    if len(jobs) != 1 or jobs[0]['name'] != 'isolated-judge' or jobs[0]['conclusion'] != 'success' or jobs[0]['status'] != 'completed': raise ValueError('source-job')
    artifacts = [a for a in client.pages(f'actions/runs/{run_id}/artifacts', 'artifacts') if a['name'] == f'verify-graph-public-{run["run_attempt"]}']
    if len(artifacts) != 1: raise ValueError('source-artifact')
    artifact = artifacts[0]
    if artifact['expired'] or not 0 < artifact['size_in_bytes'] <= MI or not re.fullmatch('sha256:[0-9a-f]{64}', artifact.get('digest', '')): raise ValueError('artifact-metadata')
    if artifact.get('workflow_run', {}).get('id') != run_id: raise ValueError('artifact-run')
    files = payload(client.download(f'actions/artifacts/{artifact["id"]}/zip'), artifact, run)
    tag = f'verify-graph-run{run_id}-attempt{run["run_attempt"]}'
    def tag_matches():
        ref = client.api('git/ref/tags/' + tag)
        if ref['object']['type'] != 'commit' or ref['object']['sha'] != run['head_sha']: raise ValueError('release-tag-changed')
    release = client.release(tag)
    if release is None:
        refs = [r for r in client.api('git/matching-refs/tags/' + tag) if r['ref'] == 'refs/tags/' + tag]
        if not refs: client.api('git/refs', method='POST', ref='refs/tags/' + tag, sha=run['head_sha'])
        tag_matches()
        release = client.api('releases', method='POST', tag_name=tag, draft=True, prerelease=True, name='Verify graph CI ' + tag, body='Public graph acceptance fixture; unsigned retention only. No live activation or operator approval.')
    tag_matches()
    validate_release(release, tag)
    rows = [dict(name=n, bytes=len(b), sha256=sha(b), release=tag, url=f'https://github.com/{REPO}/releases/download/{tag}/{n}') for n, b in sorted(files.items())]
    manifest = dict(schema='public-evidence-retention/1', repository=REPO, prepared_on=run['run_started_at'][:10], source_evidence_date=run['run_started_at'][:10], scope='public graph CI acceptance fixture only', store='GitHub Release assets', source_head=run['head_sha'], source_run=run_id, source_attempt=run['run_attempt'], release_url=f'https://github.com/{REPO}/releases/tag/{tag}', source_artifact_sha256=artifact['digest'][7:], assets=rows)
    output.mkdir(parents=True, exist_ok=True); save(output / 'retention-manifest.json', manifest)
    files['retention-manifest.json'] = (output / 'retention-manifest.json').read_bytes()
    assets = client.pages(f'releases/{release["id"]}/assets'); indexed = {a['name']: a for a in assets}
    if len(indexed) != len(assets) or set(indexed) - set(files): raise ValueError('release-extra-assets')
    for name, raw in files.items():
        if name in indexed:
            if not match_asset(indexed[name], raw): raise ValueError('immutable-release-mismatch')
        else:
            if not release['draft']: raise ValueError('published-release-incomplete')
            path = output / name; path.write_bytes(raw); client.upload(tag, path)
    assets = client.pages(f'releases/{release["id"]}/assets')
    if len(assets) != len(files) or any(a['name'] not in files or not match_asset(a, files[a['name']]) for a in assets): raise ValueError('release-byte-verification')
    fresh = client.api(f'actions/runs/{run_id}'); validate_run(fresh)
    if (fresh['head_sha'], fresh['run_attempt']) != (run['head_sha'], run['run_attempt']): raise ValueError('source-advanced')
    tag_matches()
    if release['draft']:
        if client.api(f'releases/{release["id"]}', method='PATCH', draft=False, make_latest='false')['draft']: raise ValueError('release-not-published')
    publication = output / 'publication'; publication.mkdir(exist_ok=True)
    save(publication / 'retention-manifest.json', manifest); (publication / 'summary.json').write_bytes(files['graph-on-acceptance.json'])
    return manifest

if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise SystemExit('CI-only retention')
    retain(Github(), int(sys.argv[1]), Path(sys.argv[2]))
