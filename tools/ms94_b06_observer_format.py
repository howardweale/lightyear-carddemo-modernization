"""Versioned bounded observer decoding. Historical records pass through unchanged."""
import base64
import binascii
from tools.ms94_b06_admission import check

FORMAT = 'bounded-observer-v1'
BINARY_FIELDS = {'constant_pool_base64': 'constant_pool_hex',
                 'bytecode_base64': 'bytecode_hex',
                 'definition_input_base64': 'definition_input_hex',
                 'returned_bytes_base64': 'returned_bytes_hex'}


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in BINARY_FIELDS:
            target = BINARY_FIELDS[key]
            check(target not in value and isinstance(item, str) and len(item) <= 1398104,
                  'observer-bounded-binary-shape')
            try:
                raw = base64.b64decode(item, validate=True)
            except (ValueError, binascii.Error):
                check(False, 'observer-bounded-binary-encoding')
            check(len(raw) <= 1024*1024 and base64.b64encode(raw).decode('ascii') == item,
                  'observer-bounded-binary-bound')
            result[target] = raw.hex()
        else:
            result[key] = decode(item)
    return result


def normalize(event):
    if event.get('observer_format') != FORMAT:
        check(event.get('kind') != 'class-definition-v3', 'observer-bounded-unannounced')
        return event
    result = decode(event)
    if result['kind'] == 'class-definition-v3':
        result['kind'] = 'class-definition-v2'
    return result


def java_json(value):
    """The v3 writer's compact UTF-8 JSON; control escapes are always u00xx."""
    import json
    if isinstance(value, dict):
        return '{' + ','.join(java_json(str(k)) + ':' + java_json(v) for k,v in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ','.join(java_json(v) for v in value) + ']'
    if isinstance(value, str):
        return '"' + ''.join(('\\' + c if c in ('"', '\\') else
                              '\\u%04x' % ord(c) if ord(c) < 32 else c) for c in value) + '"'
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
