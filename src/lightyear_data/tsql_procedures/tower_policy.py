"""Policy admission consumes a verified Tower decision, never a corpus label."""
from lightyear_control_tower.verification import verify_decision
from .native_evidence import canonical,sha

KIND='procedure-equivalence-policy'

def bindings(inventory,procedure,policy,evidence):
    return {k:sha(canonical(v)) for k,v in dict(inventory=inventory,procedure=procedure,policy=policy,evidence=evidence).items()}

def admit(proof,key,bound,*,scope,head,now):
    if set(bound)!={'inventory','procedure','policy','evidence'}:raise ValueError('procedure-policy-bindings')
    verify_decision(proof,key,KIND,bound,scope=scope,outcomes={'approved'},expected_head=head,now=now)
    return {'kind':KIND,'decision_proof_sha256':sha(canonical(proof)),'bound':bound,
            'claim':'operator review; not independent attestation'}
