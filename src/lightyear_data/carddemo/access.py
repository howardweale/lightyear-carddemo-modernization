"""CICS named RESP and bounded two-level DL/I over the generated typed schema.

The caller owns one database transaction. No private shadow tables or raw-record
columns are used. Checkpoint/restart, GSAM and secondary IMS DBDs are unsupported.
"""
from .schema import quote
from .store import Store


class VsamRepository:
    def __init__(self, connection, mapping, layout):
        self.connection,self.mapping=connection,mapping
        self.store=Store(connection,mapping,layout);self.cursor=None

    def read(self,key):
        row=self.store.find('ebcdic_key',key)
        return ('NORMAL',self.store.bytes(row)) if row else ('NOTFND',None)

    def start(self,*,key=None,prefix=None,reverse=False,index='ebcdic_key'):
        self.cursor=iter(self.store.browse(index,start=key,prefix=prefix,reverse=reverse))
        return 'NORMAL'

    def next(self):
        if self.cursor is None:return 'INVREQ',None
        ordinal=next(self.cursor,None)
        if ordinal is None:return 'ENDFILE',None
        row=self.store.find('source_ordinal',ordinal)
        return ('NORMAL',self.store.bytes(row)) if row else ('NOTFND',None)

    def end(self):self.cursor=None

    def write(self,raw,ordinal):
        import psycopg
        if not isinstance(raw,bytes) or len(raw)!=self.mapping['record_length']:return 'LENGERR'
        try:self.store.load_one(raw,ordinal,quarantine=False)
        except psycopg.errors.UniqueViolation:return 'DUPREC'
        except (ValueError,psycopg.DataError):return 'INVREQ'
        return 'NORMAL'

    def rewrite(self,key,raw):
        if not isinstance(raw,bytes) or len(raw)!=self.mapping['record_length']:return 'LENGERR'
        primary=self.mapping['keys'][0]
        if raw[primary['key_offset']:primary['key_offset']+primary['key_length']]!=key:return 'INVREQ'
        with self.connection.transaction():
            row=self.store.find('ebcdic_key',key,lock=True)
            if row is None:return 'NOTFND'
            self.store.replace(row,raw)
        return 'NORMAL'

    def delete(self,key):
        result=self.connection.execute('DELETE FROM '+quote(self.mapping['table'])+' WHERE ebcdic_key=%s',(key,))
        return 'NORMAL' if result.rowcount else 'NOTFND'


class DliRepository:
    def __init__(self,connection,root_mapping,root_layout,child_mapping,child_layout,procopt='G'):
        if procopt not in ('G','A','AP'):raise ValueError('unsupported-procopt')
        if root_mapping['table']!='pautsum0' or child_mapping['table']!='pautdtl1':raise ValueError('unsupported-segments')
        self.connection,self.procopt=connection,procopt
        self.root=Store(connection,root_mapping,root_layout);self.child=Store(connection,child_mapping,child_layout)
        self.boundary()

    def _get(self,store,path,hold):
        self.held=None
        row=store.find('path_key',path,lock=hold)
        if row and hold:self.held=(store,row)
        return ('  ',store.bytes(row)) if row else ('GE',None)

    def gu(self,key,hold=False):
        result=self._get(self.root,key,hold)
        self.parent=key if result[0]=='  ' else None;self.child_position=None
        self.position=(key,0,-1) if self.parent else None
        return result

    def gn(self,hold=False,*,roots_only=False):
        # Physical two-level preorder; twins follow captured twin_seq, then path.
        self.held=None
        ordered=[]
        for root in sorted(self.root.rows(),key=lambda r:r['path_key']):
            ordered.append(((root['path_key'],0,-1),self.root,root))
            if not roots_only:
                for child in sorted((r for r in self.child.rows() if r['parent_path_key']==root['path_key']),key=lambda r:(r['twin_seq'],r['path_key'])):
                    ordered.append(((root['path_key'],1,child['twin_seq'],child['path_key']),self.child,child))
        selected=next((v for v in ordered if self.position is None or v[0]>self.position),None)
        if selected is None:return 'GB',None
        self.position,store,row=selected;self.parent=row['parent_path_key'] or row['path_key']
        return self._get(store,row['path_key'],hold)

    def gnp(self,key=None,hold=False):
        self.held=None
        if self.parent is None:return 'GP',None
        if key is not None:return self._get(self.child,self.parent+key,hold)
        rows=sorted((r for r in self.child.rows() if r['parent_path_key']==self.parent and (self.child_position is None or (r['twin_seq'],r['path_key'])>self.child_position)),key=lambda r:(r['twin_seq'],r['path_key']))
        if not rows:return 'GE',None
        row=rows[0];self.child_position=(row['twin_seq'],row['path_key'])
        return self._get(self.child,row['path_key'],hold)

    def insert(self,key,payload,parent=None):
        import psycopg
        if self.procopt not in ('A','AP'):return 'AM'
        store=self.root if parent is None else self.child
        primary=store.mapping['keys'][0]
        if payload[primary['key_offset']:primary['key_offset']+primary['key_length']]!=key:return 'AJ'
        try:
            with self.connection.transaction():
                # Serializes ordinal/twin allocation inside the interaction transaction.
                self.connection.execute('LOCK TABLE '+quote(store.table)+' IN SHARE ROW EXCLUSIVE MODE')
                ordinal=self.connection.execute('SELECT COALESCE(MAX(source_ordinal),0)+1 FROM '+quote(store.table)).fetchone()[0]
                twin=self.connection.execute('SELECT COALESCE(MAX(twin_seq),0)+1 FROM '+quote(store.table)+' WHERE parent_path_key IS NOT DISTINCT FROM %s',(parent,)).fetchone()[0]
                store.load_one(payload,ordinal,parent_path=parent,twin_seq=twin,quarantine=False)
        except psycopg.errors.UniqueViolation:return 'II'
        except psycopg.errors.ForeignKeyViolation:return 'GE'
        return '  '

    def mutate(self,payload=None,*,delete=False):
        if self.procopt not in ('A','AP'):return 'AM'
        if self.held is None:return 'DJ'
        store,row=self.held;self.held=None
        with self.connection.transaction():
            if delete:
                if store is self.root:
                    self.connection.execute('DELETE FROM '+quote(self.child.table)+' WHERE parent_path_key=%s',(row['path_key'],))
                result=self.connection.execute('DELETE FROM '+quote(store.table)+' WHERE path_key=%s',(row['path_key'],))
                return '  ' if result.rowcount else 'GE'
            k=store.mapping['keys'][0]
            if payload[k['key_offset']:k['key_offset']+k['key_length']] != store.bytes(row)[k['key_offset']:k['key_offset']+k['key_length']]:return 'DA'
            store.replace(row,payload)
        return '  '

    def boundary(self):
        self.parent=None;self.held=None;self.position=None;self.child_position=None
