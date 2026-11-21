"""Abort-file joins to a prelaunch review; no outcome or death authority.

Only the original supervisor supplies its prelaunch native review in integration.
The pure predicate accepts mappings for refusal tests and never authenticates
them. No signature, new schema, retry, reservation, context or strict result.
"""
from .configured_abort_evidence import read_abort_candidate_files,_require
from .configured_receipt_terminal import _original_json
from .configured_receipt_case import review_case,consumption_tools
from lightyear_factory.contracts import canonical_hash

def match_abort_preflight(admission,review,live_ci,*,_case_id='configured-build-control'):
    """Relationship predicate only. A successful return supplies no authority."""
    _require(type(admission) is dict and type(review) is dict and type(live_ci) is dict,'preflight-shape')
    _require(review.get('schema')=='factory-human-drill-plan-review/1'
        and review.get('status')=='verified-plan-only'
        and review.get('execution_authorized') is False
        and review.get('admission_receipt_issued') is False
        and review.get('nonce_consumed') is False
        and review.get('content_sha256')==canonical_hash(review,{'content_sha256'}),'preflight-review')
    verified=review.get('verified_model_admission');binding=review.get('drill_binding')
    _require(type(verified) is dict and type(binding) is dict,'preflight-binding-shape')
    _require(type(_case_id) is str and _case_id in ('configured-build-control','answer-fragment')
        and binding.get('case_id')==_case_id,'preflight-case')
    for name in ('plan_sha256','decision_sha256','trusted_journal_head','work_order_sha256'):
        _require(name in verified and admission.get(name)==verified[name],'preflight-'+name)
    for name in ('nonce_sha256','execution_policy_sha256','work_order_sha256'):
        _require(name in binding and admission.get(name)==binding[name],'preflight-'+name)
    ci=admission.get('ci');signed_ci=binding.get('ci')
    _require(type(ci) is dict and type(signed_ci) is dict
        and set(live_ci)=={'repository','run_id','run_attempt','job'},'preflight-ci-shape')
    _require(type(live_ci['run_id']) is int and live_ci['run_id']>0
        and type(live_ci['run_attempt']) is int and live_ci['run_attempt']==1
        and type(ci.get('run_id')) is int and type(ci.get('run_attempt')) is int
        and all(ci.get(k)==v for k,v in live_ci.items()),'preflight-live-ci')
    _require(all(k in signed_ci and ci.get(k)==signed_ci[k]
        for k in ('repository','job','run_attempt','workflow_ref'))
        and 'executable_commit' in verified
        and ci.get('head_sha')==verified['executable_commit'],'preflight-signed-ci')

def read_preflight_bound_abort(runs_root,review,live_ci):
    """Read original files, check prelaunch relations, then observe existing tag.

    No proof API is reentered after expiry, no missing admission reconstructed.
    Service metadata plus hashes remain observations, not signed outcome trust.
    """
    case=review_case(review)
    _,_,observe_existing_consumption=consumption_tools(case)
    raw=read_abort_candidate_files(runs_root,_case_id=case)
    admission=_original_json(raw['human-admission.json'])
    match_abort_preflight(admission,review,live_ci,_case_id=case)
    observed=observe_existing_consumption(_original_json(raw['human-consumption.json']),admission)
    _require(read_abort_candidate_files(runs_root,_case_id=case)==raw,'preflight-files-changed')
    return {'original_files':raw,'service_observations':observed}
