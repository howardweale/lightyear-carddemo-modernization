"""Bind a new unsigned INTCALC request using externally trusted public proof."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from lightyear_control_tower.decisions import canonical, digest
from lightyear_control_tower.factory_order import body_hash, bind_predecessor, check
from lightyear_control_tower.factory_policy import validate_contract
from lightyear_control_tower.requests import SHA, read_bytes
from lightyear_control_tower.verification import verify_decision, verify_journal

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PACKET='docs/factory/intcalc-signing-order-2026-10-17.json'


def templates(root, packet):
    root=Path(root).resolve();path=(root/packet).resolve()
    if not path.is_relative_to(root):raise ValueError('packet-path-outside-checkout')
    index=json.loads(read_bytes(path))
    if (index.get('schema')!='factory-unsigned-signing-order/1' or index.get('program')!='INTCALC'
        or index.get('signed') is not False or len(index.get('items',[]))!=6):
        raise ValueError('unsigned-intcalc-packet-required')
    contracts=[]
    for position,row in enumerate(index['items'],1):
        file=(root/row['path']).resolve()
        if not file.is_relative_to(root) or row['order']!=position:raise ValueError('packet-order-path')
        raw=read_bytes(file)
        if sha256(raw).hexdigest()!=row['sha256']:raise ValueError('packet-file-hash')
        contract=validate_contract(json.loads(raw),check_evidence=False)
        if contract['program']!='INTCALC' or contract['kind']!=row['kind']:raise ValueError('packet-program-kind')
        contracts.append(contract)
    bodies=[body_hash(c) for c in contracts];packet_hash=digest(bodies)
    for i,c in enumerate(contracts):
        order=c.get('signing_order',{})
        if order!=dict(packet_sha256=packet_hash,position=i+1,predecessor_contract_sha256=bodies[i-1] if i else None,
                       predecessor_decision_sha256=None):raise ValueError('packet-template-binding')
    return contracts


def bind(proof, public_key, trusted_head, position, *, root=ROOT, packet=DEFAULT_PACKET):
    if not isinstance(trusted_head,str) or not SHA.fullmatch(trusted_head):raise ValueError('external-current-head-required')
    if b'PRIVATE KEY' in public_key:raise ValueError('public-key-only')
    if type(position) is not int or not 1<=position<=6:raise ValueError('position-must-be-1-through-6')
    contracts=templates(root,packet)
    if position==1:
        verify_journal(proof,public_key,scope='factory',expected_head=trusted_head)
        return contracts[0]
    journal=proof.get('journal')
    if not isinstance(journal,dict):raise ValueError('predecessor-decision-proof-required')
    events=verify_journal(journal,public_key,scope='factory',expected_head=trusted_head)
    event=next((e for e in events if e.get('content_sha256')==proof.get('decision_sha256')),None)
    if event is None or event.get('kind')!='tower_decision':raise ValueError('predecessor-decision-proof-required')
    payload=event['payload'];previous=payload.get('validation',{}).get('contract',{})
    expected=contracts[position-2]
    if (body_hash(previous)!=body_hash(expected) or previous.get('program')!='INTCALC'
        or previous.get('signing_order',{}).get('position')!=position-1):
        raise ValueError('wrong-predecessor-position-or-packet')
    verify_decision(proof,public_key,expected['kind'],payload['bound'],scope='factory',expected_head=trusted_head,
                    outcomes=('accept','keep','approve'))
    check(previous,events,before=event['sequence'])
    result=bind_predecessor(contracts[position-1],proof)
    check(result,events)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof',type=Path,required=True,help='Position 1: current signed journal export; 2-6: predecessor decision proof')
    parser.add_argument('--public-key',type=Path,required=True)
    parser.add_argument('--trusted-head',required=True)
    parser.add_argument('--position',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repository',type=Path,default=ROOT,help='Reviewed checkout containing the unsigned packet')
    parser.add_argument('--packet',default=DEFAULT_PACKET,help='Reviewed packet index, relative to the checkout')
    args=parser.parse_args()
    result=bind(json.loads(read_bytes(args.proof)),read_bytes(args.public_key),args.trusted_head,args.position,
                root=args.repository,packet=args.packet)
    raw=canonical(result)
    # A fresh directory prevents replacement of previously reviewed artifacts.
    args.output.mkdir(parents=True,exist_ok=False)
    file=args.output/f'intcalc-{args.position:02d}-bound-request.json'
    with file.open('xb') as stream:stream.write(raw)
    print(json.dumps(dict(path=str(file.resolve()),file_sha256=sha256(raw).hexdigest(),
                         queue_id='factory-'+digest(result),position=args.position,signed=False),indent=2))


if __name__=='__main__':main()
