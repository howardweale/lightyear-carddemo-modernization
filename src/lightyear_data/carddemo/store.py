"""PostgreSQL COPY loading and ordered data access over generated mappings."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json

from .codec import project, reconstruct
from .schema import quote


class Store:
    def __init__(self, connection, mapping, layout):
        self.connection, self.mapping, self.layout = connection, mapping, layout
        self.table = mapping['table']

    def _copy(self, table, row):
        from psycopg.types.json import Jsonb
        cols = list(row)
        with self.connection.cursor() as cursor:
            with cursor.copy('COPY '+quote(table)+' ('+', '.join(map(quote,cols))+') FROM STDIN') as stream:
                stream.write_row(tuple(Jsonb(v) if isinstance(v,dict) else v for v in row.values()))

    def load_one(self, raw, ordinal, *, position=None, parent_path=None, twin_seq=None):
        # Savepoint ensures a COPY or child constraint failure never leaves half a record.
        try:
            data = project(self.layout, self.mapping, raw)
            m = self.mapping
            row = dict(source_ordinal=ordinal, encoding_meta=data['metadata'], source_sha256=data['source_sha256'])
            for k in m['keys']: row[k['column']] = raw[k['key_offset']:k['key_offset']+k['key_length']]
            if not m['keys']:
                if position is None or type(position) is not int or position < 0: raise ValueError('captured RBA/slot required')
                row['rba' if m['definition']['kind']=='ESDS' else 'slot'] = position
            if m.get('segment'):
                if twin_seq is None or type(twin_seq) is not int or twin_seq < 0: raise ValueError('captured twin sequence required')
                key = row.get('ebcdic_key', twin_seq.to_bytes(8,'big'))
                row.update(path_key=(parent_path or b'')+key, parent_path_key=parent_path, twin_seq=twin_seq)
                if 'ebcdic_key' in row: row['ebcdic_key'] = row['path_key']
                if bool(m['segment']['parent']) != (parent_path is not None): raise ValueError('parent scope mismatch')
            children = {}
            for f in m['fields']:
                if f['filler'] or f['path'] not in data['values']: continue
                target = row if f['table']==self.table else children.setdefault((f['table'],f['ordinal']),dict(source_ordinal=ordinal,ordinal=f['ordinal']))
                value = data['values'][f['path']]
                target[f['column']] = date.fromisoformat(value) if f['date'] else value
                if f['date']: target[f['column']+'_raw'] = value
            with self.connection.transaction():
                self._copy(self.table,row)
                for (table,_),child in children.items(): self._copy(table,child)
            return dict(status='loaded', source_ordinal=ordinal, path_key=row.get('path_key'))
        except Exception as error:
            # Connection/infrastructure faults are not data quarantine events.
            from psycopg import DataError, IntegrityError
            if not isinstance(error,(ValueError, UnicodeError, DataError, IntegrityError)): raise
            reason = type(error).__name__ + ': ' + str(error).split('\n')[0]
            # SQL diagnostics can include public sign-on values; receipts expose counts only.
            if isinstance(error, (DataError, IntegrityError)): reason = type(error).__name__ + ':' + str(error.sqlstate)
            self._copy('quarantine_'+self.table,dict(source_ordinal=ordinal,raw_record=raw,reason=reason,source_sha256=sha256(raw).hexdigest()))
            return dict(status='quarantined',source_ordinal=ordinal,reason=reason)

    def rows(self):
        from psycopg.rows import dict_row
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM '+quote(self.table)+' ORDER BY source_ordinal')
            return cursor.fetchall()

    def values(self, row):
        from psycopg.rows import dict_row
        children = {}
        for table in self.mapping['children']:
            with self.connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute('SELECT * FROM '+quote(table)+' WHERE source_ordinal=%s ORDER BY ordinal',(row['source_ordinal'],))
                for child in cursor: children[(table,child['ordinal'])]=child
        active = {f['path'] for f in row['encoding_meta']['active']}
        values = {}
        for f in self.mapping['fields']:
            if f['filler'] or f['path'] not in active: continue
            source = row if f['table']==self.table else children[(f['table'],f['ordinal'])]
            value = source[f['column']]
            if f['date']:
                raw = source[f['column']+'_raw']
                if value.isoformat() != raw: raise ValueError('typed date/raw date mismatch')
                value = raw
            values[f['path']] = value
        return values

    def bytes(self, row):
        return reconstruct(self.mapping,self.values(row),row['encoding_meta'])

    def browse(self, key_column='ebcdic_key', *, start=None, prefix=None, reverse=False):
        # Key names come exclusively from the generated plan; no caller SQL fragments.
        if key_column not in {k['column'] for k in self.mapping['keys']}: raise ValueError('unknown browse key')
        clauses=[];params=[]; key=quote(key_column)
        if start is not None: clauses.append(key+(' <= %s' if reverse else ' >= %s'));params.append(start)
        if prefix is not None: clauses.append('substring('+key+' from 1 for %s) = %s');params.extend([len(prefix),prefix])
        direction=' DESC' if reverse else ' ASC'
        sql='SELECT source_ordinal FROM '+quote(self.table)
        if clauses: sql+=' WHERE '+' AND '.join(clauses)
        sql+=' ORDER BY '+key+direction+', ebcdic_key'+direction
        with self.connection.cursor() as cursor:
            cursor.execute(sql,params)
            return [r[0] for r in cursor]

    def totals(self):
        # Decimal SUM executes in PostgreSQL, independently of decoder-side totals.
        totals={}
        with self.connection.cursor() as cursor:
            for f in self.mapping['fields']:
                if f['filler'] or not f['digits'] or f['ordinal'] not in (None,1):continue
                cursor.execute('SELECT COALESCE(SUM('+quote(f['column'])+'),0) FROM '+quote(f['table']))
                totals[f['table']+'.'+f['column']] = cursor.fetchone()[0]
        return totals
