"""Re-checkable E3.1 byte def-use on explicitly validated complete CFGs.

This module does not certify a parser or decide a real mutant's equivalence.
The pipeline must supply differential acceptance and all-killed rejection gates
before using a certificate as resolution authority.
"""
from .equivalence_automation import sealed, verify, digest


def cells(spans):
    result = set()
    for span in spans:
        if set(span) != {'area', 'offset', 'length'} or not isinstance(span['area'], str):
            raise ValueError('invalid-byte-span')
        if (type(span['offset']) is not int or type(span['length']) is not int
                or span['offset'] < 0 or not 0 < span['length'] <= 32760):
            raise ValueError('invalid-byte-span')
        result.update((span['area'], n) for n in range(span['offset'], span['offset']+span['length']))
    return result


def graph(cfg):
    verify(cfg)
    if cfg.get('unsupported') or cfg.get('complete') is not True:
        raise ValueError('complete-effect-CFG-required')
    nodes = {n['id']: n for n in cfg['nodes']}
    if len(nodes) != len(cfg['nodes']) or not nodes:
        raise ValueError('duplicate-or-empty-CFG')
    for n in nodes.values():
        if set(n) != {'id', 'reads', 'writes', 'successors', 'observable', 'branch', 'effect_order'}:
            raise ValueError('closed-CFG-node-required')
        if n['effect_order'] != 'reads-before-writes':
            raise ValueError('unsupported-effect-order')
        if type(n['observable']) is not bool or type(n['branch']) is not bool:
            raise ValueError('invalid-CFG-effect-flags')
        if any(s not in nodes for s in n['successors']):
            raise ValueError('unbound-CFG-edge')
        cells(n['reads']); cells(n['writes'])
    return nodes


def dead_store(cfg, starts, changed_bytes, *, max_states=10000):
    """All paths overwrite every changed byte before any read of that byte.

    Partial overwrites and aliases are byte sets. A branch reading the value,
    unknown effects, exit with live bytes, or a non-progressing cycle refuses.
    """
    nodes = graph(cfg); changed = frozenset(cells(changed_bytes))
    if not starts or not changed or any(s not in nodes for s in starts):
        raise ValueError('dead-store-start-or-span')
    memo = {}; active = set(); trace = []

    def visit(node_id, remaining):
        if not remaining:
            return True
        key = node_id, remaining
        if key in active:
            return False
        if key in memo:
            return memo[key]
        if len(memo) + len(active) >= max_states:
            raise ValueError('def-use-state-budget')
        active.add(key)
        node = nodes[node_id]
        if cells(node['reads']) & remaining:
            result = False
        else:
            next_bytes = remaining - cells(node['writes'])
            result = not next_bytes or bool(node['successors']) and all(
                visit(s, next_bytes) for s in sorted(node['successors']))
        active.remove(key); memo[key] = result
        trace.append(dict(node=node_id, live_bytes=[list(c) for c in sorted(remaining)], overwritten_before_read=result))
        return result

    proven = all(visit(s, changed) for s in sorted(starts))
    return sealed(dict(schema='byte-dead-store-certificate/1', cfg_sha256=cfg['content_sha256'],
        starts=sorted(starts), changed_bytes=changed_bytes, overwritten_on_every_path=proven,
        states=trace, max_states=max_states, resolution_authorized=False,
        acceptance_requires=['whole-program differential gate', 'all-killed-mutants rejection check']))


def recheck_dead_store(cfg, certificate):
    verify(certificate)
    actual = dead_store(cfg, certificate['starts'], certificate['changed_bytes'],
                        max_states=certificate['max_states'])
    if digest(actual) != digest(certificate):
        raise ValueError('dead-store-certificate-mismatch')
    return actual['overwritten_on_every_path']


def output_relevance(cfg):
    """May dependency fixpoint. Outputs AND branch reads are observation sinks."""
    nodes = graph(cfg); relevant = set()
    for n in nodes.values():
        if n['observable'] or n['branch']:
            relevant.update(cells(n['reads']))
    iterations = 0
    while True:
        before = set(relevant)
        for n in nodes.values():
            if cells(n['writes']) & relevant:
                relevant.update(cells(n['reads']))
        iterations += 1
        if relevant == before:
            break
    return sealed(dict(schema='byte-output-relevance/1', cfg_sha256=cfg['content_sha256'],
        relevant_bytes=[list(c) for c in sorted(relevant)], iterations=iterations,
        absent_classification='unobservable; not equivalent; retain denominator', resolution_authorized=False))
