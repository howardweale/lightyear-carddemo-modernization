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
    redefines: str | None = None
    depending: str | None = None
    occurs_min: int = 1
    width: int = 0
    min_width: int = 0


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
    tree: Node | None = field(default=None, repr=False, compare=False)
    minimum_length: int = 0
    variable: bool = False
    overlays: tuple = ()

    def manifest(self):
        result = dict(schema_version='1.0', name=self.name, copybook_sha256=self.copybook_sha256,
                      record_length=self.record_length, fields=[asdict(f) for f in self.fields])
        if self.variable or self.overlays or any(f.usage in ('BINARY', 'COMP-5') for f in self.fields):
            result.update(schema_version='1.1', minimum_length=self.minimum_length,
                          variable_length=self.variable, overlays=list(self.overlays),
                          binary_storage='IBM 2/4/8 bytes; byte order and truncation supplied at decode')
        return result


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

    Supports IBM binary storage, explicit overlay choices and one bounded ODO
    table with sliding following fields. Alignment, nested ODO, and ODO inside
    overlays/repeated groups are refused rather than assigning guessed offsets.
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
    usages = {'DISPLAY': 'DISPLAY', 'COMP-3': 'COMP-3', 'COMPUTATIONAL-3': 'COMP-3',
              'PACKED-DECIMAL': 'COMP-3', 'BINARY': 'BINARY', 'COMP': 'BINARY',
              'COMPUTATIONAL': 'BINARY', 'COMP-4': 'BINARY', 'COMPUTATIONAL-4': 'BINARY',
              'COMP-5': 'COMP-5', 'COMPUTATIONAL-5': 'COMP-5'}
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
                      'USAGE' if word == 'USAGE' or word in usages else word)
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
            elif word == 'USAGE' or word in usages:
                if word == 'USAGE':
                    k += 1
                    if k < len(words) and words[k] == 'IS': k += 1
                    if k == len(words): raise LayoutError('missing usage')
                    word = words[k]
                if word not in usages:
                    raise LayoutError(f'unsupported usage {word}')
                node.usage = usages[word]; k += 1
            elif word == 'REDEFINES':
                k += 1
                if k == len(words): raise LayoutError('missing REDEFINES target')
                node.redefines = words[k]; k += 1
            elif word == 'OCCURS':
                k += 1
                if k == len(words) or not words[k].isdigit() or not 0 <= int(words[k]) <= 32760:
                    raise LayoutError('OCCURS requires bounded literals')
                node.occurs = node.occurs_min = int(words[k]); k += 1
                variable = k < len(words) and words[k] == 'TO'
                if variable:
                    k += 1
                    if k == len(words) or not words[k].isdigit(): raise LayoutError('missing OCCURS maximum')
                    node.occurs = int(words[k]); k += 1
                    if not node.occurs_min <= node.occurs <= 32760: raise LayoutError('invalid OCCURS bounds')
                if k < len(words) and words[k] == 'TIMES': k += 1
                if variable:
                    if words[k:k+2] != ['DEPENDING', 'ON'] or k+2 >= len(words):
                        raise LayoutError('variable OCCURS requires DEPENDING ON')
                    node.depending = words[k+2]; k += 3
                if node.occurs < 1: raise LayoutError('OCCURS maximum must be positive')
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
    if root.occurs != 1 or root.depending or root.redefines:
        raise LayoutError('level-01 cannot OCCURS or REDEFINE')
    fields, overlays, variables, controllers = [], [], [], {}

    def groups(node):
        result, names = [], set()
        for child in node.children:
            if child.name != 'FILLER' and child.name in names: raise LayoutError('duplicate sibling data name')
            names.add(child.name)
            if child.redefines:
                if not result or child.redefines not in {n.name for n in result[-1]}:
                    raise LayoutError('REDEFINES must name the preceding storage group')
                if child.name == 'FILLER' or any(n.name == 'FILLER' for n in result[-1]):
                    raise LayoutError('FILLER overlay is ambiguous')
                result[-1].append(child)
            else:
                result.append([child])
        return result

    def size(node, repeated=False, overlay=False):
        if node.depending:
            if repeated or overlay or variables: raise LayoutError('nested, repeated, or overlaid ODO is unsupported')
            variables.append(node)
        if node.picture is not None:
            expanded, digits, scale, signed = picture(node.picture)
            if node.usage != 'DISPLAY' and (not digits or node.separate or node.sign != 'TRAILING'):
                raise LayoutError('invalid numeric usage or sign clause')
            if (node.separate or node.sign != 'TRAILING') and not signed:
                raise LayoutError('SIGN requires signed numeric DISPLAY')
            if node.usage in ('BINARY', 'COMP-5'):
                if not 1 <= digits <= 18: raise LayoutError('IBM binary PIC requires 1 to 18 digits')
                width = 2 if digits <= 4 else 4 if digits <= 9 else 8
            else:
                width = (digits+2)//2 if node.usage == 'COMP-3' else (digits or len(expanded)) + int(node.separate)
            node.width = node.min_width = width
        else:
            if not node.children or node.usage != 'DISPLAY' or node.separate or node.sign != 'TRAILING':
                raise LayoutError('unsupported or empty group')
            for alternatives in groups(node):
                for child in alternatives:
                    size(child, repeated or node.occurs > 1 or bool(node.depending), overlay or len(alternatives) > 1)
                node.width += max(c.width*c.occurs for c in alternatives)
                node.min_width += max(c.min_width*c.occurs_min for c in alternatives)
        if node.width*node.occurs > 32760: raise LayoutError('layout exceeds record limit')
    size(root)

    def emit(node, prefix, offset, restricted=False):
        start = offset
        for n in range(node.occurs):
            path = prefix+node.name+(f'[{n+1}]' if node.occurs > 1 or node.depending else '')
            if node.picture is None:
                child_index = 0
                for alternatives in groups(node):
                    if len(alternatives) > 1:
                        overlays.append(dict(path=path+'.'+alternatives[0].name,
                                             choices=[c.name for c in alternatives],
                                             offset=offset, length=max(c.width*c.occurs for c in alternatives)))
                    for child in alternatives:
                        emit(child, path+'.'+(f'#{child_index+1}.' if child.name == 'FILLER' else ''),
                             offset, restricted or node.occurs > 1 or bool(node.depending) or len(alternatives) > 1)
                        child_index += 1
                    offset += max(c.width*c.occurs for c in alternatives)
            else:
                _, digits, scale, signed = picture(node.picture)
                f = Field(path, offset, node.width, node.picture, node.usage, digits, scale,
                          signed, node.sign, node.separate, node.name == 'FILLER', node.line)
                fields.append(f)
                controllers.setdefault(node.name, []).append((f, restricted or node.occurs > 1 or bool(node.depending)))
                offset += node.width
        return offset-start
    emit(root, '', 0)
    if variables:
        var = variables[0]
        found = controllers.get(var.depending, [])
        if len(found) != 1 or found[0][1] or not found[0][0].digits or found[0][0].scale or found[0][0].filler:
            raise LayoutError('ODO controller must be an unambiguous, unrepeated integer field')
        if found[0][0].line >= var.line:
            raise LayoutError('ODO controller must precede the variable table')
    return Layout(root.name, sha(text.encode()), root.width, tuple(fields), root,
                  root.min_width, bool(variables), tuple(overlays))


