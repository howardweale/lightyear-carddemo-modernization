"""Typed projection and reconstruction. Business bytes are regenerated, not copied.

Only filler/uninterpreted storage and representation metadata survive separately.
Original records are kept by the proof caller, never used as the encoder's answer.
"""
from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
import re

from lightyear_mainframe.records import decode_record, DecodeError


def encode_field(f, value, meta, codec='cp037'):
    if not f['digits']:
        raw = str(value).encode(codec)
        if len(raw) != f['length']: raise ValueError('character width changed: '+f['path'])
        return raw
    number = Decimal(str(value))
    if not number.is_finite(): raise ValueError('non-finite numeric')
    with localcontext() as ctx:
        ctx.prec = max(50, f['digits'] + f['scale'] + 5)
        scaled = abs(number) * (Decimal(10) ** f['scale'])
        if scaled != scaled.to_integral_value(): raise ValueError('numeric precision loss')
        integer = int(scaled)
    if f['usage'] != 'COMP-5' and integer >= 10 ** f['digits']: raise ValueError('numeric overflow')
    negative = number < 0 or (number == 0 and meta.get('negative_zero', False))
    if negative and not f['signed']: raise ValueError('negative unsigned field')
    if f['usage'] in ('BINARY', 'COMP-5'):
        return (-integer if negative else integer).to_bytes(f['length'], 'big', signed=f['signed'])
    digits = str(integer).zfill(f['digits'])
    old = meta.get('sign_code')
    sign = 13 if negative else old if old in (12, 15) else 12 if f['signed'] else 15
    if f['usage'] == 'COMP-3':
        packed = digits + format(sign, 'x')
        return bytes.fromhex(packed.zfill(f['length'] * 2))
    raw = bytearray(0xf0 + int(c) for c in digits)
    if f['separate']:
        symbol = ('-' if negative else '+').encode(codec)
        return symbol + raw if f['sign'] == 'LEADING' else raw + symbol
    if f['signed']:
        index = 0 if f['sign'] == 'LEADING' else len(raw)-1
        raw[index] = (sign << 4) | (raw[index] & 15)
    return bytes(raw)


def project(layout, mapping, raw, *, codec='cp037'):
    decoded = decode_record(layout, raw, codec=codec, binary_byteorder='big', binary_truncation='std')
    specs = {f['path']: f for f in mapping['fields']}
    values = {}; representations = {}; filler = []; active = []
    for entry in decoded['fields']:
        f = specs[entry['path']]
        active.append({'path': f['path'], 'offset': entry['offset'], 'length': entry['length']})
        if f['filler']:
            filler.append({'offset':entry['offset'], 'hex':entry['raw_hex']}); continue
        value = Decimal(entry['value']) if f['digits'] else entry['value']
        if not f['digits'] and f.get('text_policy') == 'printable' and any(not c.isprintable() for c in value):
            raise DecodeError('unprintable character: '+f['path'])
        if f['date']:
            # A date interpretation is explicit and traced in the mapping.
            # Preserve original text too. Invalid dates quarantine the whole record.
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): raise DecodeError('invalid ISO date: '+f['path'])
            try: date.fromisoformat(value)
            except ValueError as exc: raise DecodeError('invalid ISO date: '+f['path']) from exc
        values[f['path']] = value
        representations[f['path']] = {k:entry[k] for k in ('sign_code','negative_zero') if k in entry}
    return dict(values=values, metadata=dict(length=len(raw), active=active, filler=filler,
                representations=representations, codec=codec), source_sha256=sha256(raw).hexdigest())


def reconstruct(mapping, values, metadata):
    specs = {f['path']: f for f in mapping['fields']}
    output = bytearray(metadata['length']); coverage = bytearray(metadata['length'])
    if not mapping['minimum_length'] <= len(output) <= mapping['record_length']: raise ValueError('invalid active length')
    def put(offset, raw):
        end = offset + len(raw)
        if offset < 0 or end > len(output) or any(coverage[offset:end]): raise ValueError('overlapping/outside encoding')
        output[offset:end] = raw; coverage[offset:end] = b'\x01' * len(raw)
    for f in metadata['filler']: put(f['offset'], bytes.fromhex(f['hex']))
    seen = set()
    for active in metadata['active']:
        f = specs[active['path']]
        if f['path'] in seen or f['length'] != active['length']: raise ValueError('invalid encoding field inventory')
        seen.add(f['path'])
        if not f['filler']: put(active['offset'], encode_field(f, values[f['path']], metadata['representations'][f['path']], metadata['codec']))
    if not all(coverage): raise ValueError('unaccounted storage')
    return bytes(output)


def split_fixed(data, length):
    # An incomplete trailing record is returned and quarantined, never truncated.
    return [data[i:i+length] for i in range(0, len(data), length)]
