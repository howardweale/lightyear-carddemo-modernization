"""Read-only engine-side transaction sampling. No generated assertions are consumed.

Missing samples are inconclusive, never evidence of success. Oracle's rollback
witness is a same-session transaction/undo/counter transition; it does not claim
that polling identifies each rolled-back application row.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time

from .contracts import canonical, require, seal, verify
from .native_catalog import query

VERSION = 'native-transaction-observer-v2'
POLICY = {'version': VERSION, 'interval_ms': 25, 'maximum_gap_ms': 1000,
          'minimum_wait_ms': 100, 'maximum_seconds': 1300,
          'maximum_samples': 55000, 'target_schema': 'adempiere',
          'target_table': 'c_bpartner', 'query_timeout_ms': 3000,
          'postgres_observer_assigns_private_xids': True}
ORACLE = {
    'identity': "SELECT SYS_CONTEXT('USERENV','SESSION_USER') observer_user, SYS_CONTEXT('USERENV','DB_NAME') database_name, SYS_CONTEXT('USERENV','CON_NAME') container_name FROM dual",
    'sessions': """SELECT s.sid, s.serial# serial, s.username, s.program, s.module,
        s.action, s.blocking_session, s.blocking_session_status,
        s.event, s.state, s.row_wait_obj# row_wait_object,
        CASE WHEN t.xidusn IS NOT NULL THEN TO_CHAR(t.xidusn)||'.'||TO_CHAR(t.xidslot)||'.'||TO_CHAR(t.xidsqn) END xid,
        t.used_urec undo_records,
        (SELECT st.value FROM v$sesstat st JOIN v$statname n ON n.statistic#=st.statistic# WHERE st.sid=s.sid AND n.name='user rollbacks') rollbacks,
        (SELECT st.value FROM v$sesstat st JOIN v$statname n ON n.statistic#=st.statistic# WHERE st.sid=s.sid AND n.name='user commits') commits,
        (SELECT st.value FROM v$sesstat st JOIN v$statname n ON n.statistic#=st.statistic# WHERE st.sid=s.sid AND n.name='rollback changes - undo records applied') undo_applied
        FROM v$session s LEFT JOIN v$transaction t ON t.addr=s.taddr
        WHERE s.username='ADEMPIERE'""",
    'locks': """SELECT l.sid, l.type lock_type, l.id1, l.id2, l.lmode held_mode,
        l.request requested_mode, l.block blocking, o.owner object_schema, o.object_name
        FROM v$lock l JOIN v$session s ON s.sid=l.sid
        LEFT JOIN dba_objects o ON l.type='TM' AND o.object_id=l.id1
        WHERE s.username='ADEMPIERE' AND l.type IN ('TX','TM')""",
}
POSTGRES = {
    'identity': "SELECT current_user observer_user, current_database() database_name, pg_current_xact_id()::text next_xid",
    'sessions': """SELECT pid, backend_start::text backend_start, usename username,
        application_name, backend_xid::text xid, xact_start::text xact_start,
        state, wait_event_type, wait_event, pg_blocking_pids(pid) blockers
        FROM pg_stat_activity WHERE usename='adempiere' AND datname=current_database()""",
    'locks': """SELECT l.pid, l.locktype lock_type, l.transactionid::text transaction_id,
        l.mode, l.granted, n.nspname object_schema, c.relname object_name
        FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid
        LEFT JOIN pg_class c ON c.oid=l.relation LEFT JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE a.usename='adempiere' AND a.datname=current_database()""",
}
QUERIES = {'oracle': ORACLE, 'postgresql': POSTGRES}


def full_xid(short, next_xid):
    """Resolve a sampled xid32 against the engine's later allocated observer xid8."""
    low, upper = int(short), int(next_xid)
    require(3 <= low < 2**32 and upper >= 3, 'Invalid native transaction identity')
    value = (upper // 2**32) * 2**32 + low
    if value >= upper: value -= 2**32
    require(3 <= value < upper and upper-value < 2**31, 'Ambiguous/wrapped transaction identity')
    return str(value)


def connect(lane, password):
    if lane == 'oracle':
        import oracledb
        oracledb.defaults.fetch_decimals = True
        c = oracledb.connect(user='LY_OBSERVER', password=password, dsn='oracle:1521/FREEPDB1')
        c.call_timeout = POLICY['query_timeout_ms']
        return c
    import psycopg
    c = psycopg.connect(host='postgresql', user='ly_observer', password=password,
                        dbname='idempiere', autocommit=True,
                        options='-c statement_timeout=3000 -c default_transaction_read_only=on')
    return c


def sample(connection, lane, sequence, origin, tracked):
    started = time.monotonic_ns()
    # Allocate an observer-only xid8 AFTER sessions: an actor may allocate its xid while
    # the observer is sampling. An earlier horizon would misclassify that xid.
    order = ('sessions', 'locks', 'identity')
    results = {name: query(connection, QUERIES[lane][name]) for name in order}
    require(len(results['identity']) == 1, 'Missing native observer identity')
    require(results['identity'][0]['observer_user'].lower() == 'ly_observer', 'Observer is not a separate database principal')
    statuses = []
    if lane == 'postgresql':
        upper = results['identity'][0]['next_xid']
        for s in results['sessions']:
            if s['xid'] is not None:
                xid = full_xid(s['xid'], upper)
                s['full_xid'] = xid
                tracked.setdefault(xid, {'pid': s['pid'], 'backend_start': s['backend_start']})
        require(len(tracked) <= 10000, 'Too many observed transactions')
        if tracked:
            ids = ','.join("'"+x+"'::xid8" for x in tracked)  # validated decimal integers only
            statuses = query(connection, 'SELECT x::text xid, pg_xact_status(x) status FROM unnest(ARRAY['+ids+']) x')
    return {'sequence': sequence, 'started_ns': started-origin,
            'finished_ns': time.monotonic_ns()-origin,
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'results': results, 'transaction_status': statuses}


def monitor(lane, password, output, stop, *, connection_factory=connect):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic_ns(); count = 0; error = None; tracked = {}
    raw = output/'samples.jsonl'
    try:
        with connection_factory(lane, password) as c, raw.open('xb') as stream:
            while True:
                value = sample(c, lane, count, started, tracked)
                stream.write(canonical(value)+b'\n'); stream.flush(); count += 1
                if count == 1: (output/'ready.json').write_bytes(canonical({'ready': True}))
                if stop.is_set(): break
                require(count < POLICY['maximum_samples'], 'Observer sample budget exhausted')
                require((time.monotonic_ns()-started)/1e9 < POLICY['maximum_seconds'], 'Observer elapsed budget exhausted')
                stop.wait(POLICY['interval_ms']/1000)
    except Exception as exc:
        error = {'type': type(exc).__name__, 'message': str(exc).replace(password, '[redacted]')}
    receipt = seal({'artifact_type': VERSION, 'lane': lane, 'policy': POLICY,
                    'evidence_class': 'native-engine-session-lock-transaction-observation',
                    'query_sha256': {k: hashlib.sha256(v.encode()).hexdigest() for k,v in QUERIES[lane].items()},
                    'queries': QUERIES[lane], 'samples': count, 'samples_sha256': hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None,
                    'complete': error is None and stop.is_set(), 'error': error,
                    'elapsed_seconds': (time.monotonic_ns()-started)/1e9,
                    'independently_attested': False})
    (output/'receipt.json').write_bytes(canonical(receipt))
    return receipt


def session_key(lane, row):
    return (row['sid'], row['serial']) if lane == 'oracle' else (row['pid'], row['backend_start'])


def target_lock(lane, locks, identity, *, write=False):
    for lock in locks:
        who = lock.get('sid') if lane == 'oracle' else lock.get('pid')
        if who != identity or str(lock.get('object_schema')).lower() != POLICY['target_schema'] or str(lock.get('object_name')).lower() != POLICY['target_table']: continue
        if lane == 'oracle' and lock['lock_type'] == 'TM' and lock['held_mode'] >= (3 if write else 2): return True
        if lane == 'postgresql' and lock['lock_type'] == 'relation' and lock['granted'] and lock['mode'] in (('RowExclusiveLock',) if write else ('RowExclusiveLock','RowShareLock')): return True
    return False


def wait_pairs(lane, rows, locks):
    pairs = set(); identities = {r['sid'] if lane=='oracle' else r['pid']: r for r in rows}
    for waiter, row in identities.items():
        blockers = [row['blocking_session']] if lane=='oracle' and row.get('blocking_session_status')=='VALID' and row.get('state')=='WAITING' else row.get('blockers', []) if lane=='postgresql' and row.get('wait_event_type')=='Lock' else []
        for holder in blockers:
            if holder not in identities or holder == waiter: continue
            if not all(target_lock(lane,locks,x) for x in (waiter,holder)): continue
            if lane=='oracle':
                waiting = [x for x in locks if x['sid']==waiter and x['lock_type']=='TX' and x['requested_mode']>0]
                matched = any(h['sid']==holder and h['lock_type']=='TX' and h['held_mode']>0 and (h['id1'],h['id2'])==(w['id1'],w['id2']) for h in locks for w in waiting)
            else:
                waiting = [x for x in locks if x['pid']==waiter and x['lock_type']=='transactionid' and not x['granted']]
                matched = any(h['pid']==holder and h['lock_type']=='transactionid' and h['granted'] and h['transaction_id']==w['transaction_id'] for h in locks for w in waiting)
            if matched: pairs.add((session_key(lane,row),session_key(lane,identities[holder])))
    return pairs


def assess(receipt, samples):
    verify(receipt); lane=receipt['lane']; require(lane in QUERIES, 'Unknown observer lane')
    require(receipt['policy']==POLICY and receipt['artifact_type']==VERSION, 'Observer policy differs')
    require(receipt['query_sha256']=={k:hashlib.sha256(v.encode()).hexdigest() for k,v in QUERIES[lane].items()}, 'Observer queries differ')
    require(receipt['complete'] and receipt['error'] is None, 'Observer incomplete')
    require(len(samples)==receipt['samples'] and len(samples)>=2, 'Missing observer samples')
    waiting={}; waits=[]; rollbacks=[]; previous={}; transactions={}; last_end=None; incomplete_counters=[]
    for index, value in enumerate(samples):
        require(value['sequence']==index, 'Reordered/missing observer sample')
        start,end=value['started_ns'],value['finished_ns']
        require(type(start) is int and type(end) is int and 0<=start<=end, 'Invalid observer timing')
        require(last_end is None or last_end<=start, 'Observer time regressed')
        require(end-start<=POLICY['maximum_gap_ms']*1000000 and (last_end is None or start-last_end<=POLICY['maximum_gap_ms']*1000000), 'Observer coverage gap')
        last_end=end; results=value['results']; rows=results['sessions']; locks=results['locks']
        require(len(results['identity'])==1 and results['identity'][0]['observer_user'].lower()=='ly_observer','Observer identity differs')
        pairs=wait_pairs(lane,rows,locks)
        waiting={p:waiting.get(p,start) for p in pairs}
        for pair, since in waiting.items():
            if start-since>=POLICY['minimum_wait_ms']*1000000:
                waits.append({'sample':index,'waiter':list(pair[0]),'holder':list(pair[1]),'observed_span_ns':start-since})
        current={session_key(lane,r):r for r in rows}
        require(len(current)==len(rows), 'Ambiguous native session identity')
        for identity,row in current.items():
            if lane=='postgresql':
                if row.get('full_xid') and target_lock(lane,locks,row['pid'],write=True):
                    require(row['full_xid']==full_xid(row['xid'],results['identity'][0]['next_xid']), 'Transaction epoch binding differs')
                    transactions.setdefault(row['full_xid'], {'session':list(identity),'sample':index})
            else:
                tracked=transactions.get(identity)
                if tracked and row['xid'] is None:
                    old=tracked['row']
                    if not all(type(r.get(k)) is int for r in (old,row) for k in ('rollbacks','commits','undo_applied')):
                        incomplete_counters.append({'sample':index,'session':list(identity),'reason':'missing-counter-no-witness'})
                        transactions.pop(identity,None)
                        continue
                    if row['rollbacks']-old['rollbacks']==1 and row['undo_applied']>old['undo_applied'] and row['commits']==old['commits']:
                        rollbacks.append({'sample':index,'session':list(identity),'xid':old['xid'], 'undo_records_applied':row['undo_applied']-old['undo_applied'], 'basis':'native-same-session-transaction-ended-with-rollback-and-undo'})
                    transactions.pop(identity,None)
                elif row['xid'] is not None:
                    if tracked and tracked['row']['xid']!=row['xid']:transactions.pop(identity,None)
                    if target_lock(lane,locks,row['sid'],write=True):
                        transactions.setdefault(identity,{'row':row,'sample':index})
                # Session and lock views are not an atomic snapshot. A lock may
                # disappear just after the session query. Keep a previously
                # observed transaction binding until its end or identity change.
        if lane=='postgresql':
            for tx in value['transaction_status']:
                if tx['xid'] in transactions and tx['status']=='aborted':
                    rollbacks.append({'sample':index,'xid':tx['xid'],**transactions.pop(tx['xid']), 'basis':'native-pg_xact_status-aborted'})
        previous=current
    return seal({'artifact_type':'lightyear-native-transaction-witnesses', 'version':VERSION,
                 'lane':lane,'observer_receipt_sha256':receipt['content_sha256'],
                 'lock_wait_observed':bool(waits),'rollback_observed':bool(rollbacks),
                 'incomplete_counter_transitions':incomplete_counters,
                 'passed':bool(waits and rollbacks),'lock_witnesses':waits,'rollback_witnesses':rollbacks,
                 'scope':'Engine-observed waits and rollback activity involving the journey business-partner table; no per-row undo history or crash-recovery claim.',
                 'generated_assertions_used':False,'independently_attested':False})


def verify_capture(folder):
    folder=Path(folder);receipt=json.loads((folder/'receipt.json').read_bytes());raw=(folder/'samples.jsonl').read_bytes()
    require(len(raw)<512*1024**2,'Observer capture too large')
    require(hashlib.sha256(raw).hexdigest()==receipt['samples_sha256'],'Observer capture changed')
    return assess(receipt,[json.loads(line) for line in raw.splitlines()])


def main():
    import sys
    spec=json.load(sys.stdin);stop=threading.Event();marker=Path(spec['stop_file'])
    def stopping():
        while not stop.wait(.025):
            if marker.exists():stop.set()
    thread=threading.Thread(target=stopping,daemon=True);thread.start()
    value=monitor(spec['lane'],spec['password'],spec['output'],stop)
    print(json.dumps(value));return 0 if value['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
