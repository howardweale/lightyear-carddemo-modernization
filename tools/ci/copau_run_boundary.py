"""CI-only public corpus assembly from F2 bindings and controller packing code."""
import argparse
import ast
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from urllib.request import urlopen

from lightyear_factory.contracts import WorkOrder
from lightyear_factory.context import GraphContextAssembler
from lightyear_factory.copau_boundary import DISABLED_GRAPH, SETTINGS, encoded, digest, require
from tools.copau_public_corpus_index import file_rows, github, historical_metadata, inventory_digest

WORKER = 'docs/factory/copau-f8-workspace-manifest-2026-10-21.json'
WORKER_SHA = 'bb11b3644a6070d7176767d82826d451e0b5055a6ce3e5eda0495c45591b0771'
REQUEST = 'docs/factory/copau-f2-preparation-2026-10-22/request.json'
RETENTION = 'docs/factory/copau-f8-release-receipt-2026-10-21.json'
# Explicit call-path inventory, not a filesystem discovery of plausible templates.
# Complete source bytes conservatively retain even unused literal branches.
PROMPT_SOURCES = ('src/lightyear_factory/agents.py', 'src/lightyear_factory/providers.py',
                  'src/lightyear_factory/model_config.py', 'src/lightyear_factory/routing.py')
CONTEXT_SOURCES = ('src/lightyear_factory/context.py', 'src/lightyear_factory/gates.py',
                   'src/lightyear_factory/orchestrator.py', 'src/lightyear_factory/contracts.py',
                   'src/lightyear_factory/workspace.py', 'src/lightyear_factory/graph_tools.py')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)


def public_asset(row):
    prefix = 'https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/'
    require(row['url'].startswith(prefix) and 0 < row['bytes'] <= 16 * 1024 * 1024)
    with urlopen(row['url'], timeout=60) as stream:
        raw = stream.read(row['bytes'] + 1)
    require(len(raw) == row['bytes'] and digest(raw) == row['sha256'])
    return raw


def assemble_worker(repo, main, output):
    manifest_raw = git(repo, 'show', main + ':' + WORKER)
    require(digest(manifest_raw) == WORKER_SHA)
    manifest = json.loads(manifest_raw)
    require(len(manifest) == 403)
    retained = json.loads(git(repo, 'show', main + ':' + RETENTION))
    assets = {a['name']: a for a in retained['assets']}
    capsule = public_asset(assets['capsule.tar.gz'])
    capsule_map = json.loads(public_asset(assets['capsule-files.json']))
    require(len(capsule_map) == 380)
    # Only these two assets are operational run inputs. Other historical payloads
    # remain uninspected. Validate every member before materializing public bytes.
    with gzip.GzipFile(fileobj=io.BytesIO(capsule)) as stream:
        tar = stream.read(40 * 1024 * 1024 + 1)
    require(len(tar) <= 40 * 1024 * 1024)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(tar), mode='r:') as archive:
        for member in archive:
            name = member.name
            require(member.isfile() and not member.sparse and name in capsule_map
                    and name not in files and member.size <= 8 * 1024 * 1024
                    and not name.startswith('/') and ':' not in name and '\\' not in name
                    and not any(x in ('', '.', '..') for x in name.split('/')))
            raw = archive.extractfile(member).read(member.size + 1)
            require(len(raw) == member.size and digest(raw) == capsule_map[name])
            files[name] = raw
    require(set(files) == set(capsule_map))
    worker = output/'worker'
    for name, sha in sorted(manifest.items()):
        prefix = 'work/f8-public-worker-capsule/'
        raw = files[name[len(prefix):]] if name.startswith(prefix) else git(
            repo, 'show', retained['source_head'] + ':' + name)
        require(digest(raw) == sha)
        write(worker/name, raw)
    require({r['path']: r['sha256'] for r in file_rows(worker)} == manifest)
    write(output/'workspace-manifest.json', manifest_raw)
    return worker, manifest


