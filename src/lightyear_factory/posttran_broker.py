"""Bounded POSTTRAN Responses transport. Importing never opens a connection.

Dispatch requires an exact revised-plan approval and explicit injected transport.
No CLI configuration is represented as a server output-token cap.
"""
import math
import json
import os
from pathlib import Path
from datetime import datetime,timezone
from lightyear_mainframe.legacy_twin import ROOT as STATE_ROOT
from .posttran_preflight import verify_approval,check_client
from .posttran_second_opinion import require_inputs


def request(plan,approval,executable,packet,*,attempt,spent_usd=0):
    verify_approval(plan,approval);check_client(plan,executable);require_inputs(plan['inputs'])
    if plan.get('schema') not in ('posttran-independent-preregistration/2','posttran-independent-preregistration/3'):raise ValueError('revised-plan-required')
    if plan.get('schema')=='posttran-independent-preregistration/3':
        from hashlib import sha256
        if sha256(Path(__file__).read_bytes()).hexdigest()!=plan['dispatch']['broker_sha256']:raise ValueError('broker-hash-mismatch')
        verifier=Path(__file__).with_name('posttran_preflight.py')
        if sha256(verifier.read_text(encoding='utf-8').encode()).hexdigest()!=plan['dispatch']['approval_verifier_sha256']:raise ValueError('approval-verifier-hash-mismatch')
    limits=plan['phases']['1']
    if type(spent_usd) not in (int,float) or not math.isfinite(spent_usd) or spent_usd<0:raise ValueError('invalid-prior-spend')
    if type(attempt)!=int or not 1<=attempt<=limits['attempts']:raise ValueError('attempt-cap')
    if spent_usd+limits['per_call_worst_case_usd']>limits['api_equivalent_hard_cap_usd']:raise ValueError('dollar-cap-reservation')
    expected=set(plan['inputs'])|{'phase1-work-order.md'}
    if set(packet)!=expected:raise ValueError('independent-packet-boundary')
    from hashlib import sha256
    for path,raw in packet.items():
        want=plan['inputs'].get(path,plan['prompts'].get(path))
        if sha256(raw).hexdigest()!=want:raise ValueError('independent-packet-bytes')
    return dict(model=plan['model'],reasoning={'effort':plan['reasoning_effort']},
       service_tier=plan['service_tier'],max_output_tokens=limits['per_call_output_tokens'],
       truncation='disabled',store=False,input=[{'role':'user','content':[{'type':'input_text','text':
          path+'\n'+raw.decode('utf-8') if path.endswith(('.md','.cbl','.cpy','.jcl')) else path+'\nPUBLIC FIXED BYTES HEX\n'+raw.hex()} for path,raw in sorted(packet.items())]}])



