"""Policy obligations from bound ScriptDom nodes, never corpus family labels."""
from .native_evidence import canonical, sha


def contract(parsed):
    ast = parsed.get('ast', parsed)
    if (ast.get('schema') != 'tsql-scriptdom/1' or ast.get('parsed') is not True
            or ast.get('errors') != [] or len(ast.get('input_sha256', '')) != 64):
        raise ValueError('bound-scriptdom-syntax-required')
    nodes = ast['ast_nodes']
    def inside(child, parent):
        return (parent['start_utf16'] <= child['start_utf16'] and
                child['start_utf16'] + child['length_utf16'] <= parent['start_utf16'] + parent['length_utf16'])
    def contained(kind, parent):
        return [n for n in nodes if n['kind'] == kind and inside(n, parent)]
    # ORDER BY within OVER does not order a result set.
    orders = [n for n in nodes if n['kind'] == 'OrderByClause'
              and not any(p['kind'] == 'OverClause' and inside(n, p) for p in nodes)]
    obligations = []
    execs=ast.get('semantic_catalogue',{}).get('exec_contracts',[])
    closed_execs=[e for e in execs if e['no_results_proven']]
    # A caller's AST cannot establish the order of a callee/dynamic result.
    # Dependency parsing must supply a future result-origin contract; refuse now.
    for n in nodes:
        if n['kind'] in {'ExecuteStatement','ExecutableProcedureReference','ExecutableStringList'} and not any(inside(n,e) for e in closed_execs):
            obligations.append(dict(kind='unresolved-exec-result-origin',span=n))
        if n['kind'] in {'OffsetClause','XmlForClause','TableSampleClause'} or n['kind']=='AssignmentSetClause' and n.get('assignment_variable',True):
            obligations.append(dict(kind='selection-or-assignment-order-policy-required',span=n))
        if n['kind'] in {'SetRowCountStatement','SelectSetVariable'}:
            obligations.append(dict(kind='rowcount-or-multirow-assignment-policy-required',span=n))
    for dependency in ast.get('semantic_catalogue',{}).get('dependencies',[]):
        if dependency.get('cross_database'):
            obligations.append(dict(kind='cross-database-dependency',dependency=dependency))
    for top in (n for n in nodes if n['kind'] == 'TopRowFilter'):
        queries = [n for n in nodes if n['kind'] in ('QuerySpecification','QueryParenthesisExpression') and inside(top,n)]
        query = min(queries,key=lambda n:n['length_utf16']) if queries else None
        # Query-expression ORDER BY may follow the query-specification span.
        selects = [n for n in nodes if n['kind']=='SelectStatement' and inside(top,n)]
        parent = min(selects,key=lambda n:n['length_utf16']) if selects else query
        nested = [n for n in nodes if n['kind']=='QuerySpecification'
                  and parent and inside(n,parent) and n != query]
        if any(n['kind']=='ExistsPredicate' and inside(top,n) for n in nodes):continue
        if parent is None or not any(inside(o,parent) and not any(inside(o,n) for n in nested) for o in orders):
            obligations.append(dict(kind='unordered-top',span=top))
        else:
            obligations.append(dict(kind='top-order-uniqueness-unproven',span=top))
    for update in (n for n in nodes if n['kind']=='UpdateSpecification'):
        if any(n.get('parent_id') == update.get('node_id') if 'parent_id' in n else not any(p['kind']=='QuerySpecification' and inside(n,p) and inside(p,update) for p in nodes) for n in contained('FromClause',update)):
            obligations.append(dict(kind='update-from-cardinality-unproven',span=update))
    extra = ast.get('semantic_catalogue', {})
    for name in extra.get('nondeterministic_functions',[]):
        obligations.append(dict(kind='nondeterminism-policy-required',function=name))
    return dict(schema='tsql-syntax-contract/1',source_sha256=ast['input_sha256'],
                parser_version=ast['version'],parser_output_sha256=sha(canonical(ast)),
                order_by_present=bool(orders),order_spans=orders,policy_obligations=obligations,
                procedures=extra.get('procedures',[]),dependencies=extra.get('dependencies',[]),
                exec_contracts=execs,
                result_producers_complete=extra.get('result_producers_complete',False),
                result_contracts=extra.get('result_contracts'),update_joins=extra.get('update_joins',[]),
                conditional_results=any(n['kind'] in {'IfStatement','WhileStatement','TryCatchStatement','ExecuteStatement'} for n in nodes))


def verify_contract(value, parsed):
    if value != contract(parsed):raise ValueError('syntax-contract-replay-mismatch')
    return value


