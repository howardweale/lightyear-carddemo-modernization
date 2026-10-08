"""PostgreSQL/PLpgSQL AST contracts. No keyword scan establishes ordering.

Pinned pglast 7.10; unsupported dynamic result construction remains unresolved.
SQL expressions extracted from the PLpgSQL parser are parsed again as SQL ASTs.
"""
import json
from importlib.metadata import version
from .native_evidence import sha,canonical


def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values():yield from walk(child)
    elif isinstance(value,(list,tuple)):
        for child in value:yield from walk(child)


def contract(source):
    if version('pglast')!='7.10':raise ValueError('pinned-postgresql-parser-required')
    from pglast import parse_plpgsql
    from pglast.parser import parse_sql_json
    rules=[];issues=set();trees=[]
    def sql(query,result=False):
        try:tree=json.loads(parse_sql_json(query))
        except Exception:
            issues.add('target-expression-parse-unresolved');return
        trees.append(tree)
        for item in walk(tree):
            if 'SelectStmt' in item:
                select=item['SelectStmt']
                if select.get('limitCount') or select.get('limitOffset'):issues.add('target-limit-selection-unproven')
                if any(v for v in select.get('distinctClause',[])):issues.add('target-distinct-on-selection-unproven')
            if 'FuncCall' in item:
                call=item['FuncCall'];name='.'.join(v['String']['sval'] for v in call['funcname']).lower().split('.')[-1]
                if name in {'row_number','lag','lead','first_value','last_value'}:issues.add('target-window-order-unproven')
                if name in {'array_agg','string_agg','json_agg','jsonb_agg','xmlagg'} and not call.get('agg_order'):issues.add('target-aggregate-order-unproven')
                if name in {'now','clock_timestamp','statement_timestamp','transaction_timestamp','random','gen_random_uuid','uuid_generate_v4'}:issues.add('target-nondeterminism-policy-required')
            if 'SQLValueFunction' in item:issues.add('target-nondeterminism-policy-required')
            if 'RangeTableSample' in item:issues.add('target-sample-selection-unproven')
        if result:
            statements=tree['stmts']
            if len(statements)!=1 or 'SelectStmt' not in statements[0]['stmt']:
                issues.add('target-result-producer-unresolved');return
            select=statements[0]['stmt']['SelectStmt'];first=select
            while first.get('larg'):first=first['larg']
            outputs=first.get('targetList',[]);keys=[];resolved=True
            for entry in select.get('sortClause',[]):
                expr=entry['SortBy']['node'];matches=[]
                def strip(v):
                    if isinstance(v,dict):return {k:strip(x) for k,x in v.items() if k not in {'location','stmt_location','stmt_len'}}
                    if isinstance(v,list):return [strip(x) for x in v]
                    return v
                # Bind a closed, explicit lower()/COLLATE expression to its
                # exact projected column. Other expressions remain unresolved.
                bound_expr=expr
                if 'CollateClause' in bound_expr:bound_expr=bound_expr['CollateClause']['arg']
                call=bound_expr.get('FuncCall')
                if call and [x['String']['sval'] for x in call['funcname']]==['lower'] and len(call.get('args',[]))==1:
                    bound_expr=call['args'][0]
                ordinal=expr.get('A_Const',{}).get('ival',{}).get('ival')
                if ordinal is not None:matches=[ordinal-1] if 0<ordinal<=len(outputs) else []
                else:
                    fields=bound_expr.get('ColumnRef',{}).get('fields',[])
                    alias=fields[0].get('String',{}).get('sval') if len(fields)==1 else None
                    for i,output in enumerate(outputs):
                        target=output['ResTarget']
                        if strip(target['val'])==strip(bound_expr) or alias and target.get('name')==alias:matches.append(i)
                if len(matches)!=1:resolved=False;keys.append(-1)
                else:keys.append(matches[0])
            rules.append(dict(ordered=bool(select.get('sortClause')),resolved=resolved,key_indices=keys))
    try:
        outer=json.loads(parse_sql_json(source));trees.append(outer)
        functions=[n['CreateFunctionStmt'] for n in walk(outer) if 'CreateFunctionStmt' in n]
        if not functions:sql(source,True)
        else:
            for function in functions:
                options={o['DefElem']['defname']:o['DefElem']['arg'] for o in function['options']}
                language=options.get('language',{}).get('String',{}).get('sval')
                if language=='sql':
                    body=options['as'][0]['String']['sval'];sql(body,True);continue
                if language!='plpgsql':issues.add('target-language-unresolved');continue
                pl=parse_plpgsql(source);trees.append(pl)
                result_queries=set()
                for node in walk(pl):
                    if 'PLpgSQL_stmt_return_query' in node:
                        query=node['PLpgSQL_stmt_return_query'].get('query',{}).get('PLpgSQL_expr',{}).get('query')
                        if query:result_queries.add(query);sql(query,True)
                        else:issues.add('target-dynamic-result-unresolved')
                    if 'PLpgSQL_stmt_dynexecute' in node or 'PLpgSQL_stmt_return_next' in node:
                        issues.add('target-dynamic-or-incremental-result-unresolved')
                for node in walk(pl):
                    if 'PLpgSQL_expr' in node:
                        expression=node['PLpgSQL_expr'];query=expression['query']
                        if query in result_queries:continue
                        mode=expression.get('parseMode',0)
                        if mode==0:sql(query)
                        elif mode==2:sql('SELECT '+query)
                        elif mode==3:
                            # Assignment target is bound by PLpgSQL; parse its RHS.
                            if ':=' in query:sql('SELECT '+query.split(':=',1)[1])
                            else:issues.add('target-assignment-parse-unresolved')
    except Exception:
        issues.add('target-syntax-unresolved')
    return dict(schema='postgresql-syntax-contract/2',source_sha256=sha(source.encode()),
        parser='pglast-7.10',parser_output_sha256=sha(canonical(trees)),result_contracts=rules,
        policy_obligations=sorted(issues),determinism_proven=not issues)
