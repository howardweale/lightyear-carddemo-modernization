"""Additive scenario evidence and fail-closed release policy; no authority creation."""
from fractions import Fraction
from lightyear_control_tower.decisions import digest,verify_envelope

PROPOSAL=dict(schema='scenario-threshold/1',decision_outcomes='1/1',legacy_mutants_killed='9/10',
              distinct_values_per_output_field=2,status='proposed-not-approved')


def fraction(value):
    if not isinstance(value,str) or value.count('/')!=1:raise ValueError('coverage-fraction')
    n,d=map(int,value.split('/'))
    if n<0 or d<=0 or n>d:raise ValueError('coverage-denominator')
    return Fraction(n,d)


def assess(adequacy,threshold,compared_fields):
    reasons=[]
    if not adequacy or not adequacy.get('instrumented'):return ['scenario-coverage-unavailable']
    try:
        if fraction(adequacy['decision_outcomes'])<fraction(threshold['decision_outcomes']):reasons.append('decision-outcomes-below-threshold')
        if fraction(adequacy['legacy_mutants_killed'])<fraction(threshold['legacy_mutants_killed']):reasons.append('legacy-mutants-below-threshold')
        values=adequacy['distinct_values_per_output_field']; minimum=threshold['distinct_values_per_output_field']
        if type(minimum)!=int or minimum<2:raise ValueError('diversity-threshold')
        if not compared_fields or not set(compared_fields)<=set(values):reasons.append('compared-field-inventory-incomplete')
        if any(type(values.get(f))!=int or values[f]<minimum for f in compared_fields):reasons.append('output-diversity-below-threshold')
        # Listed/unsolved branches are not proven unreachable and cannot shrink a denominator.
        if adequacy.get('uncovered'):reasons.append('unresolved-decision-outcomes')
    except (KeyError,TypeError,ValueError,ZeroDivisionError):reasons.append('malformed-scenario-evidence')
    return sorted(set(reasons))


def issue(verdict,adequacy,compared_fields,signer):
    if not verify_envelope(verdict,signer.public):raise ValueError('scenario-original-signature')
    return signer.sign(dict(schema='scenario-assessment/1',verdict_sha256=verdict['content_sha256'],
        scenario_adequacy=adequacy,compared_fields=sorted(set(compared_fields)),
        policy_proposal=PROPOSAL,model_calls=0))


def verified_assessment(verdict,report,judge_key):
    if (not verify_envelope(verdict,judge_key) or not verify_envelope(report,judge_key)
        or report.get('schema')!='scenario-assessment/1' or report['verdict_sha256']!=verdict['content_sha256']):
        raise ValueError('scenario-assessment-binding')
    return report['scenario_adequacy']


def release(verdict,report,judge_key,policy=None,operator_key=None):
    adequacy=verified_assessment(verdict,report,judge_key)
    reasons=assess(adequacy,PROPOSAL,report['compared_fields'])
    if (not policy or not operator_key or not verify_envelope(policy,operator_key)
        or policy.get('schema')!='scenario-policy-approval/1'
        or policy.get('verdict_sha256')!=verdict['content_sha256']
        or policy.get('assessment_sha256')!=report['content_sha256']):
        reasons.append('exact-operator-threshold-approval-required')
    else:
        reasons=assess(adequacy,policy['threshold'],report['compared_fields'])
    if verdict.get('verdict')!='equivalent':reasons.append('verdict-not-equivalent')
    if verdict.get('oracle_status')=='provisional' or verdict.get('run_class')=='engineering':reasons.append('provisional-or-engineering-evidence')
    return dict(releasable=not reasons,reasons=sorted(set(reasons)),scenario_adequacy=adequacy,
                status='releasable' if not reasons else 'equivalent (not releasable: weak scenarios)' if verdict.get('verdict')=='equivalent' else 'not releasable')
