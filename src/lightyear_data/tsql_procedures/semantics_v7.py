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
    # A caller's AST cannot establish the order of a callee/dynamic result.
    # Dependency parsing must supply a future result-origin contract; refuse now.
    for n in nodes:
        if n['kind'] in {'ExecuteStatement','ExecutableProcedureReference','ExecutableStringList'}:
            obligations.append(dict(kind='unresolved-exec-result-origin',span=n))
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


def target_contract(source):
    """Conservative lexical refusal only; never establishes target determinism.

    PL/pgSQL is not parsed as T-SQL. Unresolved LIMIT selection, assignment,
    aggregate/window order and volatile clock/random calls stay policy gated.
    """
    from .inventory import tokens
    import re
    code=' '.join(t['value'].upper() if t['kind']!='string' else 'LITERAL' for t in tokens(source))
    kinds=[]
    for pattern,kind in [(r'\bLIMIT\b','target-limit-selection-unproven'),
                         (r'\bROW_NUMBER\s*\(','target-row-number-uniqueness-unproven'),
                         (r'\bSTRING_AGG\s*\(','target-string-agg-order-unproven'),
                         (r'\b(?:CURRENT_TIMESTAMP|CLOCK_TIMESTAMP|NOW|RANDOM|GEN_RANDOM_UUID|UUID_GENERATE_V4)\b','target-nondeterminism-policy-required')]:
        if re.search(pattern,code):kinds.append(kind)
    return dict(schema='postgresql-refusal-contract/1',source_sha256=sha(source.encode()),policy_obligations=kinds,determinism_proven=False)
