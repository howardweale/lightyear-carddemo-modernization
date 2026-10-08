"""Prospective syntax-bound comparator. Historical v1-v5 replay is unchanged."""
from copy import deepcopy
from .native_evidence import canonical, compare_v2
from .semantics_v7 import contract
from .value_contract_v7 import result_sets, error_equivalent, RESULT_TYPES, table_contract


def compare(source, target, mapping, qualification=None):
    # Keep the historical comparator as an evidence computation, not authority
    # for ordered results, syntax policy routing or the new verdict.
    coverage_module=None
    versions={lane['observation']['coverage']['raw']['schema'].rsplit('/',1)[-1]
              for lane in (source,target) if lane['observation'].get('coverage')}
    if len(versions)>1:raise ValueError('mixed-coverage-revisions')
    if versions=={'2'}:
        from . import coverage_v2 as coverage_module
    result=compare_v2(source,target,mapping,qualification,revision=4,coverage_module=coverage_module)
    syntax=source['observation'].get('source_syntax')
    if syntax is None:raise ValueError('source-syntax-not-captured')
    bound=contract(syntax)
    if bound['source_sha256'] != source['baseline']['procedure_sha256']:
        raise ValueError('syntax-source-bytes-differ')
    result=deepcopy(result);result['schema']='tsql-native-comparison/6'
    result['syntax_contract']=bound
    result['differences']=[d for d in result['differences'] if d['observable']!='result_sets']
    # An obsolete family label can neither add nor suppress an obligation.
    result['unresolved']=[u for u in result['unresolved'] if u['observable']!='unordered-choice-policy-required'
                          and not u['observable'].startswith('unmapped-result-type:')]
    from .semantics_v7 import unique_update_join,target_contract
    proved={j['start_utf16'] for j in bound['update_joins'] if unique_update_join(j,source['before'])}
    target_source=target['observation'].get('target_source')
    if target_source is not None:
        twin=target_contract(target_source)
        if twin['source_sha256']!=target['baseline']['procedure_sha256']:raise ValueError('target-source-bytes-differ')
        result['target_syntax_contract']=twin
        for kind in twin['policy_obligations']:result['unresolved'].append(dict(observable=kind,classification='policy-decision-required'))
    else:result['unresolved'].append(dict(observable='target-determinism-not-assessed',classification='unsupported'))
    for obligation in bound['policy_obligations']:
        if obligation['kind']=='update-from-cardinality-unproven' and obligation['span']['start_utf16'] in proved:continue
        result['unresolved'].append(dict(observable=obligation['kind'],classification='policy-decision-required'))
    ordered=bound['order_by_present']
    rules=bound.get('result_contracts')
    if rules and bound['conditional_results']:
        result['unresolved'].append(dict(observable='conditional-result-origin',classification='unsupported'))
    try:
        a,b=result_sets(source['observation'],'sqlserver'),result_sets(target['observation'],'postgresql')
        from .value_contract_v7 import normalize_result_dates
        normalize_result_dates(a,b,source['observation'])
        if rules is not None:
            if len(a)!=len(rules) or len(b)!=len(rules):raise ValueError('result-origin-count-unresolved')
            for sets in (a,b):
                for rs,rule in zip(sets,rules):
                    if not rule['ordered']:rs['rows']=sorted(rs['rows'],key=canonical);continue
                    if not rule['resolved'] or not rule['key_indices']:raise ValueError('result-order-key-unresolved')
                    groups=[]
                    for row in rs['rows']:
                        key=canonical([row[i] for i in rule['key_indices']])
                        if not groups or groups[-1][0]!=key:groups.append((key,[]))
                        groups[-1][1].append(row)
                    rs['rows']=[row for _,group in groups for row in sorted(group,key=canonical)]
        elif not ordered:
            for sets in (a,b):
                for rs in sets:rs['rows']=sorted(rs['rows'],key=canonical)
        if canonical(a)!=canonical(b):
            result['differences'].append(dict(observable='ordered-result-sets' if ordered else 'result_sets',
                source=a,target=b,classification='lossy',attribution='result-order-or-value' if ordered else 'result-value-or-cardinality',
                trap_family=None))
            left,right=deepcopy(a),deepcopy(b)
            for sets in (left,right):
                for rs in sets:rs['rows']=sorted(rs['rows'],key=canonical)
            if ordered and canonical(left)==canonical(right):
                result['differences'][-1].update(attribution='row-order',trap_family=26)
    except ValueError as ex:
        result['unresolved'].append(dict(observable=str(ex),classification='unsupported'))
    for lane in (source,target):
        if lane['observation'].get('return_contract_supported') is False:
            result['differences']=[d for d in result['differences'] if d['observable']!='return_code']
            result['unresolved'].append(dict(observable='unmapped-return-contract',classification='unsupported'))
    a,b=source['observation']['error'],target['observation']['error']
    if a and b:
        decision=error_equivalent(a,b,mapping['calling_convention'].get('error_contract',{}))
        result['normalized_fields']=[v for v in result['normalized_fields'] if not v.startswith('public supplemental CHECK violation')]
        if decision is None and not any(u['observable']=='error-map-required' for u in result['unresolved']):
            result['unresolved'].append(dict(observable='error-map-required',classification='unsupported'))
        if decision is not None:
            result['unresolved']=[u for u in result['unresolved'] if u['observable']!='error-map-required']
            if not decision:result['differences'].append(dict(observable='error-class',source=a,target=b,classification='lossy'))
    for d in result['differences']:
        if d.get('attribution')!='row-order':
            d.pop('trap_family',None)
            d['attribution']='observed-'+d['observable']
    for u in result['unresolved']:u.pop('trap_family',None)
    if source['after'].get('standalone_sequences'):
        result['unresolved'].append(dict(observable='standalone-sequence-mapping-required',classification='unsupported'))
    try:
        contracts=[(state,table_contract(source[state]),table_contract(target[state])) for state in ('before','after')]
        result['unresolved']=[u for u in result['unresolved'] if not u['observable'].startswith('unmapped-table-type:')]
        from .value_contract_v7 import normalized_tables
        for state in ('before','after'):
            left,right=normalized_tables(source[state],target[state])
            key='all-table-'+state
            result['differences']=[d for d in result['differences'] if d['observable']!=key]
            if canonical(left)!=canonical(right):result['differences'].append(dict(observable=key,source=left,target=right,classification='lossy',attribution='observed-'+key))
        # Preserve the historical contract representation for already mapped types.
        for state,left,right in contracts:
            key='table-contract-'+state
            if canonical(left)!=canonical(right) and not any(d['observable']==key for d in result['differences']):
                result['differences'].append(dict(observable=key,source=left,target=right,
                    classification='lossy',attribution='observed-'+key))
    except ValueError:pass # Existing unsupported record survives.
    # Proven differences remain divergences even when matching observations
    # would require an unordered-choice decision. Never suppress a wrong twin.
    result['observed_status']='divergent' if result['differences'] else 'match-on-compared-observables'
    result['verdict']=('divergent' if result['differences'] else 'equivalent'
        if not result['unresolved'] and result['coverage_thresholds_met'] and qualification else 'insufficient-evidence')
    result['normalized_fields']=[n for n in result['normalized_fields'] if 'row multisets' not in n]
    result['normalized_fields'].append('ordered result rows preserved' if ordered else 'unordered result rows: duplicate-preserving multiset')
    result.update(cases_run=source['observation'].get('cases_run',1),minimal_case_sha256=source['observation'].get('minimal_case_sha256'),policy_decisions=[],
        representation_policy=dict(schema='tsql-representation/3',result_types=RESULT_TYPES,
            datetime='SQL datetime 1/300-second ticks; smalldatetime minute ticks; datetime2 exact',float='exact IEEE value unless a separately admitted Tower tolerance applies',
            result_order='source-syntax-bound',decimal='exact numerical value; scale only normalized'),
        attribution='observed observable; corpus family is not causal evidence')
    return result
