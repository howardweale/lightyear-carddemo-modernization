"""Calibrated SQL grammar; the retained audit's versioned parser stays unchanged.

Statement splitting, literal distinctions and total-consumption rules are shared
with the original gate. Added syntax retains catalog/domain obligations.
"""
from __future__ import annotations

from dataclasses import replace
from lightyear_data import idempiere_sql as old


def datatype(c, dialect):
    national = dialect == 'oracle' and (c.is_word('nvarchar2') or c.is_word('nchar'))
    if national:
        tokens = list(c.tokens)
        tokens[c.pos] = replace(tokens[c.pos], value='varchar2' if c.is_word('nvarchar2') else 'char')
        sub = old.Cursor(tokens); sub.pos = c.pos
        value = old.type_spec(sub, dialect); c.pos = sub.pos
        if value['length_unit']!='session':raise old.Unsupported('invalid-national-character-length-unit')
        value.update(length_unit='char', character_set='national')
        return value
    return old.type_spec(c, dialect)


def column(c, table, mode, dialect):
    target = table+'.'+c.name()
    effects = []
    if mode == 'add' or not any(c.is_word(w) for w in ('default','not','null')):
        value = datatype(c, dialect)
        effects.append(old.effect(mode,target,'type',value,
            ['national-character-domain-context-required'] if value.get('character_set') else []))
    seen = set()
    while c.pos < len(c.tokens):
        if c.accept('default'):
            if 'default' in seen: raise old.Unsupported('duplicate-column-clause')
            seen.add('default'); start=c.pos; depth=0
            while c.pos<len(c.tokens):
                t=c.tokens[c.pos]
                if depth==0 and c.pos>start and any(c.is_word(w) for w in ('not','null','constraint','primary','unique')):break
                if t.kind=='symbol':depth+=(t.value=='(')-(t.value==')')
                c.pos+=1
            value,reasons=old.expression(c.tokens[start:c.pos],dialect)
            effects.append(old.effect(mode,target,'default',value,reasons))
        elif c.is_word('not') or c.is_word('null'):
            if 'nullable' in seen:raise old.Unsupported('duplicate-column-clause')
            seen.add('nullable'); nullable=not c.accept('not');c.need('null')
            effects.append(old.effect(mode,target,'nullable',nullable))
        else:raise old.Unsupported('unsupported-column-clause')
    if not effects:raise old.Unsupported('empty-column-change')
    return effects


def constraint(tokens, table, dialect):
    # Only a trailing, fully parsed deferral clause may be peeled off. Its
    # semantics are retained, never erased to make two definitions match.
    depth=0; start=None
    for i,t in enumerate(tokens):
        if t.kind=='symbol':depth+=(t.value=='(')-(t.value==')')
        if depth==0 and t.kind=='word' and t.value in ('deferrable','initially','not','enable','disable','validate','novalidate'):
            start=i;break
    if start is None:return old.constraint(old.Cursor(tokens),table)
    c=old.Cursor(tokens[start:]);defer=False;initial='immediate';seen=set()
    while c.is_word('not') or c.is_word('deferrable') or c.is_word('initially'):
        if c.accept('initially'):
            key='initially'
            if c.accept('deferred'):initial='deferred'
            else:c.need('immediate')
        else:
            key='deferrable'
            if c.accept('not'):c.need('deferrable')
            else:c.need('deferrable');defer=True
        if key in seen:raise old.Unsupported('duplicate-deferral-clause')
        seen.add(key)
    enabled=True;validated=True
    if dialect=='oracle':
        if c.accept('disable'):enabled=False
        else:c.accept('enable')
        if c.accept('novalidate'):validated=False
        else:c.accept('validate')
    c.finish()
    if initial=='deferred' and not defer:raise old.Unsupported('invalid-deferral-clause')
    effects=old.constraint(old.Cursor(tokens[:start]),table)
    for e in effects:
        e['value'].update(deferrable=defer,initially=initial,enabled=enabled,validated=validated)
        if not enabled or not validated:e['reasons'].append('constraint-state-context-required')
    return effects


def parse_statement(tokens,dialect):
    try:
        effects,admin=old.parse_statement(tokens,dialect)
    except old.Unsupported as original:
        c=old.Cursor(tokens)
        if not c.accept('alter') or not c.accept('table'):raise original
        table=c.qualified()
        if c.accept('add'):
            if dialect=='postgresql':c.accept('column')
            if any(c.is_word(w) for w in ('constraint','primary','foreign','unique')):
                return constraint(c.tokens[c.pos:],table,dialect),False
            mode='add'
        elif dialect=='oracle' and c.accept('modify'):mode='modify'
        elif dialect=='oracle' and c.accept('drop'):
            columns=old.names(c.group());c.finish()
            return [old.effect('drop',table+'.'+n,'column',True,['baseline-object-required']) for n in columns],False
        elif c.accept('rename'):
            c.need('column');name=c.name();c.need('to');new=c.name();c.finish()
            return [old.effect('rename',table+'.'+name,'column',new,['baseline-object-required'])],False
        else:raise original
        if c.pos<len(tokens) and tokens[c.pos].value=='(':
            if dialect!='oracle':raise old.Unsupported('oracle-only-add-column-list')
            effects=[]
            for part in old.comma_parts(c.group()):effects.extend(column(old.Cursor(part),table,mode,dialect))
        else:effects=column(c,table,mode,dialect)
        c.finish();admin=False
    # Explicit defaults prevent omitted deferrability being equated to deferred.
    for e in effects:
        if e['kind']=='constraint':
            e['value'].setdefault('deferrable',False)
            e['value'].setdefault('initially','immediate')
            e['value'].setdefault('enabled',True)
            e['value'].setdefault('validated',True)
    return effects,admin


def parse_script(sql,dialect):
    if dialect not in ('oracle','postgresql'):raise ValueError('Unknown SQL dialect')
    units=old.split_units(sql,dialect)
    for u in units:
        if u.lexical_error:u.reasons=[u.lexical_error];continue
        tokens=u.tokens[:-1] if u.tokens and u.tokens[-1].value==';' and u.tokens[-1].kind=='symbol' else u.tokens
        try:
            u.effects,u.administrative=parse_statement(tokens,dialect);u.parsed=True
        except old.Unsupported as exc:u.reasons=[str(exc)]
    return units
