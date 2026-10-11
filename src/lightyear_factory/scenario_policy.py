"""Additive scenario evidence and fail-closed release policy; no authority creation."""
from fractions import Fraction
from lightyear_control_tower.decisions import digest,verify_envelope

# Howard's explicit 2026-10-11 chat decision accepts only these pinned EOF edges.
# This is an exception record, not a signed threshold/release authorization.
IO_ACCEPTANCES=(
    dict(program='CBACT04C',source_sha256='5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4',
         id='legacy:cobol-decision:CBACT04C:189:671',outcome='false',accepted_by='Howard',accepted_on='2026-10-11'),
    dict(program='CBTRN02C',source_sha256='708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f',
         id='legacy:cobol-decision:CBTRN02C:203:684',outcome='false',accepted_by='Howard',accepted_on='2026-10-11'),
)

PROPOSAL=dict(schema='scenario-threshold/2',business_logic_outcomes='1/1',legacy_mutants_killed='9/10',
              minimum_systematic_mutants=50,io_policy='fault-covered-or-exact-operator-exception',
              accepted_io_outcomes=[],distinct_values_per_output_field=2,status='proposed-not-approved')


def fraction(value):
    if not isinstance(value,str) or value.count('/')!=1:raise ValueError('coverage-fraction')
    n,d=map(int,value.split('/'))
    if n<0 or d<=0 or n>d:raise ValueError('coverage-denominator')
    return Fraction(n,d)


def assess(adequacy,threshold,compared_fields):
    reasons=[]
    if not adequacy or not adequacy.get('instrumented'):return ['scenario-coverage-unavailable']
    try:
        if threshold.get('schema')=='scenario-threshold/2':
            split=adequacy['coverage_by_class']
            if fraction(split['business-logic']['fraction'])<fraction(threshold['business_logic_outcomes']):reasons.append('business-outcomes-below-threshold')
            mutants=adequacy['systematic_mutation']
            counts=mutants['counts']
            names=('killed-divergent','killed-failure','survived','not-compiled','equivalent (argued, listed)')
            if set(counts)!=set(names) or any(type(v)!=int or v<0 for v in counts.values()):raise ValueError('mutant-counts')
            eligible=sum(counts.values())-counts['equivalent (argued, listed)']-counts['not-compiled']
            killed=counts['killed-divergent']+counts['killed-failure']
            if (mutants['eligible_count']!=eligible or mutants['excluded_equivalents']!=counts['equivalent (argued, listed)']
                or len(mutants['unresolved_survivors'])!=counts['survived'] or len(mutants['not_compiled'])!=counts['not-compiled']
                or adequacy['legacy_mutants_killed']!=f'{killed}/{eligible}'):raise ValueError('mutant-denominator-binding')
            dispositions=mutants['equivalent_dispositions']
            if len({d['mutant_id'] for d in dispositions})!=len(dispositions) or any(not d.get('argument') or not d.get('source_sha256') for d in dispositions):raise ValueError('mutant-equivalence-binding')
            if mutants['eligible_count']<threshold['minimum_systematic_mutants']:reasons.append('systematic-mutant-set-too-small')
            if mutants.get('unresolved_survivors'):reasons.append('unresolved-mutant-survivors')
            # Howard, 2026-10-11: compiler refusals are listed exclusions, not blockers.
            refused=mutants['not_compiled']
            if any(not isinstance(x,str) or not x for x in refused) or len(set(refused))!=len(refused):raise ValueError('compiler-refusal-inventory')
            if set(refused)&{d['mutant_id'] for d in dispositions}:raise ValueError('overlapping-mutant-exclusions')
            if mutants['excluded_equivalents']!=len(mutants['equivalent_dispositions']):raise ValueError('equivalent-inventory')
            accepted={tuple(x) for x in threshold.get('accepted_io_outcomes',[])}
            accepted.update((a['id'],a['outcome']) for a in IO_ACCEPTANCES
                if a['program']==adequacy.get('program') and a['source_sha256']==adequacy.get('source_sha256'))
            for x in adequacy.get('uncovered',[]):
                if not isinstance(x,dict):raise ValueError('outcome-shape')
                if x.get('classification')!='io-handling' or (x['id'],x['outcome']) not in accepted:reasons.append('unaccepted-outcome-gap')
        elif fraction(adequacy['decision_outcomes'])<fraction(threshold['decision_outcomes']):reasons.append('decision-outcomes-below-threshold')
        if fraction(adequacy['legacy_mutants_killed'])<fraction(threshold['legacy_mutants_killed']):reasons.append('legacy-mutants-below-threshold')
        values=adequacy['distinct_values_per_output_field']; minimum=threshold['distinct_values_per_output_field']
        if type(minimum)!=int or minimum<2:raise ValueError('diversity-threshold')
        if not compared_fields or not set(compared_fields)<=set(values):reasons.append('compared-field-inventory-incomplete')
        if any(type(values.get(f))!=int or values[f]<minimum for f in compared_fields):reasons.append('output-diversity-below-threshold')
        # Listed/unsolved branches are not proven unreachable and cannot shrink a denominator.
        if threshold.get('schema')!='scenario-threshold/2' and adequacy.get('uncovered'):reasons.append('unresolved-decision-outcomes')
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