def load_copybook(path: Path):
    # utf-8 without newline conversion: the fingerprint is the original bytes.
    raw = path.read_bytes()
    return compile_copybook(raw.decode('utf-8'), str(path))


def _number(raw: bytes, f: Field, codec: str, sign_policy: str, binary_byteorder=None, binary_truncation=None):
    positive, negative = ({12, 15}, {13}) if sign_policy == 'preferred' else ({10, 12, 14, 15}, {11, 13})
    sign_code, is_negative = None, False
    if f.usage in ('BINARY', 'COMP-5'):
        if binary_byteorder not in ('big', 'little'):
            raise DecodeError('binary byte order must be explicitly big or little')
        if f.usage == 'BINARY' and binary_truncation not in ('std', 'bin'):
            raise DecodeError('BINARY requires an explicit std or bin truncation profile')
        value = int.from_bytes(raw, byteorder=binary_byteorder, signed=f.signed)
        if f.usage == 'BINARY' and binary_truncation == 'std' and abs(value) >= 10**f.digits:
            raise DecodeError('binary value exceeds picture under TRUNC(STD)')
        digits = tuple(int(c) for c in str(abs(value)))
        exact = Decimal((int(value < 0), digits, -f.scale))
        return dict(value=format(exact, 'f'), digits=''.join(map(str, digits)), scale=f.scale,
                    sign_code=None, negative_zero=False)
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


