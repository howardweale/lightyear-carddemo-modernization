"""Opt-in source-only view over G2; no provider, gate, signer or activation CLI.

The reviewed inventory is an allowlist, never an inference from node kinds.
Build the filtered payload before any G2 index. Runtime admission requires the
signed snapshot to equal that payload; it cannot silently filter after approval.
"""
import copy
import hashlib
import json
import re
from pathlib import PurePosixPath

from .contracts import ContractError
from .graph_tools import encoded

KINDS = frozenset(('source_file', 'cobol_program', 'cobol_paragraph', 'cobol_field',
    'copybook', 'cobol_file_handle', 'jcl_job', 'jcl_step', 'jcl_dd_name',
    'jcl_dd_allocation', 'dataset', 'business_rule'))
RELATIONS = frozenset(('CONTAINS', 'DECLARES', 'CALLS', 'USES_COPYBOOK', 'HAS_FIELD',
    'READS', 'WRITES', 'READS_WRITES', 'EXECUTES', 'HAS_DD', 'ALLOCATES', 'USES_FILE',
    'RESOLVES_TO', 'DEPENDS_ON', 'BINDS', 'HAS_RULE', 'DERIVED_FROM'))
TOOLS = ('graph_search', 'graph_node', 'graph_neighbors', 'graph_references')
RULES = {
    'rule:intcalc:disclosure-rate': '2cba340b18c9b58bd5da058c1e5ac53cd7b851fa5e32d25cc31a9df6edd5175c',
    'rule:intcalc:default-rate': 'a818a88f790d37d6e519bcd79d3431961d5d47c30659c86b4628ecd3b052ebf8',
    'rule:intcalc:monthly-interest': 'c6a210128492076e7cd1252ae1384d5505fd3aa1c6158f09a4a084f179a4f8e2'}
RULE_SOURCE = 'spec/mainframe/public-source/CBACT04C.cbl'
RULE_SOURCE_SHA256 = '5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4'
RULE_LINES = {'rule:intcalc:disclosure-rate': {(210, 213)},
    'rule:intcalc:default-rate': {(415, 459)},
    'rule:intcalc:monthly-interest': {(462, 468), (168, 168)}}
LIMITS = ('rule statements authored with knowledge of prior test results',
    'single program whose full source fits in context; graph effect on large estates not measured',
    'operator review, not independent attestation')
HASH = re.compile('[a-f0-9]{64}')
FIELD_PROPS = frozenset(('picture', 'pic', 'usage', 'length'))


def require(ok, code):
    if not ok:
        raise ContractError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, 'legacy-duplicate-key')
            out[key] = value
        return out
    def number(_):
        raise ContractError('legacy-non-integer')
    require(type(raw) is bytes and len(raw) <= 8*1024*1024, 'legacy-json-size')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                          parse_float=number, parse_constant=number)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError('legacy-json') from None


def safe_id(value):
    return (type(value) is str and 0 < len(value) <= 256 and
            (value.startswith('legacy:') or value in RULES) and
            not re.search(r'(?i)(?:^|[:/_-])(?:modern|scenario|test)(?:[:/_-]|$)', value))


def path_ok(value):
    return (type(value) is str and '\\' not in value and ':' not in value and
            not value.startswith('/') and all(x not in ('', '.', '..') for x in value.split('/'))
            and PurePosixPath(value).suffix.lower() in ('.cbl', '.cob', '.cpy', '.jcl', '.prc'))


def fields(obj, names, code):
    require(type(obj) is dict and set(obj) == set(names.split()), code)


