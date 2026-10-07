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
    for top in (n for n in nodes if n['kind'] == 'TopRowFilter'):
        queries = [n for n in nodes if n['kind'] in ('QuerySpecification','QueryParenthesisExpression') and inside(top,n)]
        query = min(queries,key=lambda n:n['length_utf16']) if queries else None
        # Query-expression ORDER BY may follow the query-specification span.
        selects = [n for n in nodes if n['kind']=='SelectStatement' and inside(top,n)]
        parent = min(selects,key=lambda n:n['length_utf16']) if selects else query
        nested = [n for n in nodes if n['kind']=='QuerySpecification'
                  and parent and inside(n,parent) and n != query]
        if parent is None or not any(inside(o,parent) and not any(inside(o,n) for n in nested) for o in orders):
            obligations.append(dict(kind='unordered-top',span=top))
    for update in (n for n in nodes if n['kind']=='UpdateSpecification'):
        if contained('FromClause',update):
            obligations.append(dict(kind='update-from-cardinality-unproven',span=update))
    extra = ast.get('semantic_catalogue', {})
    for name in extra.get('nondeterministic_functions',[]):
        obligations.append(dict(kind='nondeterminism-policy-required',function=name))
    return dict(schema='tsql-syntax-contract/1',source_sha256=ast['input_sha256'],
                parser_version=ast['version'],parser_output_sha256=sha(canonical(ast)),
                order_by_present=bool(orders),order_spans=orders,policy_obligations=obligations,
                procedures=extra.get('procedures',[]),dependencies=extra.get('dependencies',[]))


def verify_contract(value, parsed):
    if value != contract(parsed):raise ValueError('syntax-contract-replay-mismatch')
    return value
