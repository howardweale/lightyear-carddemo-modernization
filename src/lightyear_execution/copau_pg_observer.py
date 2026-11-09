"""Bounded external PostgreSQL protocol-3.0 observation, not qualification.

Loopback-only relay for a separately admitted disposable database. It observes
server transaction completions, never logs passwords, SQL, parameters or rows.
Caller/request ownership, private custody and candidate routing remain separate.
No TLS downgrade: SSL/GSS negotiation is refused, not answered with fallback.
"""
import ipaddress
import re
import selectors
import socket
import struct
import time

from lightyear_execution import copau_full_state_contract as contract


MAX_FRAME = 8 * 1024 * 1024
MAX_STREAM = 64 * 1024 * 1024
MAX_EVENTS = 4096


class Backend:
    """One connection, ordered backend bytes, immutable original deadline."""
    def __init__(self, binding):
        contract.require(isinstance(binding, str) and contract.SHA.fullmatch(binding))
        self.binding = binding
        self.buffer = bytearray()
        self.total = 0
        self.authenticated = False
        self.ready = False
        self.active = None
        self.closing = None
        self.events = []
        self.transactions = []
        self.failure = None

    def refuse(self, reason='pg-observation-refused'):
        self.failure = self.failure or reason
        raise contract.Refused(self.failure)

    def feed(self, raw):
        if self.failure:
            self.refuse()
        self.total += len(raw)
        if self.total > MAX_STREAM:
            self.refuse('pg-observation-limit')
        self.buffer.extend(raw)
        while len(self.buffer) >= 5:
            length = struct.unpack('!I', self.buffer[1:5])[0]
            if not 4 <= length <= MAX_FRAME:
                self.refuse('pg-frame-size')
            if len(self.buffer) < length + 1:
                return
            tag, body = bytes(self.buffer[:1]), bytes(self.buffer[5:length + 1])
            del self.buffer[:length + 1]
            self.message(tag, body)

    def event(self, value):
        if len(self.events) >= MAX_EVENTS:
            self.refuse('pg-event-limit')
        self.events.append(value)
        if self.active is not None:
            self.active.append(value)

    def message(self, tag, body):
        if tag == b'R':
            if len(body) < 4 or self.authenticated:
                self.refuse('pg-auth-sequence')
            method = struct.unpack('!I', body[:4])[0]
            if method == 0 and len(body) == 4:
                self.authenticated = True
            elif method not in (3, 5, 10, 11, 12):
                self.refuse('pg-auth-method')
            return  # Authentication bytes are never retained.
        if tag in (b'S', b'K', b'N'):
            return  # Parameters, cancel key and notice text are never retained.
        if not self.authenticated:
            self.refuse('pg-before-authentication')
        if tag in (b'T', b'D', b'1', b'2', b'3', b't', b'n'):
            return  # Row/parameter descriptions, values and extended acknowledgments.
        if tag == b'C':
            if not body.endswith(b'\0') or b'\0' in body[:-1]:
                self.refuse('pg-command-frame')
            try:
                command = body[:-1].decode('ascii')
            except UnicodeDecodeError:
                self.refuse('pg-command-frame')
            if command == 'BEGIN':
                if not self.ready or self.active is not None or self.closing:
                    self.refuse('pg-nested-or-unready-transaction')
                self.active = []
            elif command in ('COMMIT', 'ROLLBACK'):
                if self.active is None or self.closing:
                    self.refuse('pg-unbound-transaction-end')
                self.closing = command
            elif not (command in ('SET', 'SHOW', 'RESET') or
                      re.fullmatch(r'(SELECT|UPDATE|DELETE) [0-9]+|INSERT [0-9]+ [0-9]+', command)):
                self.refuse('pg-command-unsupported')
            elif command.startswith(('INSERT ', 'UPDATE ', 'DELETE ')) and self.active is None:
                self.refuse('pg-autocommit-write-refused')
            # A command tag contains only operation/count, not SQL or values.
            self.event({'command': command})
            return
        if tag == b'E':
            fields = body.split(b'\0')
            codes = [f[1:] for f in fields if f.startswith(b'C')]
            if not body.endswith(b'\0\0') or len(codes) != 1 or len(codes[0]) != 5:
                self.refuse('pg-error-frame')
            try:
                code = codes[0].decode('ascii')
            except UnicodeDecodeError:
                self.refuse('pg-error-frame')
            if not code.isalnum() or code != code.upper():
                self.refuse('pg-error-code')
            self.event({'sqlstate': code})  # No diagnostic message/detail/hint.
            return
        if tag == b'Z':
            if body not in (b'I', b'T', b'E'):
                self.refuse('pg-ready-frame')
            if body == b'I':
                if self.active is not None:
                    if self.closing not in ('COMMIT', 'ROLLBACK'):
                        self.refuse('pg-end-not-observed')
                    errors = [e['sqlstate'] for e in self.active if 'sqlstate' in e]
                    if self.closing == 'COMMIT' and errors:
                        self.refuse('pg-error-then-commit')
                    self.transactions.append(dict(outcome=self.closing,
                        events=list(self.active), sqlstates=errors))
                    self.active = self.closing = None
                elif self.closing:
                    self.refuse('pg-unbound-ready')
            elif self.active is None or self.closing:
                self.refuse('pg-transaction-state-mismatch')
            self.ready = True
            return
        # COPY, replication, notifications, suspended portals and unknown protocol
        # cannot be treated as complete evidence for this bounded N1 route.
        self.refuse('pg-backend-message-unsupported')

    def finish(self):
        if self.failure:
            self.refuse()
        if self.buffer or not self.ready or self.active is not None or self.closing:
            self.refuse('pg-incomplete-observation')
        contract.require(self.transactions, 'pg-no-transaction-observed')
        return dict(schema='copau-pg-observation/1', binding_sha256=self.binding,
            transactions=self.transactions, events_sha256=contract.sha(contract.encoded(self.events)),
            qualified=False, ownership_verified=False, status='TRANSACTION_OBSERVATION_ONLY')