def reviewed_inventory(raw, public_sources):
    """Public sources are exact bytes supplied by the trusted read manifest owner."""
    inv = strict(raw)
    fields(inv, 'schema customer_id lane_sha256 sources nodes edges', 'legacy-inventory-fields')
    require(inv['schema'] == 'factory-legacy-inventory/1' and
            inv['customer_id'] == 'carddemo-reference' and
            type(inv['lane_sha256']) is str and HASH.fullmatch(inv['lane_sha256']), 'legacy-inventory')
    require(type(inv['sources']) is dict and inv['sources'] and
            type(public_sources) is dict and set(public_sources) == set(inv['sources']), 'legacy-source-set')
    total = 0
    for path, expected in inv['sources'].items():
        data = public_sources[path]
        require(path_ok(path) and type(expected) is str and HASH.fullmatch(expected)
                and type(data) is bytes and sha(data) == expected, 'legacy-source-hash')
        total += len(data)
        require(total <= 2*1024*1024, 'legacy-source-size')
        try:
            data.decode('utf-8')
        except UnicodeError:
            raise ContractError('legacy-source-utf8') from None
    require(type(inv['nodes']) is list and len(inv['nodes']) <= 10000 and
            type(inv['edges']) is list and len(inv['edges']) <= 40000, 'legacy-inventory-size')
    nodes = {}
    for row in inv['nodes']:
        fields(row, 'id kind name properties anchors dependencies', 'legacy-node-fields')
        require(safe_id(row['id']) and row['id'] not in nodes and type(row['kind']) is str and row['kind'] in KINDS
                and type(row['name']) is str and 0 < len(row['name']) <= 256, 'legacy-node-id')
        props = row['properties']
        allowed = FIELD_PROPS if row['kind'] == 'cobol_field' else frozenset()
        if row['kind'] == 'business_rule':
            allowed = frozenset(('statement',))
            require(row['id'] in RULES and type(props) is dict and
                    type(props.get('statement')) is str and
                    sha(props['statement'].encode('utf-8')) == RULES[row['id']], 'legacy-rule-text')
        require(type(props) is dict and set(props) <= allowed and
                all(type(v) in (str, int) for v in props.values()), 'legacy-properties')
        require(type(row['anchors']) is list and 0 < len(row['anchors']) <= 32 and
                type(row['dependencies']) is list and len(row['dependencies']) <= 64 and
                all(safe_id(v) for v in row['dependencies']), 'legacy-provenance')
        for a in row['anchors']:
            fields(a, 'path line_start line_end excerpt_sha256', 'legacy-anchor-fields')
            require(type(a['path']) is str and a['path'] in public_sources and type(a['line_start']) is int
                    and type(a['line_end']) is int and 1 <= a['line_start'] <= a['line_end'], 'legacy-anchor')
            lines = public_sources[a['path']].splitlines(keepends=True)
            require(a['line_end'] <= len(lines) and sha(b''.join(
                lines[a['line_start']-1:a['line_end']])) == a['excerpt_sha256'], 'legacy-anchor-hash')
        if row['kind'] == 'business_rule':
            require(inv['sources'].get(RULE_SOURCE) == RULE_SOURCE_SHA256 and
                    all(a['path'] == RULE_SOURCE for a in row['anchors']) and
                    {(a['line_start'], a['line_end']) for a in row['anchors']} == RULE_LINES[row['id']],
                    'legacy-rule-source-binding')
        nodes[row['id']] = row
    edges = {}
    for e in inv['edges']:
        fields(e, 'id source target relation', 'legacy-edge-fields')
        require(type(e['id']) is str and e['id'] not in edges and len(e['id']) <= 256 and
                type(e['source']) is str and type(e['target']) is str and type(e['relation']) is str and
                e['source'] in nodes and e['target'] in nodes and e['relation'] in RELATIONS,
                'legacy-edge')
        edges[e['id']] = e
    for row in nodes.values():
        require(all(d in nodes for d in row['dependencies']), 'legacy-unknown-provenance')
        if row['kind'] == 'business_rule':
            require(any(e['source'] == row['id'] and e['relation'] == 'DERIVED_FROM'
                        for e in edges.values()), 'legacy-rule-anchor-edge')
    return inv, nodes, edges