def reserve(plan,attempt):
    """Fixed plan-bound ledger: failures consume the full reservation, no refunds."""
    relative=Path(plan['dispatch']['reservation_ledger'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('invalid-ledger-path')
    target=STATE_ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
    lock=target.with_suffix('.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise ValueError('phase-reservation-busy-or-interrupted') from None
    try:
        os.close(fd)
        now=datetime.now(timezone.utc);limits=plan['phases']['1']
        state=json.loads(target.read_text()) if target.exists() else dict(plan_sha256=plan['content_sha256'],started_at=now.isoformat(),reservations=[])
        if state['plan_sha256']!=plan['content_sha256']:raise ValueError('ledger-plan-mismatch')
        entries=state['reservations']
        if type(entries)!=list or any(r.get('attempt')!=i+1 or r.get('reserved_usd')!=limits['per_call_worst_case_usd'] for i,r in enumerate(entries)):raise ValueError('invalid-reservation-ledger')
        elapsed=(now-datetime.fromisoformat(state['started_at'])).total_seconds()
        if elapsed<0 or elapsed>=limits['hours']*3600:raise ValueError('phase-time-cap')
        if len(entries)>=limits['attempts'] or attempt!=len(entries)+1:raise ValueError('durable-attempt-cap')
        if (len(entries)+1)*limits['per_call_worst_case_usd']>limits['api_equivalent_hard_cap_usd']:raise ValueError('durable-dollar-cap')
        entries.append(dict(attempt=attempt,reserved_at=now.isoformat(),reserved_usd=limits['per_call_worst_case_usd'],input_tokens=limits['per_call_input_tokens'],output_tokens=limits['per_call_output_tokens']))
        temp=target.with_suffix('.pending')
        # Flush before atomically publishing the reservation, and before any API call.
        with temp.open('x',encoding='utf-8') as out:
            json.dump(state,out,sort_keys=True);out.flush();os.fsync(out.fileno())
        os.replace(temp,target)
    finally:lock.unlink(missing_ok=True)


def record_preflight(plan, attempt, event):
    """Durably record count request/result before generation; no payload or credentials."""
    relative=Path(plan['dispatch']['reservation_ledger'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('invalid-ledger-path')
    target=STATE_ROOT/relative
    lock=target.with_suffix('.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise ValueError('phase-reservation-busy-or-interrupted') from None
    try:
        os.close(fd)
        state=json.loads(target.read_text(encoding='utf-8'))
        if state['plan_sha256']!=plan['content_sha256']:raise ValueError('ledger-plan-mismatch')
        if len(state['reservations'])!=attempt:raise ValueError('preflight-attempt-binding')
        row=state['reservations'][attempt-1]
        if row['attempt']!=attempt:raise ValueError('preflight-attempt-binding')
        events=row.setdefault('preflight',[])
        if (not events and event['status']!='requested') or (events and (len(events)!=1 or event['status']=='requested')):
            raise ValueError('preflight-event-order')
        events.append(dict(event,recorded_at=datetime.now(timezone.utc).isoformat(),generation=False))
        temp=target.with_suffix('.pending')
        with temp.open('x',encoding='utf-8') as out:
            json.dump(state,out,sort_keys=True);out.flush();os.fsync(out.fileno())
        os.replace(temp,target)
    finally:lock.unlink(missing_ok=True)

def dispatch(plan,approval,executable,packet,transport,*,attempt,spent_usd=0):
    payload=request(plan,approval,executable,packet,attempt=attempt,spent_usd=spent_usd)
    if plan.get('pricing_status')!='verified-current-pricing-bound-to-plan' or not plan.get('pricing_checked_date') or plan.get('transport_contract_verified_offline') is not True:
        raise ValueError('live-dispatch-blocked-pending-pricing-and-transport-bound-approved-plan')
    if payload['service_tier']!='default':raise ValueError('unapproved-service-tier')
    reserve(plan,attempt)
    # Count the exact packet before any generation; do not infer tokens from bytes.
    count_payload={key:payload[key] for key in ('model','input','reasoning')}
    amended=plan.get('schema')=='posttran-independent-preregistration/3'
    if amended:
        from lightyear_control_tower.decisions import digest
        record_preflight(plan,attempt,dict(status='requested',endpoint='/v1/responses/input_tokens',request_sha256=digest(count_payload),packet_sha256={k:__import__('hashlib').sha256(v).hexdigest() for k,v in packet.items()}))
    try:
        counted=transport('/v1/responses/input_tokens',count_payload)
        tokens=counted.get('input_tokens') if isinstance(counted,dict) else None
        if not isinstance(counted,dict) or counted.get('object')!='response.input_tokens' or type(tokens)!=int or tokens<0:raise ValueError('invalid-input-token-count')
        if tokens>plan['phases']['1']['per_call_input_tokens']:raise ValueError('input-token-preflight-cap')
    except Exception as error:
        if amended:record_preflight(plan,attempt,dict(status='failed',error_type=type(error).__name__))
        raise
    if amended:record_preflight(plan,attempt,dict(status='completed',input_tokens=tokens,response_sha256=digest(counted)))
    # Transport owns credentials. This broker never reads them; tests use a fake.
    response=transport('/v1/responses',payload)
    if not isinstance(response,dict) or not isinstance(response.get('usage'),dict):raise ValueError('missing-billed-usage')
    usage=response.get('usage',{});output=usage.get('output_tokens');inputs=usage.get('input_tokens')
    if type(output)!=int or type(inputs)!=int or output<0 or inputs<0:raise ValueError('missing-billed-usage')
    if output>payload['max_output_tokens'] or inputs>plan['phases']['1']['per_call_input_tokens']:raise ValueError('token-cap-breach')
    if inputs!=tokens:raise ValueError('input-count-usage-mismatch')
    if response.get('service_tier','default')!='default':raise ValueError('service-tier-mismatch')
    if response.get('status')!='completed':raise ValueError('incomplete-attempt-preserve-failure')
    return response
