"""Independent full-state load/readback for the unchanged committed N1 input.

Library only: caller owns a separately admitted disposable connection. It never
accepts candidate-derived expected state, resets an existing database, launches a
candidate, authenticates custody or returns a qualified result.
"""
import json
import re

from lightyear_execution import copau_full_state_contract as contract
from tools import copau_full_state as capture


def tables(connection):
    rows = connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    names = [r[0] for r in rows]
    contract.require(all(isinstance(n, str) and re.fullmatch('[a-z][a-z0-9_]*', n) for n in names))
    return names


def snapshot(connection, producer):
    """One consistent read-only transaction; every public table and every row."""
    contract.require(connection.autocommit, 'independent-autocommit-connection-required')
    with connection.transaction():
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        inventory = tables(connection)
        contract.require(inventory, 'empty-inventory')
        state = {}
        for table in inventory:
            raw = connection.execute("SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb)::text FROM \"" + table + '\" t').fetchone()[0]
            state[table] = json.loads(raw)
    return capture.canonical_state(producer, state)


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
