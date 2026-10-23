"""Collect public metadata/bytes before private generation; no completeness override.

Produces an UNREVIEWED corpus index. An independent closure review must account
for deleted public history and bind the actual agent query boundary before use.
"""
import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from tools.copau_answer_key import sha, encoded, stable_read, no_links, git_bytes, member_name, WORKER_SHA
from tools.copau_private_prerequisites import ROOT, require, load_json

REPO = 'howardweale/lightyear-carddemo-modernization'


def github(path, binary=False):
    result = subprocess.run(['gh', 'api', 'repos/' + REPO + '/' + path],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    require(result.returncode == 0)
    return result.stdout if binary else load_json(result.stdout)


def pages(path, key=None):
    result = []; total = None
    for page in range(1, 10001):
        data = github(path + ('&' if '?' in path else '?') + 'per_page=100&page=' + str(page))
        if key:
            if total is None:total = data['total_count']
            require(data['total_count'] == total)
            rows = data[key]
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


def collect_public(destination):
    require(not destination.exists()); destination.mkdir()
    rows, unavailable, observed = [], [], []
    artifacts = pages('actions/artifacts', 'artifacts')
    assets = []
    for release in pages('releases'):
        if release['draft']:continue
        assets.extend(pages('releases/' + str(int(release['id'])) + '/assets'))
    for kind, records in [('artifact', artifacts), ('release-asset', assets)]:
        for item in records:
            identifier = int(item['id']); public_id = kind + ':' + str(identifier)
            require(public_id not in observed); observed.append(public_id)
            if (item.get('expired') or not str(item.get('digest', '')).startswith('sha256:')
                    or not 0 < item.get('size_in_bytes', item.get('size', 0)) <= 256 * 1024 * 1024):
                unavailable.append(dict(corpus='public', kind=kind, id=identifier)); continue
            try:
                if kind == 'artifact':
                    raw = github('actions/artifacts/' + str(identifier) + '/zip', True)
                else:
                    result = subprocess.run(['gh', 'api', '-H', 'Accept: application/octet-stream',
                        'repos/' + REPO + '/releases/assets/' + str(identifier)], stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, check=False)
                    require(result.returncode == 0); raw = result.stdout
                require(len(raw) <= 256 * 1024 * 1024)
                require(sha(raw) == item['digest'].removeprefix('sha256:'))
                require(len(raw) == item.get('size_in_bytes', item.get('size')))
                name = kind + '-' + str(identifier) + '.bin'
                with (destination / name).open('xb') as stream:stream.write(raw)
                rows.append(dict(path=name, sha256=sha(raw), size_bytes=len(raw), public_id=public_id,
                                 archive=zipfile.is_zipfile(io.BytesIO(raw))))
            except Exception:
                unavailable.append(dict(corpus='public', kind=kind, id=identifier))
    require(len(observed) == len(set(observed)))
    return dict(root=str(destination), files=rows, records=len(rows), observed_ids=observed,
                inventory_sha256=sha(encoded(rows)), inventory_complete=False), unavailable


def build_index(worker, manifest, history, graph, graph_boundary, public):
    bindings = load_json(stable_read(manifest, 2 * 1024 * 1024))
    require(sha(manifest.read_bytes()) == WORKER_SHA and len(bindings) == 403)
    worker_rows = file_rows(worker)
    require({r['path']: r['sha256'] for r in worker_rows} == bindings)
    require(git_bytes(history, 'rev-parse', '--is-shallow-repository').strip() == b'false')
    refs = sorted(git_bytes(history, 'show-ref').splitlines())
    ids = sorted({r.split(b' ', 1)[0] for r in git_bytes(history, 'rev-list', '--objects', '--all').splitlines()})
    graph_rows = file_rows(graph)
    boundary_raw = stable_read(graph_boundary, 2 * 1024 * 1024)
    # An export's presence alone never establishes all agent-queryable content.
    boundary = load_json(boundary_raw)
    require(boundary['schema'] == 'copau-query-boundary/1' and boundary['records'] > 0)
    public_index, unavailable = collect_public(public)
    unavailable.extend([
        dict(corpus='public', kind='unknown-history', id='deleted-artifacts-and-release-assets-unreconciled'),
        dict(corpus='history', kind='unknown-history', id='deleted-public-refs-unreconciled'),
        dict(corpus='graph', kind='graph-snapshot', id='query-boundary-review-pending'),
    ])
    return dict(schema='copau-public-corpus-index/1', captured_at=datetime.now(timezone.utc).isoformat(),
                closure_review=dict(status='unreviewed', reference=''), unavailable=unavailable,
                corpora=dict(worker=dict(root=str(worker), manifest=str(manifest), files=worker_rows),
                             public=public_index,
                             history=dict(root=str(history), refs_sha256=sha(b'\n'.join(refs)+b'\n'),
                                          objects_sha256=sha(b'\n'.join(ids)+b'\n'), object_count=len(ids)),
                             graph=dict(root=str(graph), files=graph_rows, records=boundary['records'],
                                        query_boundary_sha256=sha(boundary_raw), all_queryable_snapshots_included=False,
                                        inventory_sha256=sha(encoded(graph_rows)), inventory_complete=False)))


def main():
    try:
        p = argparse.ArgumentParser(description=__doc__)
        for name in ('worker', 'manifest', 'history', 'graph', 'graph-boundary', 'public-destination', 'out'):
            p.add_argument('--'+name, type=Path, required=True)
        args = p.parse_args()
        roots = [p.resolve() for p in vars(args).values()]
        require(all(ROOT != p and ROOT not in p.parents and p not in ROOT.parents for p in roots))
        require(not args.out.exists())
        output = args.out.resolve()
        require(all(output != p and p not in output.parents for p in
                    (args.worker.resolve(), args.history.resolve(), args.graph.resolve(), args.public_destination.resolve())))
        # Verify this exact repository is public before using authenticated gh GETs.
        result = subprocess.run(['gh', 'api', 'repos/'+REPO], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, check=False)
        require(result.returncode == 0 and load_json(result.stdout)['private'] is False)
        index = build_index(args.worker.resolve(), args.manifest.resolve(), args.history.resolve(),
                            args.graph.resolve(), args.graph_boundary.resolve(), args.public_destination.resolve())
        raw = encoded(index)
        with args.out.open('xb') as stream:stream.write(raw)
        print(json.dumps(dict(sha256=sha(raw), size_bytes=len(raw), unavailable_count=len(index['unavailable']),
                              reviewed=False, qualified=False)))
        return 0
    except Exception:
        print('REFUSED: preserve collected files. No private generation or automatic retry.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
