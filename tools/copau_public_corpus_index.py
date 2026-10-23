"""Inventory exact run surfaces before private generation; historical metadata only.

Output needs independent review of the run-visible graph and prompt/context
boundary. Historical bytes are not downloaded and their absence is not a gate.
"""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from tools.copau_answer_key import sha, encoded, stable_read, no_links, git_bytes, member_name, WORKER_SHA, HISTORICAL
from tools.copau_private_prerequisites import ROOT, require, load_json

REPO = 'howardweale/lightyear-carddemo-modernization'


def github(path):
    result = subprocess.run(['gh', 'api', 'repos/' + REPO + '/' + path],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    require(result.returncode == 0)
    return load_json(result.stdout)


def pages(path, key=None):
    result = []; total = None
    for page in range(1, 10001):
        data = github(path + ('&' if '?' in path else '?') + 'per_page=100&page=' + str(page))
        if key:
            if total is None:total = data['total_count']
            require(data['total_count'] == total); rows = data[key]
        else:rows = data
        result.extend(rows)
        if len(rows) < 100:
            require(total is None or len(result) == total)
            return result
    raise ValueError('pagination limit')


def file_rows(root):
    require(root.is_absolute()); no_links(root)
    rows = []
    for path in sorted(root.rglob('*')):
        no_links(path)
        if not path.is_file():continue
        raw = stable_read(path, 256 * 1024 * 1024)
        relative = path.relative_to(root).as_posix(); member_name(relative)
        rows.append(dict(path=relative, sha256=sha(raw), size_bytes=len(raw),
                         archive=zipfile.is_zipfile(io.BytesIO(raw))))
    require(rows)
    return rows


def historical_metadata():
    observed, missing, errors = [], [], 0
    try:
        for item in pages('actions/artifacts', 'artifacts'):
            identifier = int(item['id']); observed.append(dict(kind='artifact', id=identifier))
            if item.get('expired'):missing.append(dict(kind='artifact', id=identifier))
    except Exception:
        errors += 1; missing.append(dict(kind='unknown-history', id='artifact-catalog-unavailable'))
    try:
        for release in pages('releases'):
            if release['draft']:continue
            for item in pages('releases/' + str(int(release['id'])) + '/assets'):
                observed.append(dict(kind='release-asset', id=int(item['id'])))
    except Exception:
        errors += 1; missing.append(dict(kind='unknown-history', id='release-catalog-unavailable'))
    # Current APIs cannot enumerate deleted objects. Disclose that limitation;
    # no historical archive bytes or prior commit blobs are read for qualification.
    missing.append(dict(kind='unknown-history', id='deleted-artifacts-assets-and-prior-history-not-enumerated'))
    return dict(status=HISTORICAL, catalog_sha256=sha(encoded(observed)), observed_count=len(observed),
                missing=missing, metadata_error_count=errors)


def build_index(worker, manifest, repository, graph, prompts, contexts, run_boundary):
    raw = stable_read(manifest, 2 * 1024 * 1024); bindings = load_json(raw)
    require(sha(raw) == WORKER_SHA and len(bindings) == 403)
    worker_rows = file_rows(worker)
    require({r['path']: r['sha256'] for r in worker_rows} == bindings)
    boundary_raw = stable_read(run_boundary, 2 * 1024 * 1024); boundary = load_json(boundary_raw)
    require(boundary['schema'] == 'copau-run-visible-boundary/1'
            and set(boundary['surfaces']) == {'graph', 'prompts', 'contexts'})
    corpora = dict(worker=dict(root=str(worker), manifest=str(manifest), files=worker_rows,
        records=403, inventory_sha256=sha(encoded(worker_rows)), inventory_complete=True))
    for name, root in [('graph', graph), ('prompts', prompts), ('contexts', contexts)]:
        rows = file_rows(root); expected = boundary['surfaces'][name]
        # Review must establish closure, not just presence of an export directory.
        require(expected['inventory_sha256'] == sha(encoded(rows)) and expected['records'] > 0)
        corpora[name] = dict(root=str(root), files=rows, records=expected['records'],
            inventory_sha256=sha(encoded(rows)), inventory_complete=False,
            run_binding_sha256=sha(boundary_raw), all_run_visible_content_included=False)
    commit = github('git/ref/heads/main')['object']['sha']
    listing = git_bytes(repository, 'ls-tree', '-rz', '--full-tree', commit)
    require(listing)
    corpora['main'] = dict(root=str(repository), commit=commit, tree_listing_sha256=sha(listing))
    return dict(schema='copau-run-surface-index/2', captured_at=datetime.now(timezone.utc).isoformat(),
                closure_review=dict(status='unreviewed', reference=''), unavailable=[],
                historical=historical_metadata(), corpora=corpora)


def main():
    try:
        p = argparse.ArgumentParser(description=__doc__)
        for name in ('worker', 'manifest', 'repository', 'graph', 'prompts', 'contexts', 'run-boundary', 'out'):
            p.add_argument('--'+name, type=Path, required=True)
        args = p.parse_args()
        roots = [x.resolve() for x in vars(args).values()]
        require(all(ROOT != x and ROOT not in x.parents and x not in ROOT.parents for x in roots))
        require(not args.out.exists()); output = args.out.resolve()
        require(all(output != x and x not in output.parents for x in
                    (args.worker.resolve(), args.repository.resolve(), args.graph.resolve(),
                     args.prompts.resolve(), args.contexts.resolve())))
        require(github('')['private'] is False)
        index = build_index(args.worker.resolve(), args.manifest.resolve(), args.repository.resolve(),
                            args.graph.resolve(), args.prompts.resolve(), args.contexts.resolve(),
                            args.run_boundary.resolve())
        raw = encoded(index)
        with args.out.open('xb') as stream:stream.write(raw)
        print(json.dumps(dict(sha256=sha(raw), size_bytes=len(raw), reviewed=False, qualified=False)))
        return 0
    except Exception:
        print('REFUSED: preserve files. No private generation or automatic retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
