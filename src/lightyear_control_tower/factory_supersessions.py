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


# Mirrors the dated selection; CI checks both against the actual chosen contracts.
CURRENT = {'93204f61f4387d331f44173877517c1b289572c415627c7146af76287784d3d6': {'program': 'INTCALC', 'selected': '550f6ed38a9e8863b959b294af3c61cc91c97f11eff17e324a3476d39bed237e', 'prepared_on': '2026-10-18'}, 'aba24ea42f9a7410e2b8b2352beed53cd9b7cea0c6310850e0c86e6dd4fd3e65': {'program': 'POSTTRAN', 'selected': '92c9dab92dfa6db53c1cf72a4784775377a886d81026b67850cbd19f14e806c1', 'prepared_on': '2026-10-18'}}


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


def reject_content_superseded(contract, repository, *, journal, public_key, trusted_head):
    """A verified current journal is required even when the item set is new.

    Absence of a caller-provided journal cannot be interpreted as no decisions.
    Re-import before any decision is idempotent; decided content requires a dated
    hash-bound successor record, independently of JSON spelling or queue digest.
    """
    key=identity(contract)
    if key is None:return
    selected=CURRENT.get(key);normalized=normalized_hash(contract)
    reference_shape(contract)
    reference=contract.get('supersession')
    if selected and normalized!=selected['selected'] and reference is None:
        raise ValueError('factory-request-superseded-content')
    from .verification import verify_journal
    from .requests import SHA
    if journal is None or public_key is None or not isinstance(trusted_head,str) or not SHA.fullmatch(trusted_head):
        raise ValueError('factory-content-trusted-journal-required')
    events=verify_journal(journal,public_key,scope='factory',expected_head=trusted_head)
    previous=[e for e in events if e.get('kind')=='tower_decision'
              and identity(e.get('payload',{}).get('validation',{}).get('contract',{}))==key]
    last=previous[-1] if previous else None
    if reference is None:
        if last:raise ValueError('factory-review-content-already-decided')
        return
    # The reference is itself an immutable, public committed source of the new
    # unsigned contract. Exclude only this self-referential source from its hash.
    from .factory_import import committed
    raw=committed(repository,reference['commit'],reference['path'])
    if sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('factory-supersession-file-hash')
    row=json.loads(raw)
    predecessor=normalized_hash(last['payload']['validation']['contract']) if last else selected['selected'] if selected else None
    if (row.get('schema')!='appl-result-content-supersession/1' or row.get('program')!=contract['program']
        or row.get('item_set_sha256')!=key or row.get('predecessor_contract_sha256')!=predecessor or predecessor is None
        or row.get('successor_contract_sha256')!=normalized
        or row.get('predecessor_decision_sha256')!=(last['content_sha256'] if last else None)
        or row.get('prepared_on')!=reference['path'].split('appl-result-supersession-',1)[1][:10]
        or date.fromisoformat(row['prepared_on'])<date.fromisoformat(selected['prepared_on'] if selected else '2026-10-18')):
        raise ValueError('factory-supersession-content-binding')
