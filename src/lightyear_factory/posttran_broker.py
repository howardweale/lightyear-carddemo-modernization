"""Bounded POSTTRAN Responses transport. Importing never opens a connection.

Dispatch requires an exact revised-plan approval and explicit injected transport.
No CLI configuration is represented as a server output-token cap.
"""
from lightyear_control_tower.decisions import digest
from .posttran_preflight import verify_approval,check_client
from .posttran_second_opinion import require_inputs


def request(plan,approval,executable,packet,*,attempt,spent_usd=0):
    verify_approval(plan,approval);check_client(plan,executable);require_inputs(plan['inputs'])
    if plan.get('schema')!='posttran-independent-preregistration/2':raise ValueError('revised-plan-required')
    limits=plan['phases']['1']
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


def dispatch(plan,approval,executable,packet,transport,*,attempt,spent_usd=0):
    payload=request(plan,approval,executable,packet,attempt=attempt,spent_usd=spent_usd)
    # Transport owns credentials. This broker never reads them; tests use a fake.
    response=transport('/v1/responses',payload)
    usage=response.get('usage',{});output=usage.get('output_tokens');inputs=usage.get('input_tokens')
    if type(output)!=int or type(inputs)!=int:raise ValueError('missing-billed-usage')
    if output>payload['max_output_tokens'] or inputs>plan['phases']['1']['per_call_input_tokens']:raise ValueError('token-cap-breach')
    if response.get('status')!='completed':raise ValueError('incomplete-attempt-preserve-failure')
    return response
