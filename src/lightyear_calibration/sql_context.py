"""Source-bound schema/session contracts for a deliberately small numeric DML domain.

A template is an acquisition baseline, not a database snapshot. Unknown catalog
facts remain unknown. Complete caller-supplied contracts authorize only a static
relational projection; they do not establish customer/runtime authenticity.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal
import re
from lightyear_data import idempiere_sql as sql
from .contracts import exact, require, sha, digest, label, seal

DML_REASON='dml-schema-trigger-and-coercion-context-required'
SESSION_KEYS={'current_schema','search_path','numeric_characters','time_zone','standard_conforming_strings'}
TABLE_KEYS={'kind','complete','columns','triggers','constraints','row_policies','rewrite_rules'}


def predicate(tokens,dialect):
    c=sql.Cursor(tokens)
    def atom():
        if c.pos<len(c.tokens) and c.tokens[c.pos].value=='(':
            return predicate(c.group(),dialect)
        column=c.name()
        if c.accept('is'):
            negate=c.accept('not');c.need('null')
            return {'kind':'is-not-null' if negate else 'is-null','column':column}
        if c.accept('in'):
            values=[sql.literal(v,dialect) for v in sql.comma_parts(c.group())]
            return {'kind':'in','column':column,'values':values}
        if c.pos>=len(c.tokens) or c.tokens[c.pos].kind!='symbol' or c.tokens[c.pos].value not in ('=','<>','!=','<','>','<=','>='):
            raise sql.Unsupported('predicate-outside-context-grammar')
        operator=c.tokens[c.pos].value;c.pos+=1;start=c.pos
        if c.pos<len(c.tokens) and c.tokens[c.pos].value in ('+','-') and c.tokens[c.pos].kind=='symbol':c.pos+=1
        if c.pos>=len(c.tokens):raise sql.Unsupported('missing-predicate-value')
        c.pos+=1
        return {'kind':'comparison','column':column,'operator':'<>' if operator=='!=' else operator,
                'value':sql.literal(c.tokens[start:c.pos],dialect)}
    def conjunction():
        values=[atom()]
        while c.accept('and'):values.append(atom())
        return values[0] if len(values)==1 else {'kind':'and','terms':values}
    values=[conjunction()]
    while c.accept('or'):values.append(conjunction())
    c.finish()
    return values[0] if len(values)==1 else {'kind':'or','terms':values}


def dml_value(unit,dialect):
    """Reparse a fully parsed DML unit into literals and a bounded predicate AST."""
    e=unit.effects[0]
    if e['kind']=='insert':return deepcopy(e['value'])
    tokens=unit.tokens[:-1] if unit.tokens[-1].value==';' else unit.tokens
    depth=0;where=None
    for i,t in enumerate(tokens):
        if t.kind=='symbol':depth+=(t.value=='(')-(t.value==')')
        if depth==0 and t.kind=='word' and t.value=='where':where=i;break
    pred=predicate(tokens[where+1:],dialect) if where is not None else {'kind':'all-rows'}
    return {'assignments':deepcopy(e['value']['assignments']),'predicate':pred} if e['kind']=='update' else pred


def baseline(snapshot, texts):
    """Inventory needed tables/columns and observed DDL, leaving catalog facts unset."""
    from .sql_parser import parse_script
    cases={}
    for item in snapshot['provenance']['inputs']:
        cid=item['case_id'];lanes={}
        for lane,side in (('oracle','source'),('postgresql','target')):
            tables={}; declarations=[]
            for unit in parse_script(texts[cid][side] or '',lane):
                for e in unit.effects:
                    if e['kind'] in ('insert','update','delete'):
                        table=e['target']
                        entry=tables.setdefault(table,{'kind':None,'complete':False,'columns':{},'triggers':None,
                                                      'constraints':None,'row_policies':None,'rewrite_rules':None})
                        cols=e['value'].keys() if e['kind']=='insert' else e['value']['assignments'].keys() if e['kind']=='update' else []
                        for col in cols:entry['columns'].setdefault(col,{'type':None,'nullable':None})
                        try:
                            value=dml_value(unit,lane)
                            def visit(v):
                                if isinstance(v,dict):
                                    if 'column' in v:entry['columns'].setdefault(v['column'],{'type':None,'nullable':None})
                                    for v2 in v.values():visit(v2)
                                elif isinstance(v,list):
                                    for v2 in v:visit(v2)
                            visit(value)
                        except sql.Unsupported:pass
                    elif e['facet'] in ('type','nullable'):
                        declarations.append({'target':e['target'],'facet':e['facet'],'value':e['value'],
                                             'lines':[unit.start_line,unit.end_line],'unit_sha256':unit.sha256})
            lanes[lane]={'session':{k:None for k in sorted(SESSION_KEYS)},'tables':tables,
                         'observed_declarations':declarations}
        cases[cid]={'inputs':{lane:item[side] for lane,side in (('oracle','source'),('postgresql','target'))},'lanes':lanes}
    return {'schema_version':'1.0','artifact_type':'lightyear-sql-context-baseline','corpus_sha256':snapshot['corpus_sha256'],
            'scope':'static-declared-dml','evidence':{'mode':'template','references':[]},'cases':cases}


def admit(context, corpus_sha256, inputs):
    exact(context,{'schema_version','artifact_type','corpus_sha256','scope','evidence','cases'})
    require(context['schema_version']=='1.0' and context['artifact_type']=='lightyear-sql-context-baseline'
            and context['scope']=='static-declared-dml','Unknown context contract')
    require(context['corpus_sha256']==corpus_sha256,'Stale context corpus binding')
    exact(context['evidence'],{'mode','references'})
    require(context['evidence']['mode'] in ('template','declared-contract','captured-catalog'),'Unknown context evidence mode')
    require(isinstance(context['evidence']['references'],list) and len(context['evidence']['references'])<=1000,'Invalid context evidence')
    if context['evidence']['mode']!='template':require(context['evidence']['references'],'Context needs evidence references')
    for ref in context['evidence']['references']:
        exact(ref,{'path','sha256'});label(ref['path'],1000);sha(ref['sha256'])
    require(isinstance(context['cases'],dict) and set(context['cases'])=={i['case_id'] for i in inputs},'Context must bind every case exactly')
    for item in inputs:
        case=context['cases'][item['case_id']];exact(case,{'inputs','lanes'})
        require(case['inputs']=={lane:item[side] for lane,side in (('oracle','source'),('postgresql','target'))},'Stale context input binding')
        exact(case['lanes'],{'oracle','postgresql'})
        for lane in case['lanes'].values():
            exact(lane,{'session','tables','observed_declarations'});exact(lane['session'],SESSION_KEYS)
            require(isinstance(lane['observed_declarations'],list),'Invalid source declarations')
            session=lane['session']
            for key in ('current_schema','numeric_characters','time_zone'):
                if session[key] is not None:label(session[key])
            require(session['standard_conforming_strings'] is None or type(session['standard_conforming_strings']) is bool,'Invalid string session setting')
            require(session['search_path'] is None or (isinstance(session['search_path'],list) and all(isinstance(v,str) and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*',v) for v in session['search_path'])),'Invalid search path')
            require(isinstance(lane['tables'],dict) and len(lane['tables'])<=20000,'Invalid table inventory')
            for name,table in lane['tables'].items():
                label(name);exact(table,TABLE_KEYS)
                require(table['kind'] in (None,'base-table','view') and type(table['complete']) is bool,'Invalid table kind/completeness')
                for key in ('triggers','constraints','row_policies','rewrite_rules'):
                    require(table[key] is None or isinstance(table[key],list),'Invalid catalog inventory')
                require(isinstance(table['columns'],dict) and len(table['columns'])<=20000,'Invalid columns')
                for col,spec in table['columns'].items():
                    label(col);exact(spec,{'type','nullable'})
                    require(spec['nullable'] is None or type(spec['nullable']) is bool,'Invalid nullability')
                    if spec['type'] is not None:
                        exact(spec['type'],{'canonical_type','precision','scale'})
                        t=spec['type']
                        require(t['canonical_type']=='exact-decimal' and type(t['precision']) is int and type(t['scale']) is int
                                and 1<=t['precision']<=38 and 0<=t['scale']<=t['precision'],'Unsupported context column domain')
    return context


def project(unit,lane,context_case,enabled):
    """Return contextual DML effect; any missing/unsafe fact remains a reason."""
    e=deepcopy(unit.effects[0]);context=context_case['lanes'][lane]
    reasons=set(e['reasons']); reasons.discard(DML_REASON)
    # Only literal predicates get upgraded. Opaque assignments and calls keep
    # their original blocker, even if their text looks identical across lanes.
    try:value=dml_value(unit,lane)
    except sql.Unsupported:
        e['reasons']=sorted(reasons|{'context-predicate-grammar-required'});return e
    if not enabled:reasons.add('context-evidence-required')
    session=context['session']
    table=context['tables'].get(e['target'])
    if (not session['current_schema'] or
            (lane=='oracle' and session['numeric_characters']!='.,') or
            (lane=='postgresql' and (session['search_path']!=[session['current_schema']] or
                                      session['standard_conforming_strings'] is not True))):
        reasons.add('schema-and-session-baseline-required')
    if '.' in e['target'] or '"' in e['target']:reasons.add('context-qualified-name-mapping-required')
    if not table or not table['complete'] or table['kind']!='base-table':
        reasons.add('complete-base-table-catalog-required')
    elif any(table[k]!=[] for k in ('triggers','constraints','row_policies','rewrite_rules')):
        reasons.add('catalog-side-effects-context-required')
    columns=table['columns'] if table else {}
    touched=set()
    def check(col,v,assignment=False):
        touched.add(col);spec=columns.get(col)
        if not spec or spec['type'] is None or spec['nullable'] is None:
            reasons.add('column-domain-context-required');return
        if v['kind']=='null':
            if assignment and not spec['nullable']:reasons.add('nullability-domain-violation')
        elif v['kind']=='number':
            number=Decimal(v['value']);t=spec['type']
            if number.copy_abs()>=Decimal(10)**(t['precision']-t['scale']) or max(0,-number.as_tuple().exponent)>t['scale']:
                reasons.add('numeric-coercion-or-overflow-context-required')
        else:reasons.add('context-expression-domain-unsupported')
    def pred(p):
        if p['kind'] in ('and','or'):
            for v in p['terms']:pred(v)
        elif 'column' in p:
            vals=p.get('values',[p.get('value',{'kind':'null'})])
            for v in vals:check(p['column'],v)
    if e['kind']=='insert':
        for col,v in value.items():check(col,v,True)
        if set(value)!=set(columns):reasons.add('insert-defaults-context-required')
    elif e['kind']=='update':
        for col,v in value['assignments'].items():check(col,v,True)
        pred(value['predicate'])
    else:pred(value)
    # The AST has no opaque predicate after successful parsing; remove only the
    # aggregate expression blocker and recompute it from every value above.
    reasons.discard('expression-requires-dialect-or-session-semantics')
    e['value']={'dml':value,'domains':{col:columns.get(col) for col in sorted(touched)}}
    e['reasons']=sorted(reasons)
    return e