def filtered_projection(payload, inventory_raw, public_sources, scanner):
    """Static construction only: scanner must raise on any unsafe disclosed bytes."""
    require(callable(scanner), 'legacy-scanner-required')
    inv, wanted, allowed_edges = reviewed_inventory(inventory_raw, public_sources)
    require(type(payload) is dict and type(payload.get('nodes')) is list and
            type(payload.get('edges')) is list, 'legacy-graph-shape')
    raw = {}
    for n in payload['nodes']:
        require(type(n) is dict and type(n.get('id')) is str and n['id'] not in raw, 'legacy-graph-node')
        raw[n['id']] = n
    dependencies = {}
    for key, row in wanted.items():
        require(key in raw and raw[key].get('kind') == row['kind'] and
                raw[key].get('name') == row['name'], 'legacy-inventory-node-join')
        n = raw[key]
        deps = list(row['dependencies'])
        for obj in (n, n.get('properties', {})):
            require(type(obj) is dict, 'legacy-provenance-shape')
            extra = obj.get('provenance_dependencies', [])
            require(type(extra) is list and all(type(v) is str for v in extra), 'legacy-provenance-shape')
            deps.extend(extra)
        dependencies[key] = deps
    raw_edges = {}
    for e in payload['edges']:
        require(type(e) is dict and type(e.get('id')) is str and e['id'] not in raw_edges and
                type(e.get('source')) is str and type(e.get('target')) is str,
                'legacy-graph-edge')
        raw_edges[e['id']] = e
        if e.get('source') in wanted and e.get('relation') == 'DERIVED_FROM':
            dependencies[e['source']].append(e.get('target'))
    cleaned = set()
    def clean(key, seen):
        require(type(key) is str and key in wanted and key not in seen and len(seen) < 64,
                'legacy-tainted-provenance')
        if key in cleaned:
            return
        for dep in dependencies[key]:
            clean(dep, seen | {key})
        cleaned.add(key)
    for key in wanted:
        clean(key, set())
    nodes = []
    for key, row in sorted(wanted.items()):
        excerpts = []
        for a in row['anchors']:
            lines = public_sources[a['path']].splitlines(keepends=True)
            excerpts.append(dict(path=a['path'], line_start=a['line_start'], line_end=a['line_end'],
                                 text=b''.join(lines[a['line_start']-1:a['line_end']]).decode('utf-8')))
        props = dict(row['properties'], provenance='public-source', visibility='shared',
                     customer_id=inv['customer_id'])
        node = dict(id=key, kind=row['kind'], name=row['name'], properties=props, source=excerpts)
        scanner('legacy-node-'+sha(key.encode()), encoded(node))
        nodes.append(node)
    edges = []
    for key, edge in sorted(allowed_edges.items()):
        require(key in raw_edges and all(raw_edges[key].get(k) == v for k,v in edge.items()),
                'legacy-inventory-edge-join')
        edges.append(copy.deepcopy(edge))
    result = dict(schema='verify-graph-projection/1', lane='INTCALC', mode='field',
        customer_id=inv['customer_id'], lane_sha256=inv['lane_sha256'], nodes=nodes, edges=edges,
        verified_by=[], dataset_copybooks={}, dataset_file_names={})
    scanner('legacy-projection', encoded(result))
    return result


def output_fields(tool, result):
    fields(result, 'projection_sha256 truncated items cursor', 'legacy-result-fields')
    require(type(result['items']) is list, 'legacy-result-items')
    allowed = {
        'graph_search': {'id','kind','name','summary','provenance','item_truncated'},
        'graph_node': {'id','kind','name','properties','source','item_truncated'},
        'graph_neighbors': {'id','kind','name','relation','source','target','direction','item_truncated'},
        'graph_references': {'id','kind','name','line_ranges','provenance','item_truncated'}}[tool]
    out = copy.deepcopy(result)
    for row in out['items']:
        require(type(row) is dict, 'legacy-result-item')
        if tool == 'graph_node':
            # G2 always supplies this field; a filtered view must make it empty.
            require(row.pop('verified_by', []) == [], 'legacy-verification-link')
        require(set(row) <= allowed and safe_id(row.get('id')), 'legacy-result-allowlist')
    return out


