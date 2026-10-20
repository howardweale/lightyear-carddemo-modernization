"""Controller-only bounded leakage scan; never expose matching private values."""
import base64
import binascii
from hashlib import sha256
import json
import re
from urllib.parse import unquote
from .contracts import ContractError

MAX_BYTES = 8 * 1024 * 1024
MAX_VIEWS = 128
MAX_DEPTH = 4
CLASSES = {'expected-state', 'reference-output', 'session-answer'}


def _normalized(text):
    return ''.join(text.casefold().split())


def _decoded_views(text):
    """Preserve case for decoding; normalize only when comparing private text."""
    yield unquote(text, encoding='utf-8', errors='strict')
    try:
        value = json.loads(text)
    except (ValueError, TypeError, RecursionError):
        value = None
    pending = [value]
    visited = 0
    while pending:
        visited += 1
        if visited > MAX_VIEWS:
            raise ContractError('isolation-scan-limit')
        item = pending.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            pending.extend(item); pending.extend(item.values())
    # Whole whitespace-split encodings and encoded tokens embedded in prose/JSON.
    compact = ''.join(text.split())
    candidates = {compact}
    candidates.update(re.findall(r'(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{16,}={0,2}', text))
    candidates.update(re.findall(r'(?<![0-9A-Fa-f])(?:0x)?[0-9A-Fa-f]{16,}', text))
    if len(candidates) > MAX_VIEWS:
        raise ContractError('isolation-scan-limit')
    for token in candidates:
        if re.fullmatch(r'(?:0x)?[0-9A-Fa-f]{16,}', token):
            try:
                yield bytes.fromhex(token.removeprefix('0x')).decode('utf-8')
            except (ValueError, UnicodeError):
                pass
        if re.fullmatch(r'[A-Za-z0-9+/_-]{16,}={0,2}', token):
            try:
                yield base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True).decode('utf-8')
            except (ValueError, UnicodeError, binascii.Error):
                pass
    if re.search(r'(?:\\x[0-9A-Fa-f]{2}){8,}', text):
        yield re.sub(r'(?:\\x[0-9A-Fa-f]{2}){8,}',
                     lambda m: bytes.fromhex(m.group().replace('\\x', '')).decode('utf-8'), text)


def scan(artifacts, canaries, expected_values):
    if set(canaries) != CLASSES:
        raise ContractError('isolation-canary-classes')
    tokens = list(canaries.values())
    if any(not isinstance(t, str) or len(_normalized(t)) < 32 for t in tokens):
        raise ContractError('isolation-canary-tokens')
    tokens = {_normalized(t) for t in tokens}
    if len(tokens) != 3:
        raise ContractError('isolation-canary-tokens')
    windows = set()
    for value in expected_values:
        if not isinstance(value, str) or len(value.encode('utf-8')) > MAX_BYTES:
            raise ContractError('isolation-expected-value')
        for source in (value, _normalized(value)):
            windows.update(_normalized(source[i:i+40]) for i in range(max(0, len(source)-39)))
    windows.discard('')
    rows = []
    for name, data in artifacts:
        if not isinstance(data, (str, bytes)):
            raise ContractError('isolation-artifact-type')
        raw = data if isinstance(data, bytes) else data.encode('utf-8')
        if len(raw) > MAX_BYTES:
            raise ContractError('isolation-scan-limit')
        text = raw.decode('utf-8', errors='replace')
        pending = [(text, 0)]; seen = set(); total = 0
        while pending:
            view, depth = pending.pop()
            if view in seen:
                continue
            seen.add(view); total += len(view.encode('utf-8'))
            if len(seen) > MAX_VIEWS or total > MAX_BYTES * 4:
                raise ContractError('isolation-scan-limit')
            normalized = _normalized(view)
            if any(token in normalized for token in tokens | windows):
                raise ContractError('isolation-breach')
            try:
                for decoded in _decoded_views(view):
                    if decoded != view and decoded not in seen:
                        if depth >= MAX_DEPTH:
                            raise ContractError('isolation-scan-limit')
                        pending.append((decoded, depth + 1))
                        if len(pending) > MAX_VIEWS:
                            raise ContractError('isolation-scan-limit')
            except UnicodeError:
                raise ContractError('isolation-scan-encoding') from None
        rows.append(dict(artifact=name, sha256=sha256(raw).hexdigest()))
    return dict(status='passed', scanned=rows, canary_classes=sorted(canaries),
                expected_window_count=len(windows), normalization='casefold-whitespace-base64-hex-url/1')
