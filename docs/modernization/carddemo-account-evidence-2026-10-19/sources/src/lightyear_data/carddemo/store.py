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

    def load_one(self, raw, ordinal, *, position=None, parent_path=None, twin_seq=None, quarantine=True):
        # Savepoint ensures a COPY or child constraint failure never leaves half a record.
        try:
            row,children = self.project_rows(raw,ordinal,position=position,parent_path=parent_path,twin_seq=twin_seq)
            with self.connection.transaction():
                self._copy(self.table,row)
                for (table,_),child in children.items(): self._copy(table,child)
            return dict(status='loaded', source_ordinal=ordinal, path_key=row.get('path_key'))
        except Exception as error:
            if not quarantine: raise
            # Connection/infrastructure faults are not data quarantine events.
            from psycopg import DataError, IntegrityError
            if not isinstance(error,(ValueError, UnicodeError, DataError, IntegrityError)): raise
            reason = type(error).__name__ + ': ' + str(error).split('\n')[0]
            # SQL diagnostics can include public sign-on values; receipts expose counts only.
            if isinstance(error, (DataError, IntegrityError)): reason = type(error).__name__ + ':' + str(error.sqlstate)
            self._copy('quarantine_'+self.table,dict(source_ordinal=ordinal,raw_record=raw,reason=reason,source_sha256=sha256(raw).hexdigest()))
            return dict(status='quarantined',source_ordinal=ordinal,reason=reason)

    def project_rows(self,raw,ordinal,*,position=None,parent_path=None,twin_seq=None):
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
            target[f['column']] = (date.fromisoformat(value) if f['date'] else
                value.encode(data['metadata']['codec']) if not f['digits'] else value)
            if f['date']: target[f['column']+'_raw'] = value
        return row,children

    def find(self,column,value,*,lock=False):
        from psycopg.rows import dict_row
        if column not in ('ebcdic_key','source_ordinal','path_key'):raise ValueError('unknown lookup')
        with self.connection.cursor(row_factory=dict_row) as c:
            c.execute('SELECT * FROM '+quote(self.table)+' WHERE '+quote(column)+'=%s'+(' FOR UPDATE' if lock else ''),(value,))
            return c.fetchone()

    def replace(self,old,raw):
        from psycopg.types.json import Jsonb
        row,children=self.project_rows(raw,old['source_ordinal'],position=old.get('rba',old.get('slot')),
            parent_path=old.get('parent_path_key'),twin_seq=old.get('twin_seq'))
        with self.connection.transaction():
            columns=[c for c in row if c!='source_ordinal']
            self.connection.execute('UPDATE '+quote(self.table)+' SET '+','.join(quote(c)+'=%s' for c in columns)+' WHERE source_ordinal=%s',
                [Jsonb(row[c]) if isinstance(row[c],dict) else row[c] for c in columns]+[old['source_ordinal']])
            for table in self.mapping['children']:
                self.connection.execute('DELETE FROM '+quote(table)+' WHERE source_ordinal=%s',(old['source_ordinal'],))
            for (table,_),child in children.items():self._copy(table,child)

    def load_many(self,records):
        """Atomic COPY for generated valid fixed records; no quarantine bypass for bad data."""
        from psycopg.types.json import Jsonb
        if self.mapping['children'] or self.mapping.get('segment'):raise ValueError('bulk shape unsupported')
        with self.connection.transaction(),self.connection.cursor() as cursor:
            stream=None
            # Derive all columns from the generated mapping, using the first projected row.
            iterator=iter(enumerate(records,1));first=next(iterator,None)
            if first is None:return 0
            row,_=self.project_rows(first[1],first[0]);cols=list(row)
            with cursor.copy('COPY '+quote(self.table)+' ('+','.join(map(quote,cols))+') FROM STDIN') as stream:
                def write(row):stream.write_row(tuple(Jsonb(row[c]) if isinstance(row[c],dict) else row[c] for c in cols))
                write(row);count=1
                for i,raw in iterator:
                    row,_=self.project_rows(raw,i);write(row);count+=1
        return count

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
            elif not f['digits']:
                value = bytes(value).decode(row['encoding_meta']['codec'])
            values[f['path']] = value
        return values

    def bytes(self, row):
        return reconstruct(self.mapping,self.values(row),row['encoding_meta'])

    def browse(self, key_column='ebcdic_key', *, start=None, prefix=None, reverse=False):
        # Key names come exclusively from the generated plan; no caller SQL fragments.
        if key_column not in {k['column'] for k in self.mapping['keys']}: raise ValueError('unknown browse key')
        clauses=[];params=[]; key=quote(key_column)
        if start is not None: clauses.append(key+(' <= %s' if reverse else ' >= %s'));params.append(start)
        if prefix is not None:
            # Generic READNEXT positions at the lower bound and continues to EOF.
            # Reverse positions at the end of the generic range then continues down.
            width = next(k['key_length'] for k in self.mapping['keys'] if k['column']==key_column)
            if len(prefix)>width: raise ValueError('generic key too long')
            bound = prefix.ljust(width,b'\xff') if reverse else prefix
            clauses.append(key+(' <= %s' if reverse else ' >= %s'));params.append(bound)
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
