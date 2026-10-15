"""Generate storage mappings from copybooks, IDCAMS and IMS DBD statements.

This is a bounded definition reader, not an IDCAMS/JCL executor or IMS emulator.
Unsupported storage declarations are rejected; they never become guessed columns.
"""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import re

from lightyear_mainframe.records import compile_copybook, LayoutError


def identifier(value):
    value = re.sub(r'[^a-z0-9_]', '_', value.lower())
    if not value or not re.fullmatch(r'[a-z][a-z0-9_]*', value):
        raise ValueError('unsafe SQL identifier')
    return value if len(value) <= 55 else value[:42] + '_' + sha256(value.encode()).hexdigest()[:12]


def quote(value):
    if identifier(value) != value:
        raise ValueError('noncanonical SQL identifier')
    return '"' + value + '"'


def pinned(root):
    root = Path(root)
    manifest = json.loads((root / 'provenance.json').read_bytes())
    if not re.fullmatch('[0-9a-f]{40}', manifest['commit']):
        raise ValueError('exact upstream commit required')
    for path, info in manifest['files'].items():
        dest = (root / 'upstream' / path).resolve()
        if not dest.is_relative_to((root / 'upstream').resolve()):
            raise ValueError('source path escape')
        data = dest.read_bytes()
        if len(data) != info['bytes'] or sha256(data).hexdigest() != info['sha256']:
            raise ValueError('pinned source mismatch: ' + path)
    return manifest


def idcams(text, source):
    # Read only in-stream SYSIN; JCL comments and DELETE statements are not definitions.
    lines = text.splitlines(); active = False; pieces = []
    for number, line in enumerate(lines, 1):
        if re.match(r'//SYSIN\s+DD\s+\*', line): active = True; continue
        if line.startswith('/*') or line.startswith('//'): active = False
        if active: pieces.append((number, line.rstrip().rstrip('-').strip()))
    code = ''; locations = []
    for number, line in pieces:
        code += line + ' '; locations.extend([number] * (len(line) + 1))
    definitions = []
    for match in re.finditer(r'\bDEFINE\s+(CLUSTER|ALTERNATEINDEX)\s*\(', code):
        start = match.end(); depth = 1; end = start
        while end < len(code) and depth:
            depth += (code[end] == '(') - (code[end] == ')'); end += 1
        if depth: raise ValueError('unclosed IDCAMS definition')
        body = code[start:end-1]
        name = re.search(r'\bNAME\(([^)]+)\)', body)
        size = re.search(r'\bRECORDSIZE\((\d+)[,\s]+(\d+)\)', body)
        key = re.search(r'\bKEYS\((\d+)[,\s]+(\d+)\)', body)
        if not name or not size: raise ValueError('IDCAMS name and record size required')
        kind = 'AIX' if match[1] == 'ALTERNATEINDEX' else ('ESDS' if re.search(r'\bNONINDEXED\b', body) else 'RRDS' if re.search(r'\bNUMBERED\b', body) else 'KSDS')
        if kind in ('KSDS', 'AIX') and not key: raise ValueError('key declaration missing')
        if re.search(r'\b(?:SPANNED|LINEAR)\b', body): raise ValueError('unsupported VSAM organization')
        relate = re.search(r'\bRELATE\(([^)]+)\)', body)
        definitions.append(dict(name=name[1], kind=kind, minimum=int(size[1]), maximum=int(size[2]),
            key_length=int(key[1]) if key else None, key_offset=int(key[2]) if key else None,
            unique=not bool(re.search(r'\bNONUNIQUEKEY\b', body)),
            relate=relate[1] if relate else None, source=source, line=locations[match.start()]))
    if not definitions: raise ValueError('no supported IDCAMS definitions')
    return definitions


def copybook(text, source, *, segment=None):
    # IMS COPY members start at level 05. Add one declared enclosing record;
    # preserve physical source line numbers by adjusting only generated locations.
    wrapped = segment is not None
    layout = compile_copybook(('       01 ' + segment + '.\n' if wrapped else '') + text, source)
    return layout, int(wrapped)


def mapping(name, layout, source, definitions, line_shift=0):
    base = [d for d in definitions if d['kind'] != 'AIX']
    if len(base) != 1: raise ValueError('select exactly one VSAM/segment definition')
    base = base[0]
    if base['maximum'] != layout.record_length or base['minimum'] != (layout.minimum_length if layout.variable else layout.record_length):
        raise ValueError('copybook/definition record length mismatch')
    if layout.overlays:
        raise LayoutError('REDEFINES requires reviewed discriminator and live-reader policy; migration unsupported')
    name = identifier(name); fields = []; children = {}; seen = set()
    for f in layout.fields:
        row = asdict(f); row['line'] -= line_shift; row['source'] = source
        repeated = re.search(r'\[(\d+)\]', f.path)
        if len(re.findall(r'\[', f.path)) > 1: raise LayoutError('nested OCCURS migration unsupported')
        row['table'] = name; row['ordinal'] = None
        if repeated:
            group = f.path[:repeated.start()]
            table = identifier(name + '_' + group)
            row['table'] = table; row['ordinal'] = int(repeated[1])
            children[table] = {'path': group, 'source': source, 'line': row['line']}
        row['column'] = identifier(re.sub(r'\[\d+\]', '', f.path))
        row['sql_type'] = f'numeric({f.digits},{f.scale})' if f.digits else f'char({f.length})'
        row['date'] = not f.digits and f.length == 10 and f.path.endswith('-DATE')
        if row['date']: row['sql_type'] = 'date'
        identity = (row['table'], row['column'], row['ordinal'])
        if identity in seen and not f.filler: raise ValueError('generated column collision')
        seen.add(identity); fields.append(row)
    keys = []
    for d in definitions:
        if d['kind'] == 'AIX' and d['relate'] != base['name']: raise ValueError('alternate index targets another cluster')
        if d['key_length'] is None: continue
        if d['key_length'] <= 0 or d['key_offset'] < 0 or d['key_offset'] + d['key_length'] > layout.minimum_length:
            raise ValueError('key outside fixed prefix')
        keys.append({**d, 'column': 'ebcdic_key' if d['kind'] != 'AIX' else 'ebcdic_key_aix_' + str(len(keys))})
    return dict(schema='mainframe-data-mapping/1', table=name, source=source,
        copybook_sha256=layout.copybook_sha256, definition=base, fields=fields,
        children=children, keys=keys, variable=layout.variable,
        minimum_length=layout.minimum_length, record_length=layout.record_length)


