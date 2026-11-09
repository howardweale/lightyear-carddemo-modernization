"""Independent full-state load/readback for the unchanged committed N1 input.

Library only: caller owns a separately admitted disposable connection. It never
accepts candidate-derived expected state, resets an existing database, launches a
candidate, authenticates custody or returns a qualified result.
"""
import json
from decimal import Decimal

from lightyear_execution import copau_full_state_contract as contract
from tools import copau_full_state as capture


def tables(connection):
    return connection.execute("""SELECT n.nspname,c.relname,c.relkind
        FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
        AND n.nspname !~ '^pg_toast' AND n.nspname !~ '^pg_temp_'
        AND c.relkind IN ('r','p','m','f','v','S')
        ORDER BY n.nspname,c.relname""").fetchall()


def snapshot(connection, producer):
    """All user-schema tables/rows; unsupported relations or hidden rows FAULT.

    A database table-state snapshot, not a schema/DDL or concurrent-writer proof.
    The caller must isolate candidate execution between observation boundaries.
    """
    from psycopg import sql
    contract.require(connection.autocommit, 'independent-autocommit-connection-required')
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        connection.execute('SET LOCAL row_security = off')
        require_no_large_objects(connection)
        inventory = tables(connection)
        state = {}
        for schema, table, kind in inventory:
            contract.require(kind in ('r', 'p', 'm'), 'unsupported-database-relation')
            raw = connection.execute(sql.SQL("SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb)::text FROM {} t").format(sql.Identifier(schema, table))).fetchone()[0]
            key = table if schema == 'public' and not table.startswith('@') else '@' + json.dumps([schema, table])
            contract.require(key not in state)
            state[key] = json.loads(raw, parse_float=Decimal)
    return capture.canonical_state(producer, state)


def require_no_large_objects(connection):
    contract.require(not connection.execute(
        'SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_largeobject_metadata)'
    ).fetchone()[0], 'unsupported-large-objects')


def load_committed(store, root, connection):
    """Only an empty disposable database; no DROP, truncate, overwrite or retry."""
    contract.require(connection.autocommit, 'independent-autocommit-connection-required')
    raw, commitment = contract._commitment(store)
    contract.require(commitment['producer_bindings'] == capture.bindings())
    completed = contract.decoded(store.read('n1-complete.json'))
    contract.require(completed['status'] == 'ORACLE_CAPTURE_ONLY' and
                     completed['commitment_sha256'] == contract.sha(raw) and
                     completed['oracle_sha256'] == contract.sha(contract.get_blob(store, 'n1-oracle')))
    store.absent('n1-load-consumed.json', 'n1-load-complete.json')
    # Consumption precedes database access; failed schema/load/parity never retries.
    store.write('n1-load-consumed.json', contract.encoded(dict(commitment_sha256=contract.sha(raw))))
    try:
        producer, helpers = capture.reference.verify_producer(root)
        inputs = contract.decoded(contract.get_blob(store, 'n1-input'))
        _, entries = helpers.build(helpers.ROOT)
        expected = capture.canonical_state(producer, capture.independent_initial(
            producer, entries, inputs['raw_fixture'], commitment['input_sha256']))
        lookup = {m['table']: (layout, m) for _, layout, m in entries}
        bindings = helpers.web_build(root / 'spec/modernization/carddemo-screens')
        parents = {}
        with connection.transaction():
            require_no_large_objects(connection)
            contract.require(not tables(connection), 'database-not-empty')
            for _, _, mapping in entries:
                connection.execute(helpers.ddl(mapping))
            connection.execute(bindings['fraud']['postgres_ddl'])
            connection.execute('CREATE TABLE slice_fixture_identity (identity text PRIMARY KEY)')
            connection.execute('INSERT INTO slice_fixture_identity VALUES (%s)', (commitment['input_sha256'],))
            for item in inputs['raw_fixture']['records']:
                table, ordinal = item['identity'].split(':')
                contract.require(table == item['table'] and item.get('parent') in (None, *parents))
                layout, mapping = lookup[table]
                row = producer.Store(connection, mapping, layout).load_one(bytes.fromhex(item['raw']),
                    int(ordinal), parent_path=parents.get(item.get('parent')),
                    twin_seq=int(ordinal) if mapping.get('segment') else None, quarantine=False)
                if mapping.get('segment'):
                    parents[item['identity']] = row['path_key']
        # New committed transaction, independent of loader transaction visibility.
        actual = snapshot(connection, producer)
        contract.require(actual == expected, 'complete-initial-state-mismatch')
        result = dict(schema='copau-initial-load/1', commitment_sha256=contract.sha(raw),
            input_sha256=commitment['input_sha256'], full_state_sha256=producer.digest(actual),
            table_count=len(actual), qualified=False, status='INITIAL_STATE_ONLY')
        store.write('n1-load-complete.json', contract.encoded(result))
        return result
    except BaseException:
        raise contract.Refused('initial-load-failed-consumed') from None