class LegacyGraphSession:
    """G2 approved loader, index, cursors and four read methods; no new endpoint.

    Trusted configuration binds profile/inventory hashes. It is not model input.
    The caller retains transcript and run-wide accounting in later slices.
    """
    def __init__(self, approved, inventory_raw, public_sources, profile_raw,
                 scanner, workspace, expected_projection_sha256):
        from lightyear_toolkit.graph import GraphTools
        from lightyear_toolkit.graph_approval import load_approved
        profile = strict(profile_raw)
        fields(profile, 'schema inventory_sha256 rule_hashes', 'legacy-profile-fields')
        require(profile['schema'] == 'factory-legacy-profile/1' and
                profile['inventory_sha256'] == sha(inventory_raw) and profile['rule_hashes'] == RULES,
                'legacy-profile-binding')
        trust = approved[2]
        require(trust.get('legacy_profile_sha256') == sha(profile_raw) and
                trust.get('legacy_inventory_sha256') == sha(inventory_raw), 'legacy-trust-binding')
        payload, manifest, decision = load_approved(*approved)
        require(manifest['projection_sha256'] == expected_projection_sha256 and
                manifest['policy_sha256'] == sha(profile_raw), 'legacy-snapshot-binding')
        clean = filtered_projection(payload, inventory_raw, public_sources, scanner)
        require(encoded(clean) == encoded(payload), 'legacy-approved-payload-not-filtered')
        self._tools = GraphTools(clean, manifest, decision, workspace, None, cap=7168)
        self._scanner = scanner
        self._failed = False
        self._count = 0
        self._phase_counts = {}
        self._dispatch = {'graph_search': self._tools._graph_search,
            'graph_node': self._tools._graph_node, 'graph_neighbors': self._tools._graph_neighbors,
            'graph_references': self._tools._graph_references}
        self.projection_sha256 = expected_projection_sha256
        self.inventory_sha256 = sha(inventory_raw)

    def call(self, role, phase, tool, arguments):
        require(not self._failed and type(role) is str and type(tool) is str and
                role in ('planner','builder') and tool in TOOLS,
                'legacy-tool-forbidden')
        require(type(phase) is int and (phase == 0 if role == 'planner' else 0 <= phase <= 5),
                'legacy-phase')
        key = (role, phase)
        cap = 8 if role == 'planner' else 3
        require(self._count < 26 and self._phase_counts.get(key,0) < cap, 'legacy-call-budget')
        require(type(arguments) is dict and len(encoded(arguments)) <= 1024, 'legacy-argument-cap')
        common = {'graph_search': {'query','kind','limit','cursor'},
            'graph_node': {'node_id','include_source'},
            'graph_neighbors': {'node_id','relations','direction','depth','limit','cursor'},
            'graph_references': {'node_id','cursor'}}
        require(set(arguments) <= common[tool], 'legacy-argument-fields')
        if 'include_source' in arguments:
            require(type(arguments['include_source']) is bool, 'legacy-include-source')
        if 'cursor' in arguments:
            require(type(arguments['cursor']) is str and len(arguments['cursor']) <= 512, 'legacy-cursor')
        if 'node_id' in arguments:
            require(type(arguments['node_id']) is str and arguments['node_id'] in self._tools.index.node_by_id,
                    'legacy-node-unavailable')
        if tool != 'graph_search':
            require('node_id' in arguments, 'legacy-node-required')
        if 'kind' in arguments:
            require(type(arguments['kind']) is str and
                    (arguments['kind'] in KINDS or arguments['kind']==''), 'legacy-kind')
        if 'limit' in arguments:
            require(type(arguments['limit']) is int and 1 <= arguments['limit'] <= 10, 'legacy-limit')
        if 'depth' in arguments:
            require(type(arguments['depth']) is int and arguments['depth']==1, 'legacy-depth')
        if 'relations' in arguments:
            require(type(arguments['relations']) is list and all(type(x) is str and x in RELATIONS for x in arguments['relations']),
                    'legacy-relations')
        if tool == 'graph_search':
            require(type(arguments.get('query')) is str and len(arguments['query']) <= 512, 'legacy-query')
        require(self._tools.active(), 'legacy-approval-expired')
        self._count += 1
        self._phase_counts[key] = self._phase_counts.get(key,0)+1
        try:
            self._scanner('legacy-arguments', encoded(arguments))
            result = self._dispatch[tool](**arguments)
            self._scanner('legacy-raw-result', encoded(result))
            result = output_fields(tool, result)
            require(len(encoded(result)) <= 7168, 'legacy-response-cap')
            self._scanner('legacy-result', encoded(result))
            require(self._tools.active(), 'legacy-approval-expired')
            return result
        except BaseException:
            self._failed = True
            raise
