"""Bind captured raw fixture bytes to CICS aliases discovered in source READs.

Keys and physical fields use the pinned data plan, a disclosed shared schema
dependency. Screen behavior and expected writes use the separate raw interpreter.
"""
from copy import deepcopy
from .reference_control import Reader,Unsupported
from .reference_declarations import layout
from .reference_storage import Memory
from .reference_values import Values
from .reference_screens import RecordStore

def statements(program):
    def descend(body):
        for statement in body:
            yield statement
            if statement.verb=='IF':
                for child in statement.children:yield from descend(child)
            elif statement.verb=='EVALUATE':
                for _,child in statement.children:yield from descend(child)
            elif statement.verb=='LOOP':yield from descend(statement.children[0])
            elif statement.verb=='SEARCH':
                yield from descend(statement.children[1]);yield from descend(statement.children[2])
    for body in program.paragraphs.values():yield from descend(body)

def load(document,adapters,source_root):
    mappings={m['table']:m for m in document['plan']['mappings']};record_names={}
    for table,m in mappings.items():
        source=source_root/m['source'] if 'source' in m else None
        # Match data records using the generated field paths, not a handwritten alias table.
        roots={f['path'].split('.')[0] for f in m['fields']}
        for name in roots:record_names.setdefault(name,[]).append(table)
    aliases={}
    for adapter in adapters:
        memory=adapter.storage();values=Values(memory)
        for stmt in statements(adapter.program):
            if stmt.verb!='EXEC':continue
            kind,operation,o,flags=adapter.operands(stmt.operands)
            if kind!='CICS' or operation!='READ':continue
            dataset=str(values.value(o.get('DATASET',o.get('FILE')))).strip()
            target=o['INTO'][0].text;tables=record_names.get(target,[])
            if len(tables)!=1:raise Unsupported('reference READ record binding '+target)
            table=tables[0];length=int(values.value(o['KEYLENGTH'])) if 'KEYLENGTH' in o else memory.descriptor(values.reference(Reader(o['RIDFLD']))[0])[1]['length']
            keys=[k for k in mappings[table]['keys'] if k['key_length']==length]
            if len(keys)!=1:raise Unsupported('reference READ key binding '+dataset)
            selected=(table,keys[0]['key_offset'],length)
            if dataset in aliases and aliases[dataset]!=selected:raise Unsupported('conflicting source dataset alias')
            aliases[dataset]=selected
    records=[]
    for item in document['records']:
        raw=bytes.fromhex(item['raw']);table=item['table'];record=dict(identity=item['identity'],table=table,raw=raw,keys={})
        for dataset,(mapped,offset,length) in aliases.items():
            if mapped==table:record['keys'][dataset]=raw[offset:offset+length]
        if item['segment']:
            key=mappings[table]['keys'][0];record.update(segment=item['segment'],segment_key=raw[key['key_offset']:key['key_offset']+key['key_length']],parent=item['parent'])
        records.append(record)
    return RecordStore(records)
