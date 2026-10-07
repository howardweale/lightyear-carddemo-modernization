"""Native public-fixture execution. No Docker or credentials in this module.

Connections are supplied by the explicitly admitted VM runner. Every call uses
its own database, restored from a SQL Server backup or a PostgreSQL template.
Raw protocol evidence is retained even when cross-engine policy is unresolved.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import re
import time

from .capture import capture_state, scalar, query, identifier, state_changes, json_key


def utc():
    return datetime.now(timezone.utc).isoformat()


def go_batches(text):
    """Split standalone GO outside strings/comments; refuse batch repetition."""
    batches, lines = [], []
    quote = None
    comment = 0
    for line in text.splitlines(keepends=True):
        if not quote and not comment and re.fullmatch(r"\s*GO\s*(?:--[^\n]*)?\s*", line, re.I):
            if ''.join(lines).strip():
                batches.append(''.join(lines))
            lines = []
            continue
        if not quote and not comment and re.match(r"\s*GO\s+\d", line, re.I):
            raise ValueError('GO-repetition-not-supported')
        lines.append(line)
        i = 0
        while i < len(line):
            ch, pair = line[i], line[i:i+2]
            if comment:
                if pair == '/*': comment += 1; i += 2; continue
                if pair == '*/': comment -= 1; i += 2; continue
            elif quote:
                if ch == quote:
                    if i+1 < len(line) and line[i+1] == quote: i += 2; continue
                    quote = None
            elif pair == '--': break
            elif pair == '/*': comment += 1; i += 2; continue
            elif ch in "'\"[": quote = ']' if ch == '[' else ch
            i += 1
    if quote or comment: raise ValueError('unterminated-SQL-token')
    if ''.join(lines).strip(): batches.append(''.join(lines))
    return batches


class _QmarkCursor:
    def __init__(self, cursor): self.cursor = cursor
    def execute(self, sql, parameters=()):
        # Only the fixed capture metadata queries use qmarks, never caller SQL.
        if parameters: return self.cursor.execute(sql.replace('?', '%s'), parameters)
        return self.cursor.execute(sql)
    def __getattr__(self, name): return getattr(self.cursor, name)


class _QmarkConnection:
    def __init__(self, connection): self.connection = connection
    def cursor(self): return _QmarkCursor(self.connection.cursor())


def execute(connection, sql):
    with connection.cursor() as c:
        c.execute(sql)
        while c.nextset(): pass


def _column(c):
    # Retain every DB-API field without pretending engine type codes are equal.
    return {'name': c[0], 'type_code': str(c[1]),
            'display_size': c[2], 'internal_size': c[3],
            'precision': c[4], 'scale': c[5], 'null_ok': c[6]}


def result_set(cursor):
    return {'columns': [_column(c) for c in cursor.description],
            'rows': [[scalar(v) for v in r] for r in cursor.fetchall()]}


@contextmanager
def tds_tokens(session):
    """Capture actual TDS DONE/INFO/ERROR tokens from the pinned driver.

    Handler wrappers are process-global, so this serial runner refuses nested
    instrumentation. They are restored even if the procedure raises an error.
    """
    import pytds.tds_session as mod
    if getattr(mod, '_lightyear_capture_active', False):
        raise RuntimeError('concurrent-TDS-capture-forbidden')
    mod._lightyear_capture_active = True
    tokens = []
    originals = {name:getattr(mod._TdsSession,name) for name in ('process_end','process_msg')}
    try:
        for name,original in originals.items():
            def wrapper(s, marker, name=name, original=original):
                try: return original(s,marker)
                finally:
                    if s is session:
                        if name=='process_msg':
                            tokens.append({'token': marker, 'message': dict(s.messages[-1])})
                        else:
                            tokens.append({'token': marker, 'flags': s.done_flags,
                                           'row_count': s.rows_affected})
            setattr(mod._TdsSession,name,wrapper)
        yield tokens
    finally:
        for name,original in originals.items(): setattr(mod._TdsSession,name,original)
        mod._lightyear_capture_active = False


class NativeEngine:
    """Credential-free engine boundary. Connector must return autocommit sessions."""
    def __init__(self, engine, connector, prefix, coverage_bridge=None):
        if engine not in ('sqlserver', 'postgresql'): raise ValueError('engine')
        if not re.fullmatch(r'lytsql_[a-f0-9]{12}', prefix): raise ValueError('owned-prefix')
        self.engine, self.connector, self.prefix = engine, connector, prefix
        self.owned = set()
        self.coverage_bridge = coverage_bridge

    def name(self, suffix):
        if not re.fullmatch(r'[a-z0-9_]{1,45}', suffix): raise ValueError('database-suffix')
        return self.prefix + '_' + suffix

    def _q(self, name):
        if name not in self.owned: raise ValueError('unowned-database')
        return identifier(name, self.engine)

    def provision(self, suffix, setup, procedure):
        db = self.name(suffix)
        with self.connector(None) as c:
            # CREATE, never CREATE IF NOT EXISTS: an old slot cannot be reused.
            execute(c, 'CREATE DATABASE ' + identifier(db, self.engine))
        self.owned.add(db)
        with self.connector(db) as c:
            if self.engine == 'sqlserver':
                for sql in go_batches(setup) + go_batches(procedure): execute(c, sql)
            else:
                if self.coverage_bridge: execute(c, 'CREATE EXTENSION plpgsql_check')
                execute(c, setup)
                execute(c, procedure)
        receipt = {'engine': self.engine, 'database': db, 'created_utc': utc(),
                   'setup_sha256': hashlib.sha256(setup.encode()).hexdigest(),
                   'procedure_sha256': hashlib.sha256(procedure.encode()).hexdigest()}
        if self.engine == 'sqlserver':
            backup = '/var/opt/mssql/data/' + db + '.bak'
            with self.connector(None) as c:
                execute(c, f"BACKUP DATABASE {self._q(db)} TO DISK=N'{backup}' WITH INIT,CHECKSUM")
                execute(c, f"RESTORE VERIFYONLY FROM DISK=N'{backup}' WITH CHECKSUM")
            receipt.update(backup=backup, backup_verified=True)
        return receipt

    def reset(self, baseline, suffix):
        tick=time.monotonic()
        name = self.name(suffix)
        if name in self.owned: raise ValueError('slot-already-used')
        source = baseline['database']
        if source not in self.owned: raise ValueError('unowned-baseline')
        with self.connector(None) as c:
            if self.engine == 'sqlserver':
                with c.cursor() as cur:
                    cur.execute(f"RESTORE FILELISTONLY FROM DISK=N'{baseline['backup']}'")
                    files = cur.fetchall()
                moves = []
                for i, row in enumerate(files):
                    logical = row[0].replace("'", "''")
                    destination = '/var/opt/mssql/data/' + name + '_' + str(i) + ('.ldf' if row[2] == 'L' else '.mdf')
                    moves.append(f"MOVE N'{logical}' TO N'{destination}'")
                execute(c, f"RESTORE DATABASE {identifier(name,self.engine)} FROM DISK=N'{baseline['backup']}' WITH CHECKSUM," + ','.join(moves))
                method = 'golden-backup-restore'
            else:
                execute(c, f'CREATE DATABASE {identifier(name,self.engine)} TEMPLATE {self._q(source)}')
                method = 'fresh-database-from-template'
        self.owned.add(name)
        return {'database': name, 'baseline': source, 'method': method,
                'restored_utc': utc(), 'outer_rollback': False,
                'reset_elapsed_seconds':time.monotonic()-tick}

    def capture_state(self, connection):
        result = capture_state(_QmarkConnection(connection) if self.engine == 'sqlserver' else connection, self.engine)
        return result

    def call(self, reset, item, on_capture=None):
        db = reset['database']
        self._q(db)
        case, convention = item['cases'][0], item['calling_convention']
        with self.connector(db) as c:
            if self.engine == 'sqlserver':
                for k,v in case['source_session'].items():
                    if not re.fullmatch('[A-Z_]+',k) or not re.fullmatch('[A-Za-z_0-9]+',str(v)): raise ValueError('session-setting')
                    execute(c, f'SET {k} {v}')
                version = query(c, 'SELECT @@VERSION')[0][0]
                settings = query(c, 'DBCC USEROPTIONS')
                clock = query(c, 'SELECT CONVERT(varchar(40),SYSUTCDATETIME(),127)')[0][0]
            else:
                execute(c, "SET TIME ZONE 'UTC'")
                execute(c, 'SET standard_conforming_strings=on')
                execute(c, "SET statement_timeout='60s'")
                version = query(c, 'SELECT version()')[0][0]
                settings = query(c, 'SELECT current_setting(\'TimeZone\'),current_setting(\'standard_conforming_strings\')')
                clock = str(query(c, 'SELECT clock_timestamp()')[0][0])
            before = self.capture_state(c)
            if on_capture: on_capture('before',before)
            collector=None
            if self.coverage_bridge:
                from .coverage import SqlCoverage, PgCoverage
                collector=(SqlCoverage(c,db,self.coverage_bridge) if self.engine=='sqlserver' else PgCoverage(c))
                collector.start()
            started, tick = utc(), time.monotonic()
            obs = self._sql_call(c,item) if self.engine == 'sqlserver' else self._pg_call(c,item)
            obs.update(started_utc=started, ended_utc=utc(), elapsed_seconds=time.monotonic()-tick,
                       engine_version=version, session_settings=settings, database_clock_before=clock)
            if on_capture: on_capture('protocol',obs)
            if self.engine == 'sqlserver':
                obs['transaction_after'] = query(c, 'SELECT @@TRANCOUNT,XACT_STATE()')[0]
                obs['temp_catalog'] = query(c,"""SELECT name,object_id,is_ms_shipped,
