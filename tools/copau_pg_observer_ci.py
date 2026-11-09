"""CI-only public disposable PostgreSQL commit/rollback observation exercise.

Not candidate proof: this client is psycopg, not InteractionEngine. No private
input/custody/signing/provider capability, receipt or activation is supplied.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import threading
import time

from lightyear_execution import copau_pg_observer as pg
from lightyear_execution import copau_full_state_contract as contract
from tools import copau_full_state as capture
from tools import copau_candidate_state as candidate_state


class PublicMemory:
    """CI double only; never a production private-store implementation."""
    def __init__(self):
        self.files = {}

    def absent(self, *names):
        contract.require(not any(name in self.files for name in names))

    def write(self, name, raw):
        self.absent(name)
        contract.require(0 < len(raw) <= 262144)
        self.files[name] = bytes(raw)

    def read(self, name):
        contract.require(name in self.files)
        return self.files[name]


def exercise_state(port):
    import psycopg
    connect = dict(host='127.0.0.1', port=port, user='postgres', dbname='postgres',
                   sslmode='disable', gssencmode='disable', connect_timeout=5)
    store, root = PublicMemory(), Path.cwd()
    commitment = capture.prepare_inputs(store, root, bytes(range(32)), context_sha256='a' * 64)
    contract.acknowledge(store, b'PUBLIC CI DOUBLE', verifier=lambda _: commitment)
    capture.capture(store, root, acknowledgment_verifier=lambda _: commitment)
    producer, _ = capture.reference.verify_producer(root)
    with psycopg.connect(**connect, autocommit=True) as admin:
        admin.execute('CREATE DATABASE n1_input_public')
    with psycopg.connect(**dict(connect, dbname='n1_input_public'), autocommit=True) as independent:
        assert candidate_state.snapshot(independent, producer) == {}
        result = candidate_state.load_committed(store, root, independent)
        expected = contract.decoded(contract.get_blob(store, 'n1-initial'))
        assert candidate_state.snapshot(independent, producer) == expected
        # Session-local temporary state is explicitly outside durable state.
        independent.execute('CREATE TEMP TABLE n1_temporary (id integer)')
        independent.execute('INSERT INTO n1_temporary VALUES (1)')
        assert candidate_state.snapshot(independent, producer) == expected
        oid = independent.execute('SELECT lo_create(0)').fetchone()[0]
        try:
            candidate_state.snapshot(independent, producer)
        except contract.Refused as error:
            assert str(error) == 'unsupported-large-objects'
        else:
            raise AssertionError('even an empty large object must fault')
        finally:
            independent.execute('SELECT lo_unlink(%s)', (oid,))
        assert candidate_state.snapshot(independent, producer) == expected
        independent.execute('CREATE TABLE public.n1_unexpected (id integer)')
        assert candidate_state.snapshot(independent, producer) != expected
        independent.execute('DROP TABLE public.n1_unexpected')
        independent.execute('CREATE SCHEMA "Other.Schema"')
        independent.execute('CREATE TABLE "Other.Schema"."Odd.Table" (id integer, value text, precise numeric)')
        key = '@' + json.dumps(['Other.Schema', 'Odd.Table'])
        empty = candidate_state.snapshot(independent, producer)
        assert empty[key] == [] and empty != expected
        independent.execute('INSERT INTO "Other.Schema"."Odd.Table" VALUES (1,\'PUBLIC\',123456789012345678.123456789)')
        extra = candidate_state.snapshot(independent, producer)
        assert extra[key] == [producer.canonical(dict(id=1, value='PUBLIC', precise=Decimal('123456789012345678.123456789')))]
        assert {k: v for k, v in extra.items() if k != key} == expected
        # Privilege/RLS failures must not silently remove rows from the snapshot.
        independent.execute('CREATE ROLE n1_snapshot_reader')
        independent.execute('GRANT USAGE ON SCHEMA public,"Other.Schema" TO n1_snapshot_reader')
        independent.execute('GRANT SELECT ON ALL TABLES IN SCHEMA public,"Other.Schema" TO n1_snapshot_reader')
        independent.execute('ALTER TABLE "Other.Schema"."Odd.Table" ENABLE ROW LEVEL SECURITY')
        independent.execute('SET ROLE n1_snapshot_reader')
        try:
            candidate_state.snapshot(independent, producer)
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError('RLS-hidden rows must fault')
        finally:
            independent.execute('RESET ROLE')
        independent.execute('ALTER TABLE "Other.Schema"."Odd.Table" DISABLE ROW LEVEL SECURITY')
        independent.execute('REVOKE SELECT ON "Other.Schema"."Odd.Table" FROM n1_snapshot_reader')
        independent.execute('SET ROLE n1_snapshot_reader')
        try:
            candidate_state.snapshot(independent, producer)
        except psycopg.errors.InsufficientPrivilege:
            pass
        else:
            raise AssertionError('unreadable table must fault')
        finally:
            independent.execute('RESET ROLE')
        for create, remove in (
                ('CREATE SEQUENCE public.n1_unsupported', 'DROP SEQUENCE public.n1_unsupported'),
                ('CREATE VIEW public.n1_unsupported AS SELECT 1 AS id', 'DROP VIEW public.n1_unsupported')):
            independent.execute(create)
            try:
                candidate_state.snapshot(independent, producer)
            except contract.Refused:
                pass
            else:
                raise AssertionError('unsupported relation must fault')
            finally:
                independent.execute(remove)
        independent.execute('DROP TABLE public.authfrds')
        missing = candidate_state.snapshot(independent, producer)
        assert 'authfrds' not in missing and missing != expected
        try:
            candidate_state.load_committed(store, root, independent)
        except contract.Refused:
            pass
        else:
            raise AssertionError('consumed loader must not run again')
        print(json.dumps(dict(status='PUBLIC_COMPLETE_INITIAL_STATE_ONLY',
            table_count=result['table_count'], extra_table_caught=True,
            all_user_schemas=True, exact_numeric=True, rls_and_privilege_fault=True,
            unsupported_relation_fault=True, large_object_fault=True,
            temporary_schema_excluded=True, missing_table_caught=True,
            candidate_replay=False, qualified=False), sort_keys=True))


def exercise(port):
    import psycopg
    connect = dict(host='127.0.0.1', port=port, user='postgres', dbname='postgres',
                   sslmode='disable', gssencmode='disable', connect_timeout=5)
    # Public job-specific disposable database only; refuse any preexisting table.
    with psycopg.connect(**connect, autocommit=True) as independent:
        independent.execute('CREATE TABLE public.n1_observer_public (id integer PRIMARY KEY, value text NOT NULL)')
        relay = pg.Relay(('127.0.0.1', port), binding='a' * 64,
                         deadline=time.monotonic() + 30)
        worker = threading.Thread(target=relay.run, name='public-pg-observer')
        worker.start()
        try:
            candidate = dict(connect, port=relay.address[1])
            with psycopg.connect(**candidate) as observed:
                observed.execute('INSERT INTO public.n1_observer_public VALUES (%s,%s)', (1, 'PUBLIC COMMITTED'))
                observed.commit()
                assert independent.execute('SELECT * FROM public.n1_observer_public ORDER BY id').fetchall() == [(1, 'PUBLIC COMMITTED')]
                observed.execute('INSERT INTO public.n1_observer_public VALUES (%s,%s)', (2, 'PUBLIC ROLLED BACK'))
                observed.rollback()
                assert independent.execute('SELECT * FROM public.n1_observer_public ORDER BY id').fetchall() == [(1, 'PUBLIC COMMITTED')]
                try:
                    observed.execute('INSERT INTO public.n1_observer_public VALUES (%s,%s)', (1, 'PUBLIC DUPLICATE'))
                except psycopg.errors.UniqueViolation:
                    observed.rollback()
                else:
                    raise AssertionError('public duplicate must fail')
            worker.join(5)
            assert not worker.is_alive() and relay.failure is None and relay.result is not None
            transactions = relay.result['transactions']
            assert [t['outcome'] for t in transactions] == ['COMMIT', 'ROLLBACK', 'ROLLBACK']
            assert transactions[2]['sqlstates'] == ['23505']
            assert not any(t['sqlstates'] for t in transactions[:2])
            assert independent.execute('SELECT * FROM public.n1_observer_public ORDER BY id').fetchall() == [(1, 'PUBLIC COMMITTED')]
            print(json.dumps(dict(status='PUBLIC_POSTGRES_OBSERVER_ONLY',
                outcomes=[t['outcome'] for t in transactions], independent_durability_checked=True,
                candidate_replay=False, qualified=False), sort_keys=True))
        finally:
            relay.close()
            worker.join(5)
            assert not worker.is_alive(), 'observer cleanup incomplete'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    exercise(args.port)
    exercise_state(args.port)
