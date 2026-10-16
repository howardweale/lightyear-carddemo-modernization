"""Bounded PostgreSQL VSAM byte-record and two-level DL/I access adapters.

These adapters operate inside the caller's transaction. They do not emulate CICS
locking, IMS checkpoints, utility unload framing, or restart recovery.
"""
from .schema import quote
from .store import Store


class VsamRepository:
    def __init__(self, connection, mapping):
        self.connection,self.mapping=connection,mapping
        self.store=Store(connection,mapping,None)
        self.cursor=None

    def read(self, key):
        row=self.connection.execute('SELECT raw_record FROM '+quote(self.mapping['table'])+' WHERE ebcdic_key=%s',(key,)).fetchone()
        return ('00',bytes(row[0])) if row else ('23',None)

    def start(self, *, key=None, prefix=None, reverse=False, index='ebcdic_key'):
        self.cursor=iter(self.store.browse(index,start=key,prefix=prefix,reverse=reverse))
        return '00'

    def next(self):
        if self.cursor is None:return '46',None
        ordinal=next(self.cursor,None)
        if ordinal is None:return '10',None
        row=self.connection.execute('SELECT raw_record FROM '+quote(self.mapping['table'])+' WHERE source_ordinal=%s',(ordinal,)).fetchone()
        return ('00',bytes(row[0])) if row else ('23',None)

    def end(self):self.cursor=None

    def write(self, raw, ordinal):
        import psycopg
        if not isinstance(raw,bytes) or len(raw)!=self.mapping['record_length']:return '44'
        columns=['source_ordinal','raw_record']+[k['column'] for k in self.mapping['keys']]
        values=[ordinal,raw]+[raw[k['key_offset']:k['key_offset']+k['key_length']] for k in self.mapping['keys']]
        try:
            with self.connection.transaction():
                self.connection.execute('INSERT INTO '+quote(self.mapping['table'])+' ('+','.join(map(quote,columns))+') VALUES ('+','.join(['%s']*len(values))+')',values)
        except psycopg.errors.UniqueViolation:return '22'
        return '00'

    def rewrite(self, key, raw):
        primary=self.mapping['keys'][0]
        if not isinstance(raw,bytes) or len(raw)!=self.mapping['record_length']:return '44'
        if raw[primary['key_offset']:primary['key_offset']+primary['key_length']]!=key:return '21'
        keys=self.mapping['keys'];values=[raw]+[raw[k['key_offset']:k['key_offset']+k['key_length']] for k in keys]+[key]
        result=self.connection.execute('UPDATE '+quote(self.mapping['table'])+' SET raw_record=%s,'+','.join(quote(k['column'])+'=%s' for k in keys)+' WHERE ebcdic_key=%s',values)
        return '00' if result.rowcount else '23'

    def delete(self,key):
        result=self.connection.execute('DELETE FROM '+quote(self.mapping['table'])+' WHERE ebcdic_key=%s',(key,))
        return '00' if result.rowcount else '23'


class DliRepository:
    """Explicit root/child keys; unsupported SSA syntax must not reach this API."""
    def __init__(self, connection, procopt='G'):
        if procopt not in ('G','A','AP'):raise ValueError('unsupported-procopt')
        self.connection,self.procopt=connection,procopt;self.parent=None;self.held=None

    @staticmethod
    def create(connection):
        connection.execute('CREATE TABLE dli_root (key bytea PRIMARY KEY, payload bytea NOT NULL)')
        connection.execute('CREATE TABLE dli_child (parent bytea REFERENCES dli_root(key) ON DELETE CASCADE, key bytea, payload bytea NOT NULL, PRIMARY KEY(parent,key))')

    def gu(self,key,hold=False):
        self.held=None
        row=self.connection.execute('SELECT payload FROM dli_root WHERE key=%s'+(' FOR UPDATE' if hold else ''),(key,)).fetchone()
        self.parent=key if row else None
        if row and hold:self.held=('root',key,None)
        return ('  ',bytes(row[0])) if row else ('GE',None)

    def gnp(self,key,hold=False):
        self.held=None
        if self.parent is None:return 'DJ',None
        row=self.connection.execute('SELECT payload FROM dli_child WHERE parent=%s AND key=%s'+(' FOR UPDATE' if hold else ''),(self.parent,key)).fetchone()
        if row and hold:self.held=('child',key,self.parent)
        return ('  ',bytes(row[0])) if row else ('GE',None)

    def insert(self,key,payload,parent=None):
        import psycopg
        if self.procopt not in ('A','AP'):return 'DJ'
        try:
            with self.connection.transaction():
                if parent is None:self.connection.execute('INSERT INTO dli_root VALUES (%s,%s)',(key,payload))
                else:self.connection.execute('INSERT INTO dli_child VALUES (%s,%s,%s)',(parent,key,payload))
        except psycopg.errors.UniqueViolation:return 'II'
        except psycopg.errors.ForeignKeyViolation:return 'GE'
        return '  '

    def mutate(self, payload=None, *, delete=False):
        if self.procopt not in ('A','AP') or self.held is None:return 'DJ'
        kind,key,parent=self.held;self.held=None
        table='dli_'+kind;where='key=%s'+(' AND parent=%s' if parent is not None else '')
        args=[key]+([parent] if parent is not None else [])
        result=self.connection.execute(('DELETE FROM '+table if delete else 'UPDATE '+table+' SET payload=%s')+' WHERE '+where,args if delete else [payload]+args)
        return '  ' if result.rowcount else 'GE'

    def boundary(self):
        """Caller must clear session position after its commit/rollback boundary."""
        self.parent=None;self.held=None