OBJECT_ID('tempdb..'+CASE WHEN CHARINDEX('____',name)>0 THEN LEFT(name,CHARINDEX('____',name)-1) ELSE name END),
CASE WHEN CHARINDEX('____',name)>0 THEN LEFT(name,CHARINDEX('____',name)-1) ELSE name END
FROM tempdb.sys.tables WHERE name LIKE '#%' ORDER BY name""")
                obs['temp_objects'] = [[r[4]] for r in obs['temp_catalog'] if not r[2] and r[1]==r[3]]
            else:
                obs['transaction_after'] = c.info.transaction_status.name
                obs['temp_objects'] = query(c,"SELECT c.relname FROM pg_class c WHERE c.relnamespace=pg_my_temp_schema() AND c.relkind IN ('r','p') ORDER BY c.relname")
            after = self.capture_state(c)
            if on_capture: on_capture('after',after)
            obs['side_effects'] = state_changes(before, after)
            obs['coverage'] = collector.finish(lambda raw:on_capture('coverage-raw',raw) if on_capture else None) if collector else None
            if on_capture and obs['coverage']:on_capture('coverage',obs['coverage'])
            return {'before': before, 'after': after, 'observation': obs,
                    'reset': reset, 'calling_convention': convention}

    def _sql_call(self, connection, item):
        import pytds
        sets, outputs, err, status = [], {}, None, None
        with connection.cursor() as cur:
            parameters = [pytds.output(None, int)] if item['id']=='output-parameter' else []
            with tds_tokens(cur._session) as tokens:
                try:
                    cur.callproc('dbo.trap', parameters)
                    while True:
                        if cur.description: sets.append(result_set(cur))
                        if not cur.nextset(): break
                    values = cur.get_proc_outputs()
                    if parameters: outputs = dict(zip(item['parameters'], [scalar(v) for v in values]))
                    status = cur.get_proc_return_status()
                except pytds.Error as ex:
                    err = {'class': type(ex).__name__, 'message': str(ex),
                           'number': getattr(ex,'number',None), 'severity': getattr(ex,'severity',None),
                           'state': getattr(ex,'state',None)}
        if not any('flags' in t for t in tokens): raise RuntimeError('TDS-completion-token-not-captured')
        return {'result_sets':sets, 'output_parameters':outputs, 'return_code':status,
                'error':err, 'tds_tokens':tokens, 'notices':[]}

    def _pg_call(self, connection, item):
        import psycopg
        sets, outputs, err, status, notices = [], {}, None, 0, []
        def notice(diag):
            notices.append({k:getattr(diag,k,None) for k in ('severity_nonlocalized','sqlstate','message_primary','message_detail','context')})
        connection.add_notice_handler(notice)
        convention = item['calling_convention']
        try:
            with connection.cursor() as cur:
                if 'refcursor_order' in convention:
                    cur.execute('BEGIN')
                    cur.execute(convention['target'])
                    handles = cur.fetchone()
                    if list(handles) != convention['refcursor_order']: raise ValueError('refcursor-contract')
                    for handle in handles:
                        cur.execute('FETCH ALL FROM ' + identifier(handle,'postgresql'))
                        sets.append(result_set(cur))
                    cur.execute('COMMIT')
                else:
                    cur.execute(convention['target'])
                    if cur.description:
                        rs = result_set(cur)
                        if 'result_return_mapping' in convention:
                            mapping=convention['result_return_mapping']
                            if mapping!={'column':'tsql_return_code','type':'integer'}:
                                raise ValueError('unsupported-result-return-mapping')
                            positions=[i for i,col in enumerate(rs['columns']) if col['name']==mapping['column']]
                            if len(positions)!=1 or not rs['rows']: raise ValueError('return-column-missing')
                            position=positions[0];codes=[row[position] for row in rs['rows']]
                            if any(type(code) is not int or code!=codes[0] for code in codes):
                                raise ValueError('return-column-inconsistent')
                            status=codes[0]
                            sets.append({'columns':[col for i,col in enumerate(rs['columns']) if i!=position],
                                         'rows':[[v for i,v in enumerate(row) if i!=position] for row in rs['rows']]})
                        elif 'output_mapping' in convention:
                            if len(rs['rows'])!=1: raise ValueError('output-contract')
                            outputs = dict(zip([c['name'] for c in rs['columns']],rs['rows'][0]))
                        elif 'return_mapping' in convention:
                            if len(rs['rows'])!=1: raise ValueError('return-contract')
                            status = rs['rows'][0][0]
                        else: sets.append(rs)
        except psycopg.Error as ex:
            err = {'class':type(ex).__name__, 'message':str(ex), 'sqlstate':ex.sqlstate,
                   'severity':getattr(ex.diag,'severity_nonlocalized',None)}
            status = None
            # An explicit cursor transaction may remain failed. Do not hide it
            # by rolling it back and claiming a complete capture.
            if connection.info.transaction_status.name != 'IDLE': raise RuntimeError('failed-caller-transaction-capture-unavailable') from ex
        finally: connection.remove_notice_handler(notice)
        return {'result_sets':sets,'output_parameters':outputs,'return_code':status,
                'error':err,'tds_tokens':[],'notices':notices}

    def drop(self, database):
        q = self._q(database)
        with self.connector(None) as c:
            execute(c, 'DROP DATABASE ' + q)
        self.owned.remove(database)
        return {'database':database,'dropped_utc':utc()}

    def coverage(self, captured, procedure=None):
        """Return the replay-checked native summary, never synthesize counts."""
        from .coverage import replay_coverage
        record=captured['observation'].get('coverage')
        return replay_coverage(record) if record is not None else None
