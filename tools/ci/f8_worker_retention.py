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
from tools.ci.f8_worker_bundle import CAP, DOC, MI, PAYLOAD, inspect_capsule, save, sha


def validate_run(run):
    if (run.get('status') != 'completed' or run.get('conclusion') != 'success'
            or run.get('path') != '.github/workflows/f8-worker-bundle.yml'
            or run.get('event') not in ('pull_request', 'push')
            or run.get('repository', {}).get('full_name') != REPO or run['repository'].get('private') is not False
            or run.get('head_repository', {}).get('full_name') != REPO
            or not re.fullmatch('[0-9a-f]{40}', run.get('head_sha', ''))):
        raise ValueError('untrusted-F8-source-run')


def payload(raw, artifact, run):
    if len(raw) != artifact['size_in_bytes'] or 'sha256:' + sha(raw) != artifact['digest']: raise ValueError('artifact-digest')
    files = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if sum(e.file_size for e in archive.infolist()) > 48 * MI: raise ValueError("artifact-expanded-size")
        for entry in archive.infolist():
            if (entry.filename not in PAYLOAD or entry.filename in files or entry.file_size > 40 * MI
                    or stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG) or entry.flag_bits & 1): raise ValueError('artifact-entry')
            files[entry.filename] = archive.read(entry)
    if set(files) != PAYLOAD or sum(map(len, files.values())) > 48 * MI: raise ValueError('artifact-closure')
    summary = json.loads(files['summary.json']); conformance = json.loads(files['conformance.json'])
    if (len(files['summary.json']) >= 50000 or summary['schema'] != 'f8-worker-bundle/1'
            or (summary['source_head'], summary['source_run'], summary['source_attempt']) != (run['head_sha'], run['id'], run['run_attempt'])
            or summary['factory_run_acceptance'] is not False or summary['fixture_only'] is not True
            or conformance['factory_run_acceptance'] is not False or conformance['fixture_only'] is not True): raise ValueError('fixture-provenance')
    for name, key in [('capsule.tar.gz', 'capsule'), ('capsule-files.json', 'capsule_files'), ('workspace-manifest.json', 'workspace_manifest'), ('conformance.json', 'conformance')]:
        if sha(files[name]) != summary[key + '_sha256']: raise ValueError('payload-hash')
    if len(files['capsule.tar.gz']) != summary['capsule_bytes']: raise ValueError('capsule-size')
    capsule = json.loads(files['capsule-files.json']); inspect_capsule(files['capsule.tar.gz'], capsule)
    public = json.loads(Path(DOC + 'workspace-manifest-proposal-2026-10-20.json').read_bytes())
    expected = {p: d for p, d in public.items() if not p.endswith('.java')}
    expected.update({CAP + '/' + p: d for p, d in capsule.items()})
    if json.loads(files['workspace-manifest.json']) != expected: raise ValueError('workspace-closure')
    image = json.loads(Path(DOC + 'java-image-pin-r2-2026-10-20.json').read_bytes())['selection']['reference']
    positive = conformance['positive']['gates'][0]; negative = conformance['missing_dependency']['gates'][0]
    if (summary['image'] != image or positive['status'] != 'passed' or negative['status'] != 'failed'
            or 'F8_ISOLATION_CHECKS_PASSED' not in positive['stdout'] or positive['execution']['enforced'] is not True
            or positive['execution']['image'] != image or positive['execution']['network_mode'] != 'none'): raise ValueError('conformance-required')
    return files


def retain(client, run_id, output):
    run = client.api(f'actions/runs/{run_id}'); validate_run(run)
    if run['id'] != run_id: raise ValueError('run-identity')
    jobs = client.pages(f'actions/runs/{run_id}/attempts/{run["run_attempt"]}/jobs', 'jobs')
    if len(jobs) != 1 or jobs[0]['name'] != 'assemble-offline-worker' or jobs[0]['conclusion'] != 'success' or jobs[0]['status'] != 'completed': raise ValueError('source-job')
    artifacts = [a for a in client.pages(f'actions/runs/{run_id}/artifacts', 'artifacts') if a['name'] == f'f8-worker-offline-{run["run_attempt"]}']
    if len(artifacts) != 1: raise ValueError('source-artifact')
    artifact = artifacts[0]
    if artifact['expired'] or not 0 < artifact['size_in_bytes'] <= 64 * MI or not re.fullmatch('sha256:[0-9a-f]{64}', artifact.get('digest', '')): raise ValueError('artifact-metadata')
    files = payload(client.download(f'actions/artifacts/{artifact["id"]}/zip'), artifact, run)
    tag = f'f8-worker-run{run_id}-attempt{run["run_attempt"]}'
    def tag_matches():
        ref = client.api('git/ref/tags/' + tag)
        if ref['object']['type'] != 'commit' or ref['object']['sha'] != run['head_sha']: raise ValueError('release-tag-changed')
    release = client.release(tag)
    if release is None:
        refs = [r for r in client.api('git/matching-refs/tags/' + tag) if r['ref'] == 'refs/tags/' + tag]
        if not refs: client.api('git/refs', method='POST', ref='refs/tags/' + tag, sha=run['head_sha'])
        tag_matches()
        release = client.api('releases', method='POST', tag_name=tag, draft=True, prerelease=True, name='F8 offline worker ' + tag, body='Public CI packaging fixture; unsigned retention only. No factory acceptance or approval.')
    tag_matches()
    validate_release(release, tag)
    rows = [dict(name=n, bytes=len(b), sha256=sha(b), release=tag, url=f'https://github.com/{REPO}/releases/download/{tag}/{n}') for n, b in sorted(files.items())]
    manifest = dict(schema='public-evidence-retention/1', repository=REPO, prepared_on=run['run_started_at'][:10], source_evidence_date=run['run_started_at'][:10], scope='public F8 packaging fixture only', store='GitHub Release assets', source_head=run['head_sha'], source_run=run_id, source_attempt=run['run_attempt'], release_url=f'https://github.com/{REPO}/releases/tag/{tag}', source_artifact_sha256=artifact['digest'][7:], assets=rows)
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
    save(publication / 'retention-manifest.json', manifest); (publication / 'summary.json').write_bytes(files['summary.json'])
    return manifest

if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true': raise SystemExit('CI-only retention')
    retain(Github(), int(sys.argv[1]), Path(sys.argv[2]))