def unique_update_join(join,state):
    """Narrow positive proof: exactly one PK-equality join, no OR/functions.

    Non-key joins, aliases without bound tables, nullable/partial unique indexes,
    outer right/full joins and multi-join expressions remain policy obligations.
    """
    import json
    if not join.get('closed') or join.get('join_type') not in ('Inner','LeftOuter'):return False
    left,right=join['left'],join['right']
    if not join.get('target') or join['target'][-1].lower()!=left['alias'].lower():return False
    def table(t):
        parts=t['parts']
        key=json.dumps((['dbo']+parts) if len(parts)==1 else parts,separators=(',',':'))
        return state['tables'].get(key)
    a,b=table(left),table(right)
    if not a or not b or not b['primary_key']:return False
    covered=set()
    for pair in join['equalities']:
        if len(pair)!=2 or any(len(x)!=2 for x in pair):return False
        x,y=pair
        if x[0].lower()==right['alias'].lower():x,y=y,x
        if x[0].lower()!=left['alias'].lower() or y[0].lower()!=right['alias'].lower():return False
        if x[1] not in [c[0] for c in a['columns']] or y[1] not in [c[0] for c in b['columns']]:return False
        covered.add(y[1])
    return set(b['primary_key'])<=covered


def reached_results(bound,observation):
    rules=bound.get('result_contracts')
    if rules is None:return None
    if not any(r.get('conditional') for r in rules):return rules
    coverage=observation.get('coverage')
    if not coverage:return None
    from .coverage_v2 import replay_coverage
    if not coverage['raw']['schema'].endswith('/2'):return None
    parsed=replay_coverage(coverage)
    modules=[m for m in parsed['modules'] if m['source_sha256']==bound['source_sha256']]
    if len(modules)!=1:return None
    hits=modules[0]['native_started_offsets_utf16']
    return [r for r in rules if not r.get('conditional') or any(r['start_utf16']<=p<r['start_utf16']+r['length_utf16'] for p in hits)]


def target_contract(source):
    from .postgresql_syntax_v8 import contract as pg_contract
    return pg_contract(source)


def resolve_results(bound, observation):
    """Compose exact catalogue-bound callees; cycles/dynamic/ambiguous origins fail closed.

    Repeated conditional/loop results are never guessed from rowset count. Their
    order needs invocation-specific events; unresolved remains an explicit issue.
    """
    from copy import deepcopy
    catalogue=observation.get('dependency_catalogue',{})
    parsed=catalogue.get('parsed',{});modules=catalogue.get('modules',[])
    def expand(current, seen):
        current=deepcopy(current);rules=reached_results(current,observation)
        if rules is None:
            current['policy_obligations'].append(dict(kind='conditional-result-origin-unresolved'))
            return current
        entries=[(r.get('start_utf16',0),[r]) for r in rules];closed=[]
        for call in current.get('exec_contracts',[]):
            if call.get('no_results_proven'):closed.append(call);continue
            parts=call.get('called_parts') or []
            callee=None
            if parts and parts[-1].lower()=='sp_executesql':
                # The root syntax copy and native module copy are separately bound.
                matches=[e for ast in parsed.values() if ast.get('input_sha256')==current['source_sha256']
                         for e in ast.get('semantic_catalogue',{}).get('exec_contracts',[])
                         if e.get('start_utf16')==call['start_utf16'] and e.get('literal_sql_sha256')==call.get('literal_sql_sha256')]
                if len(matches)==1:callee=matches[0].get('literal_parsed')
            elif 1<=len(parts)<=2:
                name=parts[-1].lower();schema=parts[0].lower() if len(parts)==2 else 'dbo'
                matches=[m for m in modules if m[1].lower()==schema and m[2].lower()==name and m[3]=='P']
                if len(matches)==1:
                    m=matches[0];callee=parsed.get(str(m[0]))
                    if callee and callee['input_sha256']!=sha(m[4].encode()):raise ValueError('callee-source-binding')
            if not callee or callee['input_sha256'] in seen:continue
            child=expand(contract(callee),seen|{callee['input_sha256']})
            if not child.get('result_producers_complete') or child['policy_obligations'] or child.get('conditional_results'):continue
            entries.append((call['start_utf16'],child['result_contracts']));closed.append(call)
        def covered(issue):
            span=issue.get('span',{})
            return issue['kind']=='unresolved-exec-result-origin' and any(c['start_utf16']<=span.get('start_utf16',-1) and span.get('start_utf16',-1)+span.get('length_utf16',0)<=c['start_utf16']+c['length_utf16'] for c in closed)
        current['policy_obligations']=[x for x in current['policy_obligations'] if not covered(x)]
        current['result_contracts']=[r for _,group in sorted(entries,key=lambda x:x[0]) for r in group]
        return current
    return expand(bound,{bound['source_sha256']})
