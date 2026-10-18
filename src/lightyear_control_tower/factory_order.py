"""Ordered request dependencies, verified at intake, signing and consumption."""
from copy import deepcopy
from .decisions import digest
from .requests import SHA

ERROR = 'factory-signing-order-predecessor-required'

def require(ok):
    if not ok: raise ValueError(ERROR)

def body_hash(contract):
    return digest({k:v for k,v in contract.items() if k != 'signing_order'})

def shape(contract):
    row=contract.get('signing_order')
    if row is None: return
    require(isinstance(row,dict) and set(row)=={'packet_sha256','position','predecessor_contract_sha256','predecessor_decision_sha256'})
    require(type(row['position']) is int and 1 <= row['position'] <= 6)
    require(isinstance(row['packet_sha256'],str) and SHA.fullmatch(row['packet_sha256']))
    for key in ('predecessor_contract_sha256','predecessor_decision_sha256'):
        require(row[key] is None or isinstance(row[key],str) and SHA.fullmatch(row[key]))
    require((row['predecessor_contract_sha256'] is None)==(row['position']==1))
    if row['position']==1: require(row['predecessor_decision_sha256'] is None)

def check(contract, events, *, before=None):
    shape(contract)
    row=contract.get('signing_order')
    if row is None or row['position']==1: return
    require(events is not None and row['predecessor_decision_sha256'] is not None)
    event=next((e for e in events if e.get('content_sha256')==row['predecessor_decision_sha256']),None)
    require(event is not None and event.get('kind')=='tower_decision')
    payload=event['payload']; previous=payload.get('validation',{}).get('contract',{})
    require(payload.get('outcome') in ('accept','keep','approve'))
    require(previous.get('program')==contract['program'] and body_hash(previous)==row['predecessor_contract_sha256'])
    order=previous.get('signing_order',{})
    require(order.get('packet_sha256')==row['packet_sha256'] and order.get('position')==row['position']-1)
    require(before is None or event['sequence'] < before)
    require(not any(e.get('kind')=='tower_decision' and e['sequence']>event['sequence']
                    and e.get('payload',{}).get('bound')==payload.get('bound') for e in events))
    check(previous,events,before=event['sequence'])

def bind_predecessor(template, proof):
    """Prepare new unsigned bytes; intake still requires externally trusted journal verification."""
    result=deepcopy(template);shape(result)
    result['signing_order']['predecessor_decision_sha256']=proof['decision_sha256']
    check(result,proof['journal']['events'])
    return result

def intake(contract, *, journal=None, public_key=None, trusted_head=None):
    shape(contract)
    if contract.get('signing_order',{}).get('position',1)==1:return
    require(journal is not None and public_key is not None and isinstance(trusted_head,str) and SHA.fullmatch(trusted_head))
    from .verification import verify_journal
    check(contract,verify_journal(journal,public_key,scope='factory',expected_head=trusted_head))
