"""CI-only read-only acquisition and offline revision-9 pair comparison.

Never imports archive code, invokes a database, adjusts expectations or signs.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.request
import zipfile

from tools import export_tsql_r9 as export

REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
TAG = 'tsql-r9-evidence-2026-10-21'
SHA = re.compile('[0-9a-f]{64}')


def require(condition, code):
    if not condition:
        raise ValueError(code)


def write(path, value):
    with Path(path).open('xb') as stream:
        stream.write(export.canonical(value) + b'\n')


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def github(route):
    raw = subprocess.check_output(['gh', 'api', 'repos/' + REPOSITORY + '/' + route])
    return export.decode(raw)


def approved_assets(release, comment, package_sha):
    require(SHA.fullmatch(package_sha), 'package-sha')
    require(comment['user']['login'].casefold() == 'howardweale'
            and comment['issue_url'] == 'https://api.github.com/repos/' + REPOSITORY + '/issues/423',
            'Howard-PR423-comment-required')
    require(all(value in comment['body'] for value in (TAG, export.PACKAGE, package_sha)),
            'posted-tag-asset-sha-required')
    require(release['tag_name'] == TAG and not release['draft'] and not release['prerelease'], 'public-release-required')
    selected = {}
    for name in (export.PACKAGE, 'export-manifest.json'):
        matches = [a for a in release['assets'] if a['name'] == name]
        require(len(matches) == 1, 'unique-release-asset-required')
        asset = matches[0]
        limit = export.MAX_TOTAL + 8 * 1024 * 1024 if name == export.PACKAGE else 4 * 1024 * 1024
        require(asset['state'] == 'uploaded' and 0 < asset['size'] <= limit, 'asset-size-state')
        require(asset['browser_download_url'] ==
                'https://github.com/' + REPOSITORY + '/releases/download/' + TAG + '/' + name, 'asset-url')
        require(isinstance(asset.get('digest'), str) and asset['digest'].startswith('sha256:')
                and SHA.fullmatch(asset['digest'][7:]), 'GitHub-asset-digest-required')
        if name == export.PACKAGE:
            require(asset['digest'] == 'sha256:' + package_sha, 'posted-asset-digest-mismatch')
        selected[name] = {k: asset[k] for k in ('id', 'name', 'size', 'digest', 'browser_download_url')}
    return selected


def download(asset, destination):
    # Public release bytes only; no credentials are sent to download redirects.
    with urllib.request.urlopen(asset['browser_download_url'], timeout=60) as response, Path(destination).open('xb') as target:
        total = 0
        while True:
            raw = response.read(min(1024 * 1024, asset['size'] - total + 1))
            if not raw:
                break
            total += len(raw)
            require(total <= asset['size'], 'download-size-limit')
            target.write(raw)
    require(total == asset['size'] and 'sha256:' + file_sha(destination) == asset['digest'], 'download-identity')


def fetch(out, comment_id, package_sha):
    require(re.fullmatch('[1-9][0-9]*', comment_id), 'comment-id')
    release = github('releases/tags/' + TAG)
    comment = github('issues/comments/' + comment_id)
    assets = approved_assets(release, comment, package_sha)
    out.mkdir(parents=True, exist_ok=False)
    for name, asset in assets.items():
        download(asset, out / name)
    receipt = dict(schema='tsql-r9-public-acquisition/1', release_id=release['id'], tag=TAG,
                   approval_comment=comment['html_url'], approval_comment_id=int(comment_id),
                   approval_body_sha256=export.sha(comment['body'].encode('utf-8')),
                   package_sha256=package_sha, assets=assets)
    write(out / 'acquisition.json', receipt)
    return receipt


def unpack(package, manifest_path, expected_sha, destination):
    require(SHA.fullmatch(expected_sha) and file_sha(package) == expected_sha, 'package-digest')
    require(Path(manifest_path).stat().st_size <= 4 * 1024 * 1024, 'manifest-size')
    manifest = export.decode(Path(manifest_path).read_bytes())
    require(manifest['schema'] == 'tsql-r9-export/1'
            and manifest['package'] == export.PACKAGE
            and manifest['package_sha256'] == expected_sha
            and manifest['package_bytes'] == Path(package).stat().st_size
            and manifest['report_content_sha256'] == export.REPORT
            and manifest['public_key_sha256'] == export.KEY
            and manifest['signed_file_count'] == export.FILES
            and manifest['packaged_file_count'] == export.FILES + 1
            and manifest['native_pairs'] == 108, 'export-manifest-binding')
    files = manifest['files']
    require(len(files) == export.FILES + 1 and 'report.json' in files, 'manifest-closure')
    require(len({n.casefold() for n in files}) == len(files), 'case-colliding-paths')
    for name, row in files.items():
        export.relative(name)
        require(set(row) == {'bytes', 'sha256'} and type(row['bytes']) is int
                and 0 <= row['bytes'] <= export.MAX_FILE and SHA.fullmatch(row['sha256']), 'file-identity')
    require(sum(row['bytes'] for row in files.values()) == manifest['total_bytes'] <= export.MAX_TOTAL, 'total-size')
    with zipfile.ZipFile(package) as archive:
        members = archive.infolist()
        require(len(members) == len(files) and len({i.filename for i in members}) == len(members), 'zip-duplicate-or-count')
        require({i.filename for i in members} == {'revision-9/' + n for n in files}, 'zip-closure')
        for item in members:
            name = item.filename.removeprefix('revision-9/')
            require(item.create_system == 3 and stat.S_ISREG(item.external_attr >> 16)
                    and not item.flag_bits & 1 and item.compress_type == zipfile.ZIP_STORED
                    and item.file_size == files[name]['bytes'], 'zip-member-type-size')
        destination.mkdir(parents=True, exist_ok=False)
        for item in members:
            name = item.filename.removeprefix('revision-9/')
            raw = archive.read(item)
            require(len(raw) == files[name]['bytes'] and export.sha(raw) == files[name]['sha256'], 'zip-file-digest')
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as target:
                target.write(raw)
    # The existing exporter verifies signatures, all 1889 signed hashes, closure,
    # credential markers, the pinned report/key and all 108 pair manifest links.
    inspected = export.inspect(destination)
    require(inspected == {k: v for k, v in manifest.items()
                          if k not in ('package', 'package_sha256', 'package_bytes')}, 'reinspection-differs')
    return inspected


def differences(old, current, path=''):
    if type(old) is not type(current):
        return [dict(path=path, old=old, current=current)]
    if isinstance(old, dict):
        out = []
        for key in sorted(set(old) | set(current)):
            at = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in old or key not in current:
                out.append(dict(path=at, old_present=key in old, current_present=key in current,
                                old=old.get(key), current=current.get(key)))
            else:
                out.extend(differences(old[key], current[key], at))
        return out
    if isinstance(old, list):
        if len(old) != len(current):
            return [dict(path=path, old=old, current=current)]
        return [change for i, (a, b) in enumerate(zip(old, current))
                for change in differences(a, b, path + '/' + str(i))]
    return [] if old == current else [dict(path=path, old=old, current=current)]


def pair_inputs(root, record, public, plan, qualification):
    def signed(path):
        return export.envelope(export.decode((root / path).read_bytes()), public)
    index = record['index']
    require(type(index) is int and index > 0, 'pair-index')
    require(signed(f'progress-{index:03d}.json') == record, 'progress-binding')
    folder = f'pair-{index:03d}-{record["id"]}-{record["variant"]}-{record["repeat"]}'
    export.relative(folder)
    pair = root / folder
    manifest = export.decode((pair / 'manifest.json').read_bytes())
    require(manifest['content_sha256'] == record['manifest_sha256'], 'pair-content-binding')
    body = export.envelope(manifest, public)
    require(body['schema'] == 'tsql-native-pair/1' and body['model_calls'] == 0
            and set(body['files']) == {'source.json', 'target.json', 'comparison.json'}, 'pair-schema')
    require(body['plan_sha256'] == export.sha((root / 'plan.json').read_bytes())
            and body['images'] == plan['images'] and record['id'] in plan['ids'], 'pair-plan-binding')
    require(all(body.get(k) == record.get(k) for k in ('id', 'variant', 'repeat', 'scenario', 'case_sha256', 'index')),
            'pair-record-binding')
    values = {}
    for name, digest in body['files'].items():
        raw = (pair / name).read_bytes()
        require(export.sha(raw) == digest, 'pair-file-binding')
        values[name] = export.decode(raw)
    require({p.name for p in pair.iterdir()} == set(body['files']) | {'manifest.json'}, 'pair-closure')
    saved = values['comparison.json']
    require(saved['schema'] == 'tsql-native-comparison/9'
            and saved['mapping']['assets'] == body['assets']
            and saved.get('coverage_qualification') == qualification, 'historical-comparison-binding')
    historical_replay = signed(f'replay-{index:03d}.json')
    require(historical_replay['manifest_sha256'] == record['manifest_sha256']
            and historical_replay['comparison'] == saved
            and record['status'] == saved['observed_status']
            and record['verdict'] == saved['verdict'], 'historical-outcome-binding')
    for lane in ('source', 'target'):
        capture = values[lane + '.json']
        procedure = 'source' if lane == 'source' else record['variant']
        setup = 'source-setup' if lane == 'source' else ('target-setup' if record['variant'] == 'correct' else 'wrong-setup')
        require(capture['baseline']['procedure_sha256'] == body['assets'][procedure]['sha256']
                and capture['baseline']['setup_sha256'] == body['assets'][setup]['sha256'], 'capture-input-binding')
        policy = capture['observation'].get('policy_admission')
        require(not policy or policy['trusted_key_sha256'] == body.get('policy_authority_sha256'), 'policy-authority-binding')
    return values['source.json'], values['target.json'], saved


def compare_pair(source, target, saved):
    from lightyear_data.tsql_procedures.comparison_v9 import compare
    from lightyear_data.tsql_procedures.semantics import contract, resolve_results, target_contract
    contracts = {}
    errors = {}
    computations = {
        'syntax_contract': lambda: resolve_results(contract(source['observation']['source_syntax']), source['observation']),
        'target_syntax_contract': lambda: target_contract(target['observation']['target_source']),
    }
    for name, compute in computations.items():
        try:
            contracts[name] = compute()
        except Exception as failure:
            errors[name] = dict(type=type(failure).__name__, message=str(failure))
    try:
        current = compare(source, target, saved['mapping'], saved.get('coverage_qualification'))
        require(not errors, 'contract-computation-refused')
    except Exception as failure:
        # A refusal remains a reported result for this pair, never an omitted row.
        return dict(status='refused', error_type=type(failure).__name__, error=str(failure),
                    contracts=contracts, contract_errors=errors, original_comparison=saved,
                    old_outcome={k: saved[k] for k in ('observed_status', 'verdict')},
                    contract_changes=[d for name in contracts for d in
                        differences(saved.get(name), contracts[name], '/' + name)])
    changes = differences(saved, current)
    contract_changes = [d for d in changes if 'contract' in d['path']]
    return dict(status='unchanged' if not changes else 'changed',
                old_outcome={k: saved[k] for k in ('observed_status', 'verdict')},
                current_outcome={k: current[k] for k in ('observed_status', 'verdict')},
                outcome_changed=any(saved[k] != current[k] for k in ('observed_status', 'verdict')),
                contract_changes=contract_changes, changes=changes,
                original_comparison=saved, current_comparison=current)


def replay(root, out, acquisition):
    require(importlib.metadata.version('pglast') == '7.20', 'pglast-7.20-required')
    inspected = export.inspect(root)
    public = (root / 'evidence-public-key.bin').read_bytes()
    body = export.envelope(export.decode((root / 'report.json').read_bytes()), public)
    plan = export.envelope(export.decode((root / 'plan.json').read_bytes()), public)
    ready = export.envelope(export.decode((root / 'ready.json').read_bytes()), public)
    accepted = export.envelope(export.decode((root / 'm0-acceptance.json').read_bytes()), public)
    require(plan['owner'] == body['owner'] and plan['pairs'] == body['planned_pairs'], 'plan-owner-pairs')
    require(body['counts'] == dict(Counter(r['status'] for r in body['records'])), 'original-counts')
    require(accepted['schema'] == 'tsql-M0-acceptance/5' and accepted['passed']
            and accepted['procedures'] == 43 and accepted['native_pairs'] == 108
            and len(accepted['variants']) == 86 and all(v['accepted'] for v in accepted['variants']), 'original-86-of-86')
    for engine, image in plan['images'].items():
        require(image == ready['images'][engine]['Id'] or image in ready['images'][engine]['RepoDigests'], 'image-binding')
    qualification = export.decode((root / 'coverage-qualification.json').read_bytes())
    require(export.sha((root / 'coverage-qualification.json').read_bytes()) == plan['coverage_qualification_sha256']
            and qualification['images'] == plan['images']
            and qualification['bridge_sha256'] == plan['coverage_bridge_sha256'], 'qualification-binding')
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for record in body['records']:
        # Authentication failures abort rather than blessing untrusted inputs.
        source, target, saved = pair_inputs(root, record, public, plan, qualification)
        result = compare_pair(source, target, saved)
        name = f'pair-{record["index"]:03d}.json'
        result.update(index=record['index'], id=record['id'], variant=record['variant'], repeat=record['repeat'],
                      manifest_sha256=record['manifest_sha256'])
        write(out / name, result)
        rows.append(dict(index=record['index'], id=record['id'], variant=record['variant'],
                         status=result['status'], report=name, report_sha256=file_sha(out / name)))
    require(len(rows) == 108 and len({r['index'] for r in rows}) == 108, 'complete-108-pairs-required')
    audit_result = None
    audit_error = None
    if all(r['status'] == 'unchanged' for r in rows):
        # Preserve the original comprehensive acceptance replay. No patched
        # comparator, expectation replacement or edited receipt can make it pass.
        from tools.replay_tsql_native import audit
        try:
            audit_result = audit(root, export.REPORT, export.KEY)
            require(audit_result['qualification_passed'], 'original-audit-not-qualified')
        except Exception as failure:
            audit_error = dict(type=type(failure).__name__, message=str(failure))
    held = all(r['status'] == 'unchanged' for r in rows) and audit_result is not None and audit_error is None
    source_root = Path(__file__).resolve().parents[1]
    sources = {str(p.relative_to(source_root)).replace('\\', '/'): file_sha(p)
               for p in sorted((source_root / 'src/lightyear_data/tsql_procedures').glob('*.py'))}
    for name in ('tools/reverify_tsql_r9.py', 'tools/replay_tsql_native.py', 'tools/export_tsql_r9.py',
                 'tests/test_tsql_r9_reverification.py', 'tests/test_tsql_r9_export.py',
                 '.github/workflows/tsql-r9-reverification.yml', 'pyproject.toml'):
        sources[name] = file_sha(source_root / name)
    measured_at = datetime.now(timezone.utc).isoformat()
    summary = dict(schema='tsql-r9-parser-reverification/1', pglast='7.20', measured_at=measured_at,
                   report_content_sha256=export.REPORT, public_key_sha256=export.KEY,
                   signed_files=inspected['signed_file_count'], pairs=rows,
                   pair_counts=dict(Counter(r['status'] for r in rows)),
                   original_expected_outcomes='86/86 measured with the earlier parser',
                   holds_under_pglast_7_20=held, original_audit=audit_result, audit_error=audit_error,
                   acquisition=acquisition, source_hashes=sources,
                   checkout_commit=os.environ.get('GITHUB_SHA'), run_id=os.environ.get('GITHUB_RUN_ID'),
                   run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), database_calls=0, model_calls=0,
                   claim='Historical public-corpus re-verification; no new native run or release authorization')
    write(out / 'summary.json', summary)
    text = '# R3 Stage B — pglast 7.20\n\nMeasured at ' + measured_at + '.\n\n'
    text += ('The original 86/86 expected outcomes across 108 pairs hold under pglast 7.20.\n'
             if held else 'The original 86/86 was measured with the earlier parser; this run does not establish that it holds under pglast 7.20.\n')
    text += '\nAll 108 pairs are reported. Differences and refusals remain visible; original receipts and expectations were not changed.\n\n'
    text += '| Pair | Procedure | Variant | Result | Report |\n|---|---|---|---|---|\n'
    for row in rows:
        text += f'| {row["index"]} | {row["id"]} | {row["variant"]} | {row["status"]} | {row["report"]} |\n'
    with (out / 'dated-note.md').open('x', encoding='utf-8') as stream:
        stream.write(text)
    return summary


def offline_guard():
    def refuse(event, args):
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'os.posix_spawn'):
            raise RuntimeError('offline-replay-forbids-network-and-processes')
    sys.addaudithook(refuse)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['fetch', 'replay'])
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--comment-id')
    parser.add_argument('--package-sha256', required=True)
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'CI-only')
    if args.phase == 'fetch':
        fetch(args.input, args.comment_id, args.package_sha256)
        return 0
    require(args.out is not None, 'output-required')
    offline_guard()
    run = args.input / 'verified-revision-9'
    unpack(args.input / export.PACKAGE, args.input / 'export-manifest.json', args.package_sha256, run)
    acquisition = export.decode((args.input / 'acquisition.json').read_bytes())
    require(acquisition['package_sha256'] == args.package_sha256, 'acquisition-binding')
    result = replay(run, args.out, acquisition)
    print(json.dumps(dict(pairs=len(result['pairs']), counts=result['pair_counts'], holds=result['holds_under_pglast_7_20'])))
    return 0 if result['holds_under_pglast_7_20'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
