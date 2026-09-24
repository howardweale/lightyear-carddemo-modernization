"""Strict, copybook-driven fixed-record decoding without equivalence rules."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
import json
from pathlib import Path
import re

from .source import sha, tokenize


class LayoutError(ValueError):
    pass


class DecodeError(ValueError):
    pass


@dataclass
class Node:
    level: int
    name: str
    line: int
    occurs: int = 1
    picture: str | None = None
    usage: str = 'DISPLAY'
    sign: str = 'TRAILING'
    separate: bool = False
    children: list = field(default_factory=list)


@dataclass(frozen=True)
class Field:
    path: str
    offset: int
    length: int
    picture: str
    usage: str
    digits: int
    scale: int
    signed: bool
    sign: str
    separate: bool
    filler: bool
    line: int


@dataclass(frozen=True)
class Layout:
    name: str
    copybook_sha256: str
    record_length: int
    fields: tuple[Field, ...]

    def manifest(self):
        return dict(schema_version='1.0', name=self.name, copybook_sha256=self.copybook_sha256,
                    record_length=self.record_length, fields=[asdict(f) for f in self.fields])


def picture(pic):
    if not re.fullmatch(r'S?(?:[X9AV](?:\([0-9]+\))?)+', pic):
        raise LayoutError(f'unsupported picture {pic}')
    expanded = ''
    for symbol, count in re.findall(r'([SX9AV])(?:\(([0-9]+)\))?', pic):
        n = int(count or 1)
        if not 1 <= n <= 32760:
            raise LayoutError('picture exceeds fixed-record limit')
        expanded += symbol*n
    if re.fullmatch(r'X+|A+', expanded):
        return expanded, 0, 0, False
    if not re.fullmatch(r'S?9+(?:V9+)?', expanded):
        raise LayoutError(f'unsupported edited/mixed picture {pic}')
    return expanded, expanded.count('9'), len(expanded.split('V')[1]) if 'V' in expanded else 0, expanded.startswith('S')


def compile_copybook(text: str, name='<memory>') -> Layout:
    """Compile one level-01 fixed layout. Unsupported clauses fail closed.

    Supports groups, fixed OCCURS, DISPLAY X/A/9/S9/V, COMP-3 and separate
    leading/trailing signs. REDEFINES/ODO/binary/alignment/edited pictures need
    a different explicit layout implementation, never a guessed offset.
    """
    tokens = tokenize(text, name)
    declarations, current = [], []
    for t in tokens:
        if t.text == '.':
            if current:
                declarations.append(current); current = []
        else:
            current.append(t)
    if current:
        raise LayoutError('declaration must end with a period')
    root, stack = None, []
    for declaration in declarations:
        words = [t.text for t in declaration]
        if len(words) < 2 or not re.fullmatch(r'[0-9]{2}', words[0]):
            raise LayoutError('expected a level-number data declaration')
        level, name = int(words[0]), words[1]
        if level == 88:
            if not stack or 'VALUE' not in words[2:]:
                raise LayoutError('invalid level-88 condition')
            continue
        if level not in range(1, 50) or not re.fullmatch(r'[A-Z0-9][A-Z0-9-]*', name):
            raise LayoutError('unsupported level or data name')
        node = Node(level, name, declaration[0].line)
        k = 2
        seen_clauses = set()
        while k < len(words):
            word = words[k]
            clause = ('PIC' if word in ('PIC', 'PICTURE') else
                      'USAGE' if word in ('USAGE', 'DISPLAY', 'COMP-3', 'COMPUTATIONAL-3', 'PACKED-DECIMAL') else word)
            if clause in seen_clauses: raise LayoutError(f'duplicate {clause} clause')
            seen_clauses.add(clause)
            if word in ('PIC', 'PICTURE'):
                if node.picture is not None:
                    raise LayoutError('duplicate picture')
                k += 1
                if k < len(words) and words[k] == 'IS': k += 1
                parts = []
                while k < len(words) and re.fullmatch(r'[SX9AV0-9]+|\(|\)', words[k]):
                    parts.append(words[k]); k += 1
                node.picture = ''.join(parts)
                picture(node.picture)
            elif word in ('USAGE', 'DISPLAY', 'COMP-3', 'COMPUTATIONAL-3', 'PACKED-DECIMAL'):
                if word == 'USAGE':
                    k += 1
                    if k < len(words) and words[k] == 'IS': k += 1
                    if k == len(words): raise LayoutError('missing usage')
                    word = words[k]
                if word not in ('DISPLAY', 'COMP-3', 'COMPUTATIONAL-3', 'PACKED-DECIMAL'):
                    raise LayoutError(f'unsupported usage {word}')
                node.usage = 'DISPLAY' if word == 'DISPLAY' else 'COMP-3'; k += 1
            elif word == 'OCCURS':
                k += 1
                if k == len(words) or not words[k].isdigit() or not 1 <= int(words[k]) <= 32760:
                    raise LayoutError('OCCURS requires a bounded positive literal')
                node.occurs = int(words[k]); k += 1
                if k < len(words) and words[k] == 'TIMES': k += 1
            elif word == 'SIGN':
                k += 1
                if k < len(words) and words[k] == 'IS': k += 1
                if k == len(words) or words[k] not in ('LEADING', 'TRAILING'):
                    raise LayoutError('SIGN requires LEADING or TRAILING')
                node.sign = words[k]; k += 1
                if k < len(words) and words[k] == 'SEPARATE':
                    node.separate = True; k += 1
                    if k < len(words) and words[k] == 'CHARACTER': k += 1
            elif word == 'VALUE':
                # Initialization does not change offsets. Accept one literal
                # or figurative constant, not arbitrary trailing clauses.
                k += 1
                if k < len(words) and words[k] == 'IS': k += 1
                if k == len(words) or not (words[k].startswith(("'", '"')) or
                    re.fullmatch(r'[+-]?[0-9]+(?:\.[0-9]+)?', words[k]) or
                    words[k] in ('SPACE', 'SPACES', 'ZERO', 'ZEROS', 'ZEROES', 'LOW-VALUES', 'HIGH-VALUES')):
                    raise LayoutError('unsupported VALUE')
                k += 1
            else:
                raise LayoutError(f'line {node.line}: unsupported clause {word}')
        while stack and stack[-1].level >= level: stack.pop()
        if level == 1:
            if root is not None: raise LayoutError('exactly one level-01 record required')
            root = node
        elif not stack:
            raise LayoutError('field has no containing level-01 record')
        else:
            if stack[-1].picture is not None: raise LayoutError('elementary field cannot contain children')
            stack[-1].children.append(node)
        stack.append(node)
    if root is None: raise LayoutError('empty copybook')
    fields, offset = [], 0

    def emit(node, prefix):
        nonlocal offset
        for n in range(node.occurs):
            path = prefix + node.name + (f'[{n+1}]' if node.occurs > 1 else '')
            if node.picture is None:
                if not node.children or node.usage != 'DISPLAY' or node.separate or node.sign != 'TRAILING':
                    raise LayoutError('unsupported or empty group')
                seen = set()
                for j, child in enumerate(node.children):
                    if child.name != 'FILLER' and child.name in seen: raise LayoutError('duplicate sibling data name')
                    seen.add(child.name)
                    emit(child, path+'.'+(f'#{j+1}.' if child.name == 'FILLER' else ''))
            else:
                expanded, digits, scale, signed = picture(node.picture)
                if node.usage == 'COMP-3' and (not digits or node.separate or node.sign != 'TRAILING'):
                    raise LayoutError('invalid packed usage or sign clause')
                if (node.separate or node.sign != 'TRAILING') and not signed:
                    raise LayoutError('SIGN requires signed numeric DISPLAY')
                length = (digits+2)//2 if node.usage == 'COMP-3' else (digits or len(expanded)) + int(node.separate)
                if offset+length > 32760: raise LayoutError('layout exceeds fixed-record limit')
                fields.append(Field(path, offset, length, node.picture, node.usage, digits, scale,
                                    signed, node.sign, node.separate, node.name == 'FILLER', node.line))
                offset += length
    emit(root, '')
    return Layout(root.name, sha(text.encode()), offset, tuple(fields))


def load_copybook(path: Path):
    # utf-8 without newline conversion: the fingerprint is the original bytes.
    raw = path.read_bytes()
    return compile_copybook(raw.decode('utf-8'), str(path))


def _number(raw: bytes, f: Field, codec: str, sign_policy: str):
    positive, negative = ({12, 15}, {13}) if sign_policy == 'preferred' else ({10, 12, 14, 15}, {11, 13})
    sign_code, is_negative = None, False
    if f.usage == 'COMP-3':
        nibbles = [n for b in raw for n in (b >> 4, b & 15)]
        sign_code = nibbles.pop()
        if len(nibbles) > f.digits:
            if nibbles.pop(0) != 0: raise DecodeError('nonzero packed padding nibble')
        if any(n > 9 for n in nibbles): raise DecodeError('invalid packed decimal digit')
        if sign_code not in (positive | negative if f.signed else {15}):
            raise DecodeError('invalid packed sign for declared picture/policy')
        is_negative = sign_code in negative
        digits = nibbles
    else:
        body = raw
        if f.separate:
            sign_byte = raw[0] if f.sign == 'LEADING' else raw[-1]
            body = raw[1:] if f.sign == 'LEADING' else raw[:-1]
            symbol = bytes([sign_byte]).decode(codec)
            if symbol not in ('+', '-'): raise DecodeError('invalid separate sign')
            sign_code, is_negative = sign_byte, symbol == '-'
        zones, digits = [b >> 4 for b in body], [b & 15 for b in body]
        if any(n > 9 for n in digits): raise DecodeError('invalid zoned decimal digit')
        if f.signed and not f.separate:
            index = 0 if f.sign == 'LEADING' else len(zones)-1
            sign_code = zones[index]
            if sign_code not in positive | negative: raise DecodeError('invalid zoned sign')
            is_negative = sign_code in negative
            zones[index] = 15
        if any(z != 15 for z in zones): raise DecodeError('invalid zoned digit zone')
    # Tuple construction is exact even beyond Decimal's ambient precision and
    # preserves negative zero, unlike arithmetic scaling through float/context.
    value = Decimal((int(is_negative), tuple(digits), -f.scale))
    return dict(value=format(value, 'f'), digits=''.join(str(d) for d in digits),
                scale=f.scale, sign_code=sign_code, negative_zero=is_negative and not any(digits))


def decode_record(layout: Layout, raw: bytes, *, codec='cp037', sign_policy='preferred'):
    if codec not in ('cp037', 'cp500', 'cp1140'):
        raise DecodeError('an explicitly supported single-byte EBCDIC code page is required')
    if sign_policy not in ('preferred', 'ibm-valid'):
        raise DecodeError('unknown sign policy')
    if len(raw) != layout.record_length:
        raise DecodeError(f'record length {len(raw)} != declared {layout.record_length}')
    decoded = []
    for f in layout.fields:
        data = raw[f.offset:f.offset+f.length]
        entry = dict(path=f.path, offset=f.offset, length=f.length, raw_hex=data.hex(), filler=f.filler)
        try:
            entry.update(_number(data, f, codec, sign_policy) if f.digits else dict(value=data.decode(codec)))
        except DecodeError as exc:
            raise DecodeError(f'{f.path} at byte {f.offset}: {exc}') from exc
        decoded.append(entry)
    return dict(copybook_sha256=layout.copybook_sha256, record_sha256=sha(raw), raw_hex=raw.hex(),
                codec=codec, sign_policy=sign_policy, fields=decoded)


def decode_fixed(layout: Layout, raw: bytes, **options):
    if len(raw) % layout.record_length:
        raise DecodeError('truncated or incorrectly framed fixed-block records')
    return [decode_record(layout, raw[i:i+layout.record_length], **options)
            for i in range(0, len(raw), layout.record_length)]


def spool_envelope(raw: bytes, layout: Layout) -> bytes:
    """Synthetic retained HEX export. This is not the z/OSMF binary protocol."""
    if len(raw) % layout.record_length: raise DecodeError('partial record')
    return (json.dumps(dict(format='lightyear-fb-hex-v1', lrecl=layout.record_length,
                            record_count=len(raw)//layout.record_length,
                            copybook_sha256=layout.copybook_sha256, sha256=sha(raw), hex=raw.hex()),
                       sort_keys=True)+'\n').encode('ascii')


def decode_spool(payload: bytes, layout: Layout, **options):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise DecodeError('duplicate spool envelope field')
            result[k] = v
        return result
    try:
        envelope = json.loads(payload.decode('ascii'), object_pairs_hook=unique)
    except (UnicodeError, ValueError) as exc:
        raise DecodeError('spool must be an explicit FB HEX envelope, not translated business bytes') from exc
    keys = {'format', 'lrecl', 'record_count', 'copybook_sha256', 'sha256', 'hex'}
    if not isinstance(envelope, dict) or set(envelope) != keys:
        raise DecodeError('invalid spool envelope')
    if envelope['format'] != 'lightyear-fb-hex-v1' or envelope['copybook_sha256'] != layout.copybook_sha256:
        raise DecodeError('spool layout identity mismatch')
    if type(envelope['lrecl']) is not int or envelope['lrecl'] != layout.record_length:
        raise DecodeError('spool record length mismatch')
    if type(envelope['record_count']) is not int or envelope['record_count'] < 0:
        raise DecodeError('invalid record count')
    encoded = envelope['hex']
    if not isinstance(encoded, str) or not re.fullmatch(r'(?:[0-9a-f]{2})*', encoded):
        raise DecodeError('invalid hex export')
    raw = bytes.fromhex(encoded)
    if len(raw) != envelope['record_count']*layout.record_length or sha(raw) != envelope['sha256']:
        raise DecodeError('incomplete or corrupt spool export')
    return decode_fixed(layout, raw, **options)