def template_inventory(repo, main, paths, root):
    records = []
    for path in paths:
        raw = git(repo, 'show', main + ':' + path)
        # Execute the same packing code whose source is indexed, never silently
        # mix a candidate's changed packer with main's source binding.
        require((repo/path).read_bytes() == raw)
        write(root/path, raw)
        tree = ast.parse(raw.decode('utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                literals = [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                if literals:
                    records.append(dict(path=path, function=node.name, line=node.lineno,
                        end_line=node.end_lineno, string_literals=len(literals), source_sha256=digest(raw)))
    require(records)
    return records


def collect(repo, output):
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and not output.exists())
    require(github('')['private'] is False)
    main = github('git/ref/heads/main')['object']['sha']
    # Fetch exact public objects only; no checkout or branch changes.
    subprocess.check_call(['git', '-C', str(repo), 'fetch', '--no-tags', 'origin', main])
    output.mkdir(parents=True)
    request = json.loads(git(repo, 'show', main + ':' + REQUEST))
    require(request['bindings']['workspace']['sha256'] == WORKER_SHA)
    require(request['work_order']['metadata']['retrieval'] == 'packed-context-no-tools')
    order = WorkOrder.from_dict(request['work_order'])
    require(not order.graph_node_ids and order.metadata.get('graph', 'packed') == 'packed')
    retained = json.loads(git(repo, 'show', main + ':' + RETENTION))
    subprocess.check_call(['git', '-C', str(repo), 'fetch', '--no-tags', 'origin', retained['source_head']])
    worker, manifest = assemble_worker(repo, main, output)
    graph = output/'graph'
    write(graph/'disabled.json', encoded(DISABLED_GRAPH))
    prompts, contexts = output/'prompts', output/'contexts'
    prompt_records = template_inventory(repo, main, PROMPT_SOURCES, prompts)
    context_records = template_inventory(repo, main, CONTEXT_SOURCES, contexts)
    # Include the complete public order and all worker bytes conservatively.
    # Current allowed_paths is a directory: the present packer only includes
    # regular-file paths. Record that actual result rather than invent excerpts.
    write(contexts/'work-order.json', encoded(order.to_dict()))
    for path in manifest:
        write(contexts/'worker-inputs'/path, (worker/path).read_bytes())
    context = GraphContextAssembler(None, None).assemble(order, worker)
    require(context['nodes'] == context['edges'] == context['source_excerpts'] == [])
    require(context['semantic_memory'] is None)
    write(contexts/'packed-context.json', encoded(context))
    planner = GraphContextAssembler.planner_context(context)
    builder = GraphContextAssembler.builder_context(context, [], [])
    write(contexts/'planner-context.json', encoded(planner))
    write(contexts/'builder-context.json', encoded(builder))
    historical = historical_metadata()
    rows = {name: file_rows(output/name) for name in ('graph', 'prompts', 'contexts')}
    boundary = dict(schema='copau-run-visible-boundary/1', prepared_on='2026-10-24',
        main_commit=main, work_order_sha256=order.content_sha256,
        launch_settings=SETTINGS, launch_settings_sha256=digest(encoded(SETTINGS)),
        graph_declaration=DISABLED_GRAPH,
        worker=dict(files=403, manifest_path=WORKER, manifest_sha256=WORKER_SHA,
                    inventory_sha256=inventory_digest(file_rows(worker)),
                    deciding_code='FactoryModelAdmission.verify_runtime -> IsolatedWorkspace._create_allowlisted'),
        surfaces=dict(
            graph=dict(status='disabled', records=0, exception='copau-empty-graph-2026-10-24',
                declaration_sha256=digest(encoded(DISABLED_GRAPH)), inventory_sha256=inventory_digest(rows['graph']),
                deciding_code='copau_boundary.enforce passes graph/evidence None; graph_policy packed gives zero tool budget'),
            prompts=dict(records=len(prompt_records), inventory_sha256=inventory_digest(rows['prompts']),
                templates=prompt_records, deciding_code='ModelAgentSet.plan/build/analyze_failure -> _call_once -> provider.complete'),
            contexts=dict(records=len(context_records)+407, inventory_sha256=inventory_digest(rows['contexts']),
                templates=context_records, worker_input_files=403, order_records=1, rendered_records=3,
                deciding_code='FactoryOrchestrator._context -> GraphContextAssembler.assemble/planner_context/builder_context; gates.builder_failure_view; ModelAgentSet payloads')),
        historical=historical,
        operational_release_inputs=[assets for assets in retained['assets'] if assets['name'] in ('capsule.tar.gz','capsule-files.json')],
        approval=dict(status='unreviewed', invalidated_by=['main','graph','templates','workspace','launch_settings']),
        gaps=['Final concrete signed F2 WorkOrder/plan must bind this boundary and launch-settings hash after the approved P5 merge.',
              'Model-generated plans, edits and sanitized failure payloads are dynamic; their packer source/schema is indexed and runtime isolation scanning remains required.',
              'Current allowed_paths is a directory; the current packer exposes zero allowed-file excerpts. All 403 workspace files are included conservatively in this public context surface.'],
        request_ready=False, run_authorized=False)
    require(len(encoded(boundary)) <= 2 * 1024 * 1024)
    write(output/'boundary.json', encoded(boundary))
    # Required collector invocation is a separate CI process, public inputs only.
    subprocess.check_call([os.sys.executable, '-B', 'tools/copau_public_corpus_index.py',
        '--worker', str(worker), '--manifest', str(output/'workspace-manifest.json'),
        '--repository', str(repo), '--graph', str(graph), '--prompts', str(prompts),
        '--contexts', str(contexts), '--run-boundary', str(output/'boundary.json'),
        '--out', str(output/'index.json')], cwd=repo)
    index = json.loads((output/'index.json').read_bytes())
    require(index['closure_review']['status'] == 'unreviewed')
    require(github('git/ref/heads/main')['object']['sha'] == main)
    receipt = dict(schema='copau-public-boundary-receipt/1', main_commit=main,
        boundary_sha256=digest((output/'boundary.json').read_bytes()),
        index_sha256=digest((output/'index.json').read_bytes()),
        surfaces={name: dict(files=len(row['files']), records=row['records'], inventory_sha256=row['inventory_sha256'])
                  for name,row in index['corpora'].items() if name != 'main'},
        run_url='https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/'+os.environ['GITHUB_RUN_ID'],
        reviewed=False, gaps=boundary['gaps'], request_ready=False)
    write(output/'receipt.json', encoded(receipt))
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    collect(Path.cwd().resolve(), args.out.resolve())