def decode_record(layout: Layout, raw: bytes, *, codec='cp037', sign_policy='preferred',
                  binary_byteorder=None, binary_truncation=None, redefines=None):
    if codec not in ('cp037', 'cp500', 'cp1140'):
        raise DecodeError('an explicitly supported single-byte EBCDIC code page is required')
    if sign_policy not in ('preferred', 'ibm-valid'):
        raise DecodeError('unknown sign policy')
    if binary_byteorder not in (None, 'big', 'little') or binary_truncation not in (None, 'std', 'bin'):
        raise DecodeError('unknown binary profile')
    choices = {} if redefines is None else redefines
    if not isinstance(choices, dict): raise DecodeError('REDEFINES choices must be a path-to-name mapping')
    used, decoded, counts = set(), [], {}

    def decode(f):
        data = raw[f.offset:f.offset+f.length]
        if len(data) != f.length: raise DecodeError(f'{f.path}: truncated field')
        entry = dict(path=f.path, offset=f.offset, length=f.length, raw_hex=data.hex(), filler=f.filler)
        try:
            entry.update(_number(data, f, codec, sign_policy, binary_byteorder, binary_truncation)
                         if f.digits else dict(value=data.decode(codec)))
        except DecodeError as exc:
            raise DecodeError(f'{f.path} at byte {f.offset}: {exc}') from exc
        decoded.append(entry)
        if f.digits and not f.scale: counts[f.path.split('.')[-1]] = int(entry['value'])

    def walk(node, prefix, offset):
        count = node.occurs
        if node.depending:
            count = counts.get(node.depending)
            if count is None or not node.occurs_min <= count <= node.occurs:
                raise DecodeError('ODO count missing or outside declared bounds')
        for n in range(count):
            path = prefix+node.name+(f'[{n+1}]' if node.occurs > 1 or node.depending else '')
            if node.picture:
                _, digits, scale, signed = picture(node.picture)
                decode(Field(path, offset, node.width, node.picture, node.usage, digits, scale,
                             signed, node.sign, node.separate, node.name == 'FILLER', node.line))
                offset += node.width
            else:
                j = 0
                while j < len(node.children):
                    first = j
                    alternatives = [node.children[j]]; j += 1
                    while j < len(node.children) and node.children[j].redefines:
                        alternatives.append(node.children[j]); j += 1
                    selected = alternatives[0]
                    if len(alternatives) > 1:
                        key = path+'.'+selected.name
                        if key not in choices or choices[key] not in {c.name for c in alternatives}:
                            raise DecodeError(f'explicit REDEFINES choice required for {key}')
                        used.add(key)
                        selected = next(c for c in alternatives if c.name == choices[key])
                    end = walk(selected, path+'.'+(f'#{first+1}.' if selected.name == 'FILLER' else ''), offset)
                    offset = offset+max(c.width*c.occurs for c in alternatives) if len(alternatives)>1 else end
        return offset
    if layout.variable or layout.overlays:
        end = walk(layout.tree, '', 0)
    else:
        end = layout.record_length
        if len(raw) != end: raise DecodeError(f'record length {len(raw)} != declared {end}')
        for f in layout.fields: decode(f)
    if len(raw) != end: raise DecodeError(f'record length {len(raw)} != active layout {end}')
    if used != set(choices): raise DecodeError('unknown or inactive REDEFINES selection')
    result = dict(copybook_sha256=layout.copybook_sha256, record_sha256=sha(raw), raw_hex=raw.hex(),
                  codec=codec, sign_policy=sign_policy, fields=decoded)
    if any(f.usage in ('BINARY', 'COMP-5') for f in layout.fields):
        result.update(binary_byteorder=binary_byteorder, binary_truncation=binary_truncation)
    if layout.overlays: result['redefines'] = dict(choices)
    if layout.variable: result['active_record_length'] = end
    return result


def decode_rdw(layout: Layout, raw: bytes, **options):
    """Unblocked variable records: IBM four-byte big-endian RDW including itself.

    No BDW, spanning/segment flags, padding or guessed text framing is admitted.
    """
    records, offset = [], 0
    while offset < len(raw):
        header = raw[offset:offset+4]
        if len(header) != 4 or header[2:] != b'\0\0': raise DecodeError('invalid or truncated RDW')
        length = int.from_bytes(header[:2], 'big')
        if length < 4 or length > 32764 or offset+length > len(raw): raise DecodeError('invalid RDW length')
        records.append(decode_record(layout, raw[offset+4:offset+length], **options))
        offset += length
    return records


def decode_fixed(layout: Layout, raw: bytes, **options):
    if layout.variable: raise DecodeError('variable layout requires explicit record or RDW framing')
    if len(raw) % layout.record_length:
        raise DecodeError('truncated or incorrectly framed fixed-block records')
    return [decode_record(layout, raw[i:i+layout.record_length], **options)
            for i in range(0, len(raw), layout.record_length)]


def spool_envelope(raw: bytes, layout: Layout) -> bytes:
    """Synthetic retained HEX export. This is not the z/OSMF binary protocol."""
    if layout.variable: raise DecodeError('variable layout cannot use an FB spool envelope')
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
