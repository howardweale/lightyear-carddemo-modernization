"""CI-only public disposable PostgreSQL commit/rollback observation exercise.

Not candidate proof: this client is psycopg, not InteractionEngine. No private
input/custody/signing/provider capability, receipt or activation is supplied.
"""
import argparse
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
        result = candidate_state.load_committed(store, root, independent)
        expected = contract.decoded(contract.get_blob(store, 'n1-initial'))
        assert candidate_state.snapshot(independent, producer) == expected
        independent.execute('CREATE TABLE public.n1_unexpected (id integer)')
        assert candidate_state.snapshot(independent, producer) != expected
        try:
            candidate_state.load_committed(store, root, independent)
        except contract.Refused:
            pass
        else:
            raise AssertionError('consumed loader must not run again')
        print(json.dumps(dict(status='PUBLIC_COMPLETE_INITIAL_STATE_ONLY',
            table_count=result['table_count'], extra_table_caught=True,
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
