"""Regenerate an unsigned revision from verified public files; no dispatch."""
from pathlib import Path
import json,hashlib
from lightyear_control_tower.decisions import digest
from .posttran_second_opinion import ROOT as root

def prepare(executable):
    old=json.loads((root/'docs/factory/posttran-second-opinion/plan.json').read_text());plan={k:v for k,v in old.items() if k!='content_sha256'}
    client=Path(executable)
    plan.update(schema='posttran-independent-preregistration/2',supersedes_plan_sha256=old['content_sha256'],status='revised-proposal-requires-new-exact-approval',execution_authorized=False,model_calls_made=0,
     client=dict(version='codex-cli 0.160.0',sha256=hashlib.sha256(client.read_bytes()).hexdigest(),role='verified installed artifact pin; CLI dispatch remains disabled because no verified CLI output cap',path=str(client)),
     dispatch=dict(protocol='OpenAI Responses API',endpoint='/v1/responses',broker='src/lightyear_factory/posttran_broker.py',broker_sha256=hashlib.sha256((root/'src/lightyear_factory/posttran_broker.py').read_bytes()).hexdigest(),output_cap_parameter='max_output_tokens',includes_reasoning=True,transport='explicit credential-owning transport must implement HTTP API; no model dispatch performed or credentials loaded'))
    for number,calls,hours in ((1,3,2),(2,2,1)):
     p=plan['phases'][str(number)];p.update(output_tokens=64000*calls,per_call_output_tokens=64000,api_equivalent_hard_cap_usd=12*calls,
     per_call_worst_case_usd=11.05,worst_case_token_cap_usd=round(11.05*calls,2),estimate_usd=None)
    plan['budget_basis']['output_cap_proposal']=dict(observed_aggregate_output=89246,observed_calls=10,observed_mean_output=8924.6,
     reasoning_separately_measured=False,per_call_tail_measured=False,proposed_cap=64000,multiplier_to_observed_mean=round(64000/8924.6,3),
     limitation='Only aggregate prior public factory usage available, not a measured per-call reasoning/output tail. 64000 is a proposal with headroom, not a forecast. Prior 16000 cap and approval do not authorize this revision.')
    plan['budget_basis']['reservation_rates_usd_per_million']=dict(input=25,output_including_reasoning=75,source='Retained conservative prior plan planning rates; fresh official pricing check required before dispatch')
    plan['content_sha256']=digest(plan)
    return plan
