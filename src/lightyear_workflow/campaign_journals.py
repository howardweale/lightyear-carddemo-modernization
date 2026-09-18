"""Bounded family journals anchored by signed parent checkpoints."""
from .run_store import RunStore
from lightyear_control_tower.decisions import verify_envelope
from lightyear_data.contracts import content_hash


def signed_append(store, signer, auth, kind, payload, journal_id):
    previous = store.events()
    body = signer.sign({**payload, 'run_id': auth['run_id'], 'plan_sha256': auth['plan']['plan_sha256'],
                        'journal_id': journal_id, 'event_type': kind,
                        'previous_event_sha256': previous[-1]['content_sha256'] if previous else None})
    return store.append(kind, body)


def check(events, auth, key, journal_id=None):
    for event in events:
        body = event['payload']
        if (not verify_envelope(body, key) or body.get('run_id') != auth['run_id']
                or body.get('plan_sha256') != auth['plan']['plan_sha256']
                or body.get('event_type') != event['type']
                or body.get('previous_event_sha256') != event['previous_sha256']
                or (journal_id is not None and body.get('journal_id') != journal_id)):
            raise ValueError('Campaign event signature, scope or chain invalid')
    return events


def read(directory, auth, key):
    parent = RunStore(directory, read_only=True).events()
    def load(topic):
        path = directory / 'families' / topic
        if any(p.is_symlink() for p in (path, path.parent, path / 'events.sqlite3')):
            raise ValueError('Symbolic family journal')
        return RunStore(path, read_only=True).events()
    return assemble(parent, load, auth, key)


def exported(events, auth, key):
    """Verify JSON exports with exactly the same per-journal bounds as SQLite."""
    grouped = {}
    for event in events:
        journal = event['payload'].get('journal_id', 'campaign')
        grouped.setdefault(journal, []).append(event)
    permitted = {'campaign', *auth['plan'].get('families', [])}
    if set(grouped) - permitted:
        raise ValueError('Unknown exported journal')
    for group in grouped.values():
        previous = None
        if len(group) > 256:
            raise ValueError('Export exceeds bounded journal size')
        for sequence, event in enumerate(group, 1):
            if event['sequence'] != sequence or event['previous_sha256'] != previous or event['content_sha256'] != content_hash(event):
                raise ValueError('Export journal integrity check failed')
            previous = event['content_sha256']
    value = assemble(grouped.get('campaign', []), lambda topic: grouped.get(topic, []), auth, key)
    if value != events:
        raise ValueError('Export event order differs from parent/family checkpoints')
    return value


def assemble(parent, load, auth, key):
    if auth['plan'].get('journal_layout') != 'family-v1':
        return check(parent, auth, key)
    check(parent, auth, key, 'campaign')
    families = auth['plan']['families']
    # Family identifiers are a fixed allowlist, never filesystem paths from input.
    from .paired_types import FAMILIES
    if families != list(FAMILIES):
        raise ValueError('Unknown family journal scope')
    opened, active, output = [], None, []

    def children(topic, checkpoint=None):
        events = check(load(topic), auth, key, topic)
        allowed = {c['id'] for c in auth['plan']['cases'] if c['family'] == topic}
        if len(events) > 3 * len(allowed):
            raise ValueError('Family exceeds its observation/comparison bound')
        for event in events:
            p = event['payload']
            if event['type'] not in ('observation', 'comparison'):
                raise ValueError('Non-case event in family journal')
            case_id = p.get('case_id') if event['type'] == 'observation' else p['comparison']['case_id']
            if case_id not in allowed or p.get('family') != topic:
                raise ValueError('Cross-family observation')
        if checkpoint is not None:
            if not events or checkpoint['journal_head_sha256'] != events[-1]['content_sha256'] or checkpoint['event_count'] != len(events):
                raise ValueError('Family journal missing, pruned or differs from signed checkpoint')
        return events

    for event in parent:
        kind, p = event['type'], event['payload']
        if kind == 'family-start':
            topic = p['family']
            if active or len(opened) >= len(families) or topic != families[len(opened)]:
                raise ValueError('Family order/ownership differs from authorization')
            opened.append(topic)
            active = topic
        elif kind == 'family-finished':
            if active != p['family']:
                raise ValueError('Family checkpoint without active family')
            output.extend(children(active, p))
            active = None
        elif kind in ('observation', 'comparison'):
            raise ValueError('Case event outside family journal')
        elif kind in ('error', 'cleanup', 'terminal') and active:
            output.extend(children(active))
            active = None
        output.append(event)
    if active:
        output.extend(children(active))
    return output
