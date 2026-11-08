"""Immutable staging for the whole N1 session; no admission or private CLI.

The caller must supply a reviewed private store and an authenticated commitment
acknowledgment verifier. This module supplies neither custody nor authentication.
Missing verification fails before oracle entry. All writes are exclusive; a
consumed oracle attempt cannot be retried through this stage.
"""
import hashlib
import json
import re


SESSION = 'authorization-pages-and-fraud'
LIMIT = 64 * 1024 * 1024
CHUNK = 65536
SHA = re.compile(r'[0-9a-f]{64}')


class Refused(Exception):
    """Fixed public reason only; never propagate private exception text."""


def require(condition, reason='full-state-refused'):
    if not condition:
        raise Refused(reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decoded(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: require(False))
    except Exception:
        raise Refused('invalid-private-json') from None


def put_blob(store, name, raw):
    """Chunk through the existing private Store's bounded exclusive writes."""
    require(re.fullmatch('[a-z][a-z0-9-]*', name) and isinstance(raw, bytes)
            and 0 < len(raw) <= LIMIT)
    pieces = [raw[i:i + CHUNK] for i in range(0, len(raw), CHUNK)]
    names = [f'{name}-{i}.json' for i in range(len(pieces))]
    store.absent(name + '-manifest.json', *names)
    # Hex chunks keep every individual file inside the existing 262144B limit.
    for path, piece in zip(names, pieces):
        store.write(path, encoded({'hex': piece.hex()}))
    manifest = dict(sha256=sha(raw), size=len(raw), chunks=[sha(p) for p in pieces])
    store.write(name + '-manifest.json', encoded(manifest))
    require(get_blob(store, name) == raw)
    return manifest['sha256']


def get_blob(store, name):
    require(re.fullmatch('[a-z][a-z0-9-]*', name))
    manifest = decoded(store.read(name + '-manifest.json'))
    require(set(manifest) == {'sha256', 'size', 'chunks'}
            and type(manifest['size']) is int and 0 < manifest['size'] <= LIMIT
            and isinstance(manifest['chunks'], list)
            and len(manifest['chunks']) == (manifest['size'] + CHUNK - 1) // CHUNK)
    pieces = []
    for i, digest in enumerate(manifest['chunks']):
        row = decoded(store.read(f'{name}-{i}.json'))
        require(set(row) == {'hex'} and isinstance(row['hex'], str)
                and 0 < len(row['hex']) <= CHUNK * 2)
        try:
            piece = bytes.fromhex(row['hex'])
        except ValueError:
            raise Refused('invalid-private-chunk') from None
        require(sha(piece) == digest)
        pieces.append(piece)
    raw = b''.join(pieces)
    require(len(raw) == manifest['size'] and sha(raw) == manifest['sha256'])
    return raw


def stage_inputs(store, inputs, *, context_sha256, producer_bindings):
    require(isinstance(context_sha256, str) and SHA.fullmatch(context_sha256))
    require(isinstance(producer_bindings, dict) and producer_bindings
            and all(isinstance(k, str) and isinstance(v, str) and SHA.fullmatch(v)
                    for k, v in producer_bindings.items()))
    store.absent('n1-commitment.json', 'n1-ack.json', 'n1-consumed.json',
                 'n1-complete.json')
    digest = put_blob(store, 'n1-input', encoded(inputs))
    commitment = dict(schema='copau-full-session-input-commitment/1',
                      session=SESSION, context_sha256=context_sha256,
                      input_sha256=digest, producer_bindings=producer_bindings)
    raw = encoded(commitment)
    store.write('n1-commitment.json', raw)
    return raw


def _commitment(store):
    raw = store.read('n1-commitment.json')
    value = decoded(raw)
    require(set(value) == {'schema', 'session', 'context_sha256', 'input_sha256',
                           'producer_bindings'}
            and value['schema'] == 'copau-full-session-input-commitment/1'
            and value['session'] == SESSION and encoded(value) == raw)
    require(sha(get_blob(store, 'n1-input')) == value['input_sha256'])
    return raw, value


def acknowledge(store, acknowledgment, *, verifier):
    """verifier must authenticate bytes and return the exact committed payload.

    No boolean, string 'approved', optional acknowledgment, or default verifier
    is accepted. Authenticity and public-key/context policy belong to the later
    reviewed adapter; a caller-supplied lambda is NOT production authentication.
    """
    store.absent('n1-ack.json', 'n1-consumed.json', 'n1-complete.json')
    raw, _ = _commitment(store)
    require(isinstance(acknowledgment, bytes) and 0 < len(acknowledgment) <= CHUNK)
    try:
        authenticated = verifier(acknowledgment)
    except Exception:
        raise Refused('ack-authentication-failed') from None
    require(type(authenticated) is bytes and authenticated == raw, 'ack-binding-refused')
    store.write('n1-ack.json', encoded(dict(commitment_sha256=sha(raw),
                acknowledgment_hex=acknowledgment.hex())))


def consume(store, *, verifier, producer_bindings):
    """Reauthenticate the persisted ACK, then consume before calling any oracle."""
    store.absent('n1-consumed.json', 'n1-complete.json')
    raw, value = _commitment(store)
    require(value['producer_bindings'] == producer_bindings, 'producer-binding-refused')
    ack_raw = store.read('n1-ack.json')
    ack = decoded(ack_raw)
    require(set(ack) == {'commitment_sha256', 'acknowledgment_hex'}
            and ack['commitment_sha256'] == sha(raw))
    try:
        signed = bytes.fromhex(ack['acknowledgment_hex'])
        authenticated = verifier(signed)
    except Exception:
        raise Refused('ack-authentication-failed') from None
    require(type(authenticated) is bytes and authenticated == raw, 'ack-binding-refused')
    inputs = decoded(get_blob(store, 'n1-input'))
    binding = dict(commitment_sha256=sha(raw), acknowledgment_sha256=sha(signed))
    store.write('n1-consumed.json', encoded(binding))
    return inputs, binding
