"""Fail-closed first-COPAU launch boundary. No signing, secrets or transport."""
import hashlib
import json
from pathlib import Path
import re

from .contracts import ContractError, canonical_hash

ORDER_ID = 'copau-first-factory-run-2026-10-30'
SETTINGS = dict(graph='none', memory='disabled', context='packed')
DISABLED_GRAPH = dict(schema='copau-disabled-graph/1', scope='first-copau-run',
                      status='disabled', nodes=0, edges=0, tool_calls=0)
FORBIDDEN_OPTIONS = frozenset(('--graph', '--evidence-pack', '--approved-projection',
                             '--memory-root', '--memory-policy', '--disable-memory'))


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition):
    if not condition:
        raise ContractError('copau-run-visible-boundary-refused')


def disabled_graph(row, declaration):
    """Zero data records are permitted only for this explicit dated exception."""
    require(row.get('status') == 'disabled' and type(row.get('records')) is int and row['records'] == 0)
    require(row.get('exception') == 'copau-empty-graph-2026-10-24')
    require(declaration == DISABLED_GRAPH and row.get('declaration_sha256') == digest(encoded(declaration)))


def validate_launch(order, options, boundary):
    require(order.order_id == ORDER_ID)
    supplied = {item.split('=', 1)[0] for item in options if item.startswith('--')}
    require(not any(option.startswith(item) for item in supplied for option in FORBIDDEN_OPTIONS))
    require(not order.graph_node_ids and order.metadata.get('graph', 'packed') == 'packed')
    require(not order.metadata.get('graph_policy') and order.metadata.get('context_schema', '1.0') == '1.0')
    require(not any(key in order.metadata for key in ('semantic_memory', 'memory', 'memory_policy', 'approved_projection')))
    require(boundary.get('schema') == 'copau-run-visible-boundary/1')
    require(boundary.get('launch_settings') == SETTINGS)
    require(boundary.get('launch_settings_sha256') == digest(encoded(SETTINGS)))
    require(re.fullmatch('[0-9a-f]{40}', boundary.get('main_commit', '')) is not None)
    require(boundary.get('work_order_sha256') == order.content_sha256)
    require(set(boundary.get('surfaces', {})) == {'graph', 'prompts', 'contexts'})
    disabled_graph(boundary['surfaces']['graph'], boundary.get('graph_declaration'))


def enforce(args, order, options, admission):
    """Called after HMAC verification, before F2 preflight/nonce/credentials.

The signed F2 plan must bind the exact boundary and launch settings. A public
unreviewed collection alone never authorizes a launch or changes readiness.
"""
    if getattr(order, 'order_id', None) != ORDER_ID:
        require(getattr(args, 'factory_run_boundary', None) is None)
        return
    try:
        path = args.factory_run_boundary
        require(path is not None and admission is not None)
        root = args.source_root.resolve()
        path = Path(path)
        path = path if path.is_absolute() else root/path
        require(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)())
        relative = path.resolve(strict=True).relative_to(root).as_posix()
        # The existing bounded committed-JSON reader checks exact Git bytes.
        boundary = admission._committed_json(relative)
        raw = path.read_bytes()
        require(len(raw) <= 2 * 1024 * 1024 and json.loads(raw) == boundary)
        validate_launch(order, options, boundary)
        admitted = admission.verify_plan(order)
        plan = admission._committed_json(admission.paths[0])
        require(canonical_hash(plan, {'content_sha256'}) == admitted['plan_sha256'])
        expected = dict(path=relative, sha256=digest(raw),
                        launch_settings_sha256=boundary['launch_settings_sha256'],
                        main_commit=boundary['main_commit'])
        require(plan.get('run_visible_boundary') == expected)
        require(plan.get('executable_commit') == boundary['main_commit'])
        # None is passed directly to the controller; no sentinel filename can be
        # replaced with a graph. Explicit user overrides were already refused.
        args.graph = None
        args.evidence_pack = None
        args.approved_projection = None
        args.disable_memory = True
    except Exception:
        raise ContractError('copau-run-visible-boundary-refused') from None
