"""Public protocol fixtures; real PostgreSQL coverage has a separate CI job."""
import socket
import struct
import threading
import time
import unittest

from lightyear_execution import copau_pg_observer as pg
from lightyear_execution import copau_full_state_contract as contract


def frame(tag, payload):
    return tag + struct.pack('!I', len(payload) + 4) + payload


def startup():
    return frame(b'R', struct.pack('!I', 0)) + frame(b'Z', b'I')


def transaction(end=b'COMMIT'):
    return (frame(b'C', b'BEGIN\0') + frame(b'Z', b'T') +
            frame(b'C', b'INSERT 0 1\0') + frame(b'Z', b'T') +
            frame(b'C', end + b'\0') + frame(b'Z', b'I'))


class PgObserverTests(unittest.TestCase):
    def test_fragmented_commit_and_rollback_are_distinct(self):
        observer = pg.Backend('a' * 64)
        for value in startup() + transaction() + transaction(b'ROLLBACK'):
            observer.feed(bytes([value]))
        result = observer.finish()
        self.assertEqual([x['outcome'] for x in result['transactions']], ['COMMIT', 'ROLLBACK'])
        self.assertFalse(result['qualified'])
        self.assertFalse(result['ownership_verified'])

    def test_command_success_without_ready_is_not_commit(self):
        for suffix in (b'', frame(b'Z', b'T'), frame(b'Z', b'E')):
            observer = pg.Backend('a' * 64)
            with self.subTest(suffix=suffix), self.assertRaises(contract.Refused):
                observer.feed(startup() + frame(b'C', b'BEGIN\0') +
                              frame(b'C', b'COMMIT\0') + suffix)
                observer.finish()

    def test_error_rollback_preserves_sqlstate_but_never_private_diagnostics(self):
        observer = pg.Backend('a' * 64)
        observer.feed(startup() + frame(b'C', b'BEGIN\0') +
            frame(b'E', b'SERROR\0C23505\0MPRIVATE SENTINEL\0DPRIVATE ROW\0\0') +
            frame(b'Z', b'E') + frame(b'C', b'ROLLBACK\0') + frame(b'Z', b'I'))
        raw = contract.encoded(observer.finish())
        self.assertNotIn(b'PRIVATE', raw)
        self.assertIn(b'23505', raw)
        self.assertEqual(observer.transactions[0]['outcome'], 'ROLLBACK')

    def test_commit_after_error_fails(self):
        observer = pg.Backend('a' * 64)
        with self.assertRaisesRegex(contract.Refused, 'pg-error-then-commit'):
            observer.feed(startup() + frame(b'C', b'BEGIN\0') +
                frame(b'E', b'C23505\0\0') + frame(b'C', b'COMMIT\0') + frame(b'Z', b'I'))

    def test_unbound_commit_autocommit_write_and_unknown_messages_refuse(self):
        for value in (frame(b'C', b'COMMIT\0'), frame(b'C', b'INSERT 0 1\0'),
                      frame(b'C', b'CREATE TABLE\0'), frame(b'G', b'copy'),
                      frame(b's', b''), frame(b'Z', b'T'), frame(b'C', b'INSERT SECRET\0')):
            observer = pg.Backend('a' * 64)
            with self.subTest(value=value), self.assertRaises(contract.Refused):
                observer.feed(startup() + value)

    def test_truncation_bad_length_and_missing_transaction_refuse(self):
        for value in (startup(), startup() + transaction()[:-1],
                      b'C' + struct.pack('!I', 3), b'C' + struct.pack('!I', pg.MAX_FRAME + 1)):
            observer = pg.Backend('a' * 64)
            with self.subTest(value=value), self.assertRaises(contract.Refused):
                observer.feed(value)
                observer.finish()

    def test_first_fault_is_sticky(self):
        observer = pg.Backend('a' * 64)
        with self.assertRaisesRegex(contract.Refused, 'pg-before-authentication'):
            observer.feed(frame(b'C', b'BEGIN\0'))
        with self.assertRaisesRegex(contract.Refused, 'pg-before-authentication'):
            observer.feed(startup() + transaction())

    def test_rows_auth_and_cancel_keys_are_not_retained(self):
        observer = pg.Backend('a' * 64)
        observer.feed(frame(b'R', struct.pack('!I', 10) + b'PRIVATE AUTH') + startup() +
            frame(b'K', b'PRIVATE CANCEL') + frame(b'D', b'PRIVATE ROW') + transaction())
        self.assertNotIn(b'PRIVATE', contract.encoded(observer.finish()))

    def test_ssl_request_refused_without_upstream_or_downgrade(self):
        relay = pg.Relay(('127.0.0.1', 1), binding='a' * 64, deadline=time.monotonic() + 3)
        worker = threading.Thread(target=relay.run)
        worker.start()
        try:
            with socket.create_connection(relay.address, timeout=2) as client:
                client.sendall(struct.pack('!II', 8, 80877103))
                self.assertEqual(client.recv(1), b'')
        finally:
            relay.close()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(relay.result)
        self.assertEqual(relay.failure, 'pg-relay-incomplete')

    def test_remote_target_and_forbidden_port_refuse_before_socket(self):
        for address in [('192.0.2.1', 5432), ('127.0.0.1', 8768)]:
            with self.subTest(address=address), self.assertRaises(contract.Refused):
                pg.Relay(address, binding='a' * 64, deadline=time.monotonic() + 2)