def ddl(m):
    q = quote; table = m['table']; primary = 'ebcdic_key' if m['keys'] else 'rba' if m['definition']['kind']=='ESDS' else 'slot'
    columns = ['source_ordinal bigint NOT NULL UNIQUE', 'encoding_meta jsonb NOT NULL', 'source_sha256 char(64) NOT NULL']
    if not m['keys']: columns += [q(primary) + ' bigint PRIMARY KEY CHECK (' + q(primary) + ' >= 0)']
    for key in m['keys']:
        columns.append(q(key['column']) + ' bytea NOT NULL' + (' PRIMARY KEY' if key['column']==primary else ''))
    if m.get('segment'):
        columns += ['path_key bytea NOT NULL UNIQUE', 'parent_path_key bytea', 'twin_seq bigint NOT NULL CHECK (twin_seq >= 0)']
        if m['segment']['parent']:
            columns.append('FOREIGN KEY (parent_path_key) REFERENCES ' + q(identifier(m['segment']['parent'])) + '(path_key)')
            columns.append('CHECK (parent_path_key IS NOT NULL)')
    for f in m['fields']:
        if f['filler'] or f['table'] != table: continue
        columns.append(q(f['column']) + ' ' + f['sql_type'] + ' NOT NULL')
        if f['date']: columns.append(q(f['column'] + '_raw') + ' char(10) NOT NULL')
    statements = ['CREATE TABLE ' + q(table) + ' (\n  ' + ',\n  '.join(columns) + '\n);']
    for child in m['children']:
        cols = ['source_ordinal bigint NOT NULL REFERENCES '+q(table)+'(source_ordinal) ON DELETE CASCADE', 'ordinal integer NOT NULL CHECK (ordinal > 0)']
        seen = set()
        for f in m['fields']:
            if f['table'] != child or f['filler'] or f['column'] in seen: continue
            seen.add(f['column']); cols.append(q(f['column']) + ' ' + f['sql_type'] + ' NOT NULL')
            if f['date']: cols.append(q(f['column'] + '_raw') + ' char(10) NOT NULL')
        cols.append('PRIMARY KEY (source_ordinal, ordinal)')
        statements.append('CREATE TABLE '+q(child)+' ('+', '.join(cols)+');')
    for k in m['keys']:
        statements.append('CREATE ' + ('UNIQUE ' if k['unique'] else '') + 'INDEX ON '+q(table)+' ('+q(k['column'])+');')
    if m.get('segment'):
        statements.append('CREATE INDEX ON '+q(table)+' (parent_path_key, twin_seq);')
    statements.append('CREATE TABLE '+q('quarantine_'+table)+' (source_ordinal bigint PRIMARY KEY, raw_record bytea NOT NULL, reason text NOT NULL, source_sha256 char(64) NOT NULL);')
    return '\n'.join(statements) + '\n'


def dbd(text, source):
    statements = []; current = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith('*'): continue
        code = line[:71].rstrip()
        match = re.match(r'^\s*(?:(\w+)\s+)?(DBD|DATASET|SEGM|FIELD|LCHILD|XDFLD|DBDGEN|FINISH|END|TITLE)\s*(.*)$', code)
        if match:
            current = dict(op=match[2], text=match[3], line=number, source=source); statements.append(current)
        elif current and line[:15].isspace(): current['text'] += code.strip()
        else: raise ValueError('unsupported DBD statement at line '+str(number))
    segments = []; current = None; relationships = []
    for s in statements:
        body = s['text']
        if s['op'] == 'SEGM':
            name = re.search(r'NAME=(\w+)', body); length = re.search(r'BYTES=(\d+)', body)
            parent = re.search(r'PARENT=\(*([A-Z0-9]+)', body)
            if not all((name, length, parent)): raise ValueError('incomplete segment definition')
            current = dict(name=name[1], length=int(length[1]), parent=None if parent[1]=='0' else parent[1], sequence=None, statement=s)
            if current['parent'] and current['parent'] not in {x['name'] for x in segments}: raise ValueError('unknown or forward parent')
            segments.append(current)
        elif s['op'] == 'FIELD':
            if current is None: raise ValueError('FIELD without segment')
            seq = re.search(r'NAME=\((\w+),SEQ,([UM])\)', body)
            if seq:
                start = re.search(r'START=(\d+)',body); size = re.search(r'BYTES=(\d+)',body)
                if not start or not size: raise ValueError('incomplete sequence field')
                current['sequence'] = dict(name=seq[1], unique=seq[2]=='U', offset=int(start[1])-1, length=int(size[1]), statement=s)
        elif s['op'] in ('LCHILD','XDFLD'): relationships.append(s)
    if not segments or sum(s['parent'] is None for s in segments)!=1: raise ValueError('one root segment required')
    return dict(segments=segments, relationships=relationships,
        unsupported=[{'reason':'logical/index relationship requires explicit target DBD resolution', **s} for s in relationships])