def _remaining(deadline):
    value = deadline - time.monotonic()
    contract.require(value > 0, 'pg-original-deadline')
    return value


def _read_exact(sock, size, deadline):
    result = bytearray()
    while len(result) < size:
        sock.settimeout(_remaining(deadline))
        part = sock.recv(size - len(result))
        contract.require(part, 'pg-startup-eof')
        result.extend(part)
    return bytes(result)


class Relay:
    """Exactly one downstream connection; no retry, resumption or port fallback.

    Construct on the controller side, then run in an owned thread. The original
    deadline includes accept, connect, startup and all traffic. Calling close
    closes both sockets as well as the listener; no leaked upstream connection.
    This is not an OS isolation boundary or a private execution admission.
    """
    def __init__(self, upstream, *, binding, deadline):
        host, port = upstream
        contract.require(ipaddress.ip_address(host).is_loopback and
                         type(port) is int and 0 < port <= 65535 and port != 8768)
        contract.require(type(deadline) in (int, float) and
                         time.monotonic() < deadline < time.monotonic() + 600)
        self.upstream, self.deadline = upstream, deadline
        self.backend = Backend(binding)
        self.result, self.failure = None, None
        self.sockets = []
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sockets.append(self.listener)
        self.listener.bind(('127.0.0.1', 0))
        contract.require(self.listener.getsockname()[1] != 8768)
        self.listener.listen(1)
        self.address = self.listener.getsockname()

    def close(self):
        for sock in self.sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def run(self):
        try:
            self.listener.settimeout(_remaining(self.deadline))
            client, _ = self.listener.accept()
            self.sockets.append(client)
            self.listener.close()  # No second client can silently share evidence.
            length_raw = _read_exact(client, 4, self.deadline)
            length = struct.unpack('!I', length_raw)[0]
            contract.require(8 <= length <= 10000, 'pg-startup-length')
            body = _read_exact(client, length - 4, self.deadline)
            contract.require(body[:4] == struct.pack('!I', 196608), 'pg-protocol-3-only')
            contract.require(body.endswith(b'\0\0'), 'pg-startup-frame')
            server = socket.create_connection(self.upstream, timeout=_remaining(self.deadline))
            self.sockets.append(server)
            server.sendall(length_raw + body)
            # Password/SQL bytes are forwarded transiently, never logged/hashed.
            with selectors.DefaultSelector() as selector:
                selector.register(client, selectors.EVENT_READ, server)
                selector.register(server, selectors.EVENT_READ, client)
                client_total = 0
                while True:
                    ready = selector.select(_remaining(self.deadline))
                    contract.require(ready, 'pg-original-deadline')
                    for key, _ in ready:
                        source, target = key.fileobj, key.data
                        source.settimeout(_remaining(self.deadline))
                        raw = source.recv(65536)
                        if not raw:
                            self.result = self.backend.finish()
                            return
                        if source is server:
                            self.backend.feed(raw)
                        else:
                            client_total += len(raw)
                            contract.require(client_total <= MAX_STREAM, 'pg-client-limit')
                        target.settimeout(_remaining(self.deadline))
                        target.sendall(raw)
        except BaseException:
            self.failure = self.backend.failure or 'pg-relay-incomplete'
            self.result = None  # No private exception traceback escapes the thread.
        finally:
            self.close()
