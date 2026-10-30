"""One HTTP exchange for supervised engineering; no live client or run entry.

This is not operation authorization, a global two-send limiter, or qualification
evidence. A future approved caller must own durable send reservation, supervision,
the fixed TLS connection, whole-process containment, and retained round receipts.
"""
import hashlib
import http.client
import math
import time

from lightyear_factory.contracts import ContractError
from tools.ci.supervised_intcalc_boundary import LABEL, generation_request

BODY_LIMIT = 1048576


def _remaining(deadline):
    if type(deadline) is not float or not math.isfinite(deadline):
        raise ContractError('supervised-exchange-deadline')
    remaining = deadline - time.monotonic()
    if remaining <= 0 or remaining > 1200:
        raise ContractError('supervised-exchange-deadline')
    return remaining


def _exchange_once(connection, candidate, authorization, deadline):
    """One POST, no redirect handling/retry/reconnect loop; close on every exit.

    Only offline loopback CI invokes this kernel currently. There is deliberately
    no production endpoint factory, credential lookup, command line or run gate.
    Socket timeouts are not an aggregate header-read or OS scheduling guarantee.
    """
    # Freeze public source into the existing exact request before any network IO.
    body = generation_request(candidate)
    if (type(authorization) is not str or not authorization.startswith('Bearer ')
            or not 8 <= len(authorization) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in authorization[7:])):
        raise ContractError('supervised-exchange-authorization-format')
    if type(connection) not in (http.client.HTTPConnection, http.client.HTTPSConnection):
        raise ContractError('supervised-exchange-connection-type')
    if connection.sock is not None:
        raise ContractError('supervised-exchange-connection-reuse')
    started = time.monotonic()
    response = None
    try:
        connection.timeout = _remaining(deadline)
        # http.client does not implement redirects, retry policies, SDK fallback,
        # provider tools, token-count requests, or a response-resumption protocol.
        connection.request('POST', '/v1/responses', body=body,
                           headers={'Authorization': authorization,
                                    'Content-Type': 'application/json',
                                    'Accept': 'application/json',
                                    'Accept-Encoding': 'identity',
                                    'Connection': 'close'})
        transport_socket = connection.sock
        transport_socket.settimeout(_remaining(deadline))
        response = connection.getresponse()
        if response.status != 200:
            raise ContractError('supervised-exchange-http-refused')
        headers = response.getheaders()
        lengths = [v for k, v in headers if k.lower() == 'content-length']
        encodings = [v for k, v in headers if k.lower() == 'content-encoding']
        transfers = [v for k, v in headers if k.lower() == 'transfer-encoding']
        types = [v for k, v in headers if k.lower() == 'content-type']
        if (len(lengths) > 1 or len(encodings) > 1 or transfers
                or encodings and encodings != ['identity']
                or len(types) != 1 or types[0].split(';', 1)[0].strip().lower() != 'application/json'):
            raise ContractError('supervised-exchange-response-framing')
        length = None
        if lengths:
            if not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 7:
                raise ContractError('supervised-exchange-response-length')
            length = int(lengths[0])
            if not 0 < length <= BODY_LIMIT:
                raise ContractError('supervised-exchange-response-length')
        result = bytearray()
        while True:
            # Keep the original socket reference when HTTPResponse takes ownership.
            transport_socket.settimeout(_remaining(deadline))
            block = response.read1(min(8192, BODY_LIMIT + 1 - len(result)))
            if not block:
                break
            result.extend(block)
            if len(result) > BODY_LIMIT:
                raise ContractError('supervised-exchange-response-size')
        _remaining(deadline)
        if not result or length is not None and len(result) != length:
            raise ContractError('supervised-exchange-response-truncated')
        raw = bytes(result)
        return raw, dict(label=LABEL, request_sha256=hashlib.sha256(body).hexdigest(),
                         response_sha256=hashlib.sha256(raw).hexdigest(),
                         response_bytes=len(raw), elapsed_seconds=time.monotonic()-started,
                         physical_requests_attempted=1, qualification_evidence=False)
    except ContractError:
        raise
    except (OSError, http.client.HTTPException, ValueError, AttributeError):
        # No response body, reason phrase, headers, credential, or exception text.
        # A failed exchange may have been billed; the future caller must stop.
        raise ContractError('supervised-exchange-outcome-unknown') from None
    finally:
        if response is not None:
            response.close()
        connection.close()
