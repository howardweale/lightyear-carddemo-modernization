"""Content supersession for public review intake; never creates authority."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
import re
from .decisions import digest

SUPERSEDED = {'856e8efc25a005c8ba7bbafe9493fde6f7fea0e74915e900632c724cca483c10': 'factory-50bbd415d2da34c3786681ad1ad390d9add581ca17137b2d4f35ecb05fe7a51f', '35ce5a3f754e5b98460544321aaab9919ee70d29b4a81963ee78b997254f492f': 'factory-92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1'}


def reject_superseded(contract):
    if 'superseded_by' in contract or digest(contract) in SUPERSEDED:
        raise ValueError('factory-request-superseded')


def identity(contract):
    if contract.get('kind')!='equivalence-review':return None
    return digest(dict(program=contract['program'],items=sorted(set(contract['details']['items']))))


def normalized_hash(contract):
    value=deepcopy(contract);reference=value.pop('supersession',None)
    if reference:value['sources']=[s for s in value['sources'] if s!=reference]
    if 'signing_order' in value:value['signing_order']['predecessor_decision_sha256']=None
    return digest(value)


def reference_shape(contract):
    reference=contract.get('supersession')
    if reference is None:return
    if (contract.get('kind')!='equivalence-review' or not isinstance(reference,dict)
        or set(reference)!={'path','sha256','commit'} or reference not in contract.get('sources',[])
        or not re.fullmatch(r'docs/factory/appl-result-supersession-\d{4}-\d{2}-\d{2}[^/]*\.json',reference['path'])):
        raise ValueError('factory-supersession-reference')


def overlaps(left, right):
    return (left.get('kind') == right.get('kind') == 'equivalence-review'
            and left['program'] == right['program']
            and bool(set(left['details']['items']) & set(right['details']['items'])))


def predecessor_row(contract, state, decision=None):
    return dict(contract_sha256=normalized_hash(contract), request_sha256=digest(contract),
                item_set_sha256=identity(contract), state=state, decision_sha256=decision)


def overlap_predecessors(contract, repository, root, events):
    """Bind every overlapping current request and latest decision, plus selection.

    A queue envelope is validated with its sources before it contributes an
    identity. Invalid queue evidence refuses intake rather than hiding a conflict.
    """
    from .factory_selection import load_selection
    from .factory_policy import FactoryInbox, load_contract
    from .kinds import factory_registry
    from .requests import confined, read_json
    from pathlib import Path
    selected = load_selection(repository, committed_only=True)
    latest = {}
    for event in events:
        previous = event.get('payload', {}).get('validation', {}).get('contract', {})
        if event.get('kind') == 'tower_decision' and overlaps(contract, previous):
            latest[digest(previous)] = (previous, event['content_sha256'])
    rows = [predecessor_row(previous, 'decided', decision) for previous, decision in latest.values()]
    folder = confined(root, 'work/control-tower/requests/factory', internal=True)
    inbox = FactoryInbox(root, 'factory', factory_registry())
    paths = sorted(folder.glob('*.json'))
    if len(paths) > 10000:
        raise ValueError('factory-live-request-inventory-bound')
    for path in paths:
        item = inbox.item(path.stem)
        previous = load_contract(root, item)
        fingerprint = digest(previous)
        if (overlaps(contract, previous) and fingerprint != digest(contract)
                and fingerprint not in latest):
            rows.append(predecessor_row(previous, 'live'))
    if selected:
        for choice in selected['records']:
            previous = read_json(confined(repository, choice['path']))
            if (overlaps(contract, previous) and normalized_hash(previous) != normalized_hash(contract)
                    and not any(r['contract_sha256'] == normalized_hash(previous) for r in rows)):
                rows.append(predecessor_row(previous, 'selected'))
    return sorted(rows, key=lambda row: (row['state'], row['request_sha256'])), selected


def reject_content_superseded(contract, repository, *, root, journal, public_key, trusted_head):
    """Refuse subset, superset and partial overlap before any destination write."""
    key = identity(contract)
    if key is None:
        return
    reference_shape(contract)
    from .verification import verify_journal
    from .requests import SHA
    if journal is None or public_key is None or not isinstance(trusted_head, str) or not SHA.fullmatch(trusted_head):
        raise ValueError('factory-content-trusted-journal-required')
    events = verify_journal(journal, public_key, scope='factory', expected_head=trusted_head)
    predecessors, selection = overlap_predecessors(contract, repository, root, events)
    reference = contract.get('supersession')
    if reference is None:
        if any(r['state'] == 'selected' for r in predecessors):
            raise ValueError('factory-request-superseded-content')
        if any(r['state'] == 'decided' for r in predecessors):
            raise ValueError('factory-review-content-already-decided')
        if predecessors:
            raise ValueError('factory-review-content-live-overlap')
        return
    from .factory_import import committed
    raw = committed(repository, reference['commit'], reference['path'])
    if sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('factory-supersession-file-hash')
    row = json.loads(raw)
    same = (row.get('program') == contract['program'] and row.get('item_set_sha256') == key
            and row.get('successor_contract_sha256') == normalized_hash(contract)
            and row.get('prepared_on') == reference['path'].split('appl-result-supersession-', 1)[1][:10])
    if not same or not predecessors:
        raise ValueError('factory-supersession-content-binding')
    minimum = selection['prepared_on'] if selection else '2026-10-18'
    if date.fromisoformat(row['prepared_on']) < date.fromisoformat(minimum):
        raise ValueError('factory-supersession-content-binding')
    if row.get('schema') == 'appl-result-content-supersession/2':
        if row.get('predecessors') != predecessors:
            raise ValueError('factory-supersession-content-binding')
    elif row.get('schema') == 'appl-result-content-supersession/1':
        # Preserve old exact-set records only when they fully describe the sole
        # predecessor. Old records cannot authorize a partial or multiple overlap.
        if (len(predecessors) != 1 or predecessors[0]['state'] == 'live'
                or predecessors[0]['item_set_sha256'] != key
                or row.get('predecessor_contract_sha256') != predecessors[0]['contract_sha256']
                or row.get('predecessor_decision_sha256') != predecessors[0]['decision_sha256']):
            raise ValueError('factory-supersession-content-binding')
    else:
        raise ValueError('factory-supersession-content-binding')
