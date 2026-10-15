"""Prospective signed review overlay; never edits the original run or history."""
import copy
from .equivalence_automation import verify,digest,sealed,audit_disposition
from .equivalence_classes import signed_member


def apply_reviews(ledger, class_requests, audit_request, submissions, authority, matcher_sha256, disabled_classes=()):
    """Submissions bind a contract digest to a proof verified with external trust.

    Audit rejection is a confirmed error. It retracts the whole route from this
    overlay, including class additions; a pending audit is never called clean.
    A disabled route needs a new implementation/run and a new signed audit.
    """
    verify(ledger)
    if authority is None or not authority.signed_only:raise ValueError('external-signed-authority-required')
    rows=copy.deepcopy(ledger['rows']); by_id={r['id']:r for r in rows};decisions=[]
    requests={digest(r['contract']):r for r in class_requests}
    for key,proof in submissions.items():
        if key not in requests and key!=digest(audit_request.get('contract',{})):
            raise ValueError('unbound-review-submission')
        if key not in requests:continue
        request=requests[key];cp=verify(request['class_proof'])
        if cp['head']!=ledger['head']:raise ValueError('class-head-mismatch')
        if cp['class_id'] in disabled_classes:raise ValueError('held-out-disabled-class')
        for mid,match in cp['matches'].items():
            if mid not in by_id:raise ValueError('class-mutant-not-in-ledger')
            row=by_id[mid]
            # All class memberships must bind the exact mutation, even if an
            # additional solver/pair hash is also included in the class packet.
            if match.get('mutant_sha256')!=row['mutant_sha256']:raise ValueError('class-mutant-binding')
            result=signed_member(authority,request,proof,mid,match,matcher_sha256)
            if row['status'] in ('unresolved','proposed'):
                row.update(status='equivalent',route='S2',basis='signed-class-proof',evidence=[result])
            decisions.append(result['decision_sha256'])
    samples=audit_request.get('packet',{}).get('samples',[]); reviewed={}
    contract=audit_request.get('contract')
    if contract and digest(contract) in submissions:
        packet=verify(audit_request['packet'])
        if packet['head']!=ledger['head']:raise ValueError('audit-head-mismatch')
        original={r['id']:r for r in ledger['rows']}
        if any(original.get(r['id'])!=r for r in packet['resolutions']):raise ValueError('audit-resolution-binding')
        if contract['details']['packet_sha256']!=digest(packet):raise ValueError('audit-packet-binding')
        # Verify rejected/investigate outcomes too; never ignore a negative audit.
        proof=submissions[digest(contract)]
        decision=authority.verify(proof,'equivalence-review',contract,('accept','reject','investigate'))
        decisions.append(proof['decision_sha256'])
        for mid,item in decision['validation']['items'].items():
            if item['outcome'] in ('accept','reject'):reviewed[mid]='correct' if item['outcome']=='accept' else 'incorrect'
    audit,disabled=audit_disposition(samples,reviewed)
    for row in rows:
        if (row['program'],row['route']) in disabled:
            row.update(status='unresolved',disabled_route=row['route'],route=None,reason='confirmed-audit-error-disables-route')
    return sealed(dict(schema='equivalence-review-overlay/1',head=ledger['head'],program=ledger['program'],
                       parent_sha256=ledger['content_sha256'],rows=rows,audit=audit,
                       disabled_routes=[list(x) for x in sorted(disabled)],signed_decisions=sorted(set(decisions)),
                       release_authorized=False,model_calls=0))
