"""Prospective, fail-closed verifier for raw JVM forwarding stubs.

No class-name pattern grants trust. Collector records are VM observations, never
candidate traces. The caller must supply the adjacent target frame and a class
catalogue verified against the frozen plan.
"""
import hashlib
import re
from tools.ms94_b06_admission import check
from tools.ms94_b06_classfile import Reader

POLICY = 'exact-forwarding-stub-v1'


def validate_spec(spec, classes):
    """Prospective opt-in only; bind every permitted framework host to an entry."""
    check(spec['forwarding_stub'] == {'policy': POLICY, 'adjacent_target': 'younger'}, 'observer-stub-policy')
    check(re.fullmatch('[a-f0-9]{64}', spec.get('forwarding_amendment_sha256', '')) is not None,
          'observer-stub-amendment')
    entries = spec.get('host_jar_entries')
    check(isinstance(entries, dict) and entries, 'observer-host-jar-empty')
    for name, item in entries.items():
        check(name in classes and set(item) == {'jar', 'member', 'entry_sha256'}, 'observer-host-jar-spec')
        check(item['entry_sha256'] == classes[name]['class_sha256'] and
              item['member'] == name.replace('.', '/') + '.class', 'observer-host-jar-catalog')
        jar = item['jar']
        check(isinstance(jar, str) and jar.startswith(('/application/', '/root/.m2/')) and
              jar.endswith('.jar') and '..' not in jar.split('/'), 'observer-host-jar-path')


def pool(raw, count):
    r, entries, index = Reader(raw), {}, 1
    check(type(count) is int and 1 < count <= 65535, 'stub-pool-count')
    while index < count:
        tag = r.u1()
        if tag == 1: value = r.take(r.u2())
        elif tag in (7, 8, 16, 19, 20): value = r.u2()
        elif tag in (9, 10, 11, 12, 17, 18): value = (r.u2(), r.u2())
        elif tag == 15: value = (r.u1(), r.u2())
        elif tag in (3, 4): value = r.take(4)
        elif tag in (5, 6):
            value = r.take(8); entries[index] = (tag, value); index += 2; continue
        else: check(False, 'stub-pool-tag')
        entries[index] = (tag, value); index += 1
    check(index == count and r.offset == len(raw), 'stub-pool-length')
    return entries


def text(cp, index):
    check(index in cp and cp[index][0] == 1, 'stub-pool-utf8')
    try: return cp[index][1].decode('ascii')
    except UnicodeDecodeError: check(False, 'stub-nonascii-identity')


def member(cp, index, allowed):
    check(index in cp and cp[index][0] in allowed, 'stub-member-kind')
    owner, nt = cp[index][1]
    check(owner in cp and cp[owner][0] == 7 and nt in cp and cp[nt][0] == 12, 'stub-member-reference')
    name, desc = cp[nt][1]
    return text(cp, cp[owner][1]).replace('/', '.'), text(cp, name), text(cp, desc)


def descriptor(value):
    check(isinstance(value, str) and value.startswith('('), 'stub-descriptor')
    def one(i):
        start = i
        while i < len(value) and value[i] == '[': i += 1
        check(i < len(value), 'stub-descriptor')
        if value[i] == 'L':
            end = value.find(';', i)
            check(end > i + 1, 'stub-descriptor')
            return value[start:end + 1], end + 1
        check(value[i] in 'BCDFIJSZV' and not (i > start and value[i] == 'V'), 'stub-descriptor')
        return value[start:i + 1], i + 1
    args, i = [], 1
    while i < len(value) and value[i] != ')':
        t, i = one(i); check(t != 'V', 'stub-void-argument'); args.append(t)
    check(i < len(value) and value[i] == ')', 'stub-descriptor')
    result, i = one(i + 1)
    check(i == len(value), 'stub-descriptor')
    return args, result


def width(t): return 2 if t in ('J', 'D') else 1


def load_family(t):
    return 'A' if t.startswith(('L', '[')) else ('I' if t in 'BCISZ' else t)


def definition(raw):
    """Check raw material, including non-forwarding definitions retained as census."""
    check(isinstance(raw, dict), 'stub-definition')
    try:
        cp = bytes.fromhex(raw['constant_pool_hex'])
        code = bytes.fromhex(raw['bytecode_hex'])
    except (KeyError, ValueError, TypeError):
        check(False, 'stub-raw-bytes')
    check(hashlib.sha256(cp).hexdigest() == raw['constant_pool_sha256'], 'stub-pool-hash')
    expected = 'unavailable' if raw['native_or_abstract'] else hashlib.sha256(code).hexdigest()
    check(raw['method_sha256'] == expected and (not raw['native_or_abstract'] or code == b''), 'stub-method-hash')
    return pool(cp, raw['constant_pool_count']), code


def validate_stub(raw, frame, target_frame, classes, host_entries):
    """Only loads/captured getfield, exactly one invoke, and a typed return.

    No casts, boxing, allocation, arithmetic, branches, stores, field writes,
    second invoke, or other adaptation. Unsupported ordinary lambda shapes fail.
    """
    cp, code = definition(raw)
    for name in ('class', 'method', 'signature', 'loader', 'constant_pool_sha256', 'method_sha256'):
        check(raw[name] == frame[name], 'stub-definition-frame-binding')
    check(not raw['native_or_abstract'] and raw['method_modifiers'] & (8 | 0x20) == 0, 'stub-instance-method')
    # VM metadata identifies a synthetic runtime definition; spelling never binds its host.
    check(raw['class_modifiers'] & 0x1000 and '/' in raw['class'], 'stub-not-vm-hidden-synthetic')
    check(isinstance(target_frame, dict), 'stub-missing-adjacent-target')
    args, result = descriptor(raw['signature'])
    local_types, slot = {}, 1
    for t in args: local_types[slot] = t; slot += width(t)
    values, fields_seen, locals_seen = [], [], []
    fields = {f['name']: f for f in raw['fields']}
    check(len(fields) == len(raw['fields']), 'stub-duplicate-field')
    i, invoke = 0, None
    returned = False
    return_ops = {'I':0xac,'J':0xad,'F':0xae,'D':0xaf,'A':0xb0,'V':0xb1}
    compact = ((0x1a, 'I'), (0x1e, 'J'), (0x22, 'F'), (0x26, 'D'), (0x2a, 'A'))
    while i < len(code):
        op = code[i]; i += 1
        loaded = next(((kind, op - start) for start, kind in compact if start <= op < start + 4), None)
        if op in (0x15, 0x16, 0x17, 0x18, 0x19):
            check(i < len(code), 'stub-truncated-load')
            loaded = ('IJFDA'[op - 0x15], code[i]); i += 1
        if loaded is not None:
            check(invoke is None, 'stub-load-after-invoke')
            kind, local = loaded
            if local == 0:
                check(kind == 'A', 'stub-invalid-this-load')
                values.append(('THIS', None))
            else:
                check(local in local_types and load_family(local_types[local]) == kind, 'stub-local-type')
                check(local not in locals_seen, 'stub-repeated-local')
                locals_seen.append(local); values.append((local_types[local], None))
            continue
        if op == 0xb4:  # own captured instance field, after aload_0
            check(invoke is None and i + 2 <= len(code) and values and values.pop()[0] == 'THIS', 'stub-field-load')
            owner, name, desc = member(cp, int.from_bytes(code[i:i+2], 'big'), {9}); i += 2
            f = fields.get(name)
            declared = raw['class_signature'][1:-1].replace('/', '.')
            check(owner == declared and f is not None and f['signature'] == desc and
                  f['modifiers'] & 0x10 and not f['modifiers'] & 8, 'stub-captured-field')
            check(name not in fields_seen, 'stub-repeated-field')
            fields_seen.append(name); values.append((desc, None)); continue
        if op in (0xb6, 0xb7, 0xb8, 0xb9):
            check(invoke is None and i + 2 <= len(code), 'stub-invoke-count')
            owner, method, sig = member(cp, int.from_bytes(code[i:i+2], 'big'), {11} if op == 0xb9 else {10,11})
            i += 2
            params, returns = descriptor(sig)
            expected = ([] if op == 0xb8 else ['L' + owner.replace('.', '/') + ';']) + params
            check([v[0] for v in values] == expected, 'stub-invoke-arguments')
            check(locals_seen == list(local_types), 'stub-argument-order-or-closure')
            captured = [n for n,f in fields.items() if not f['modifiers'] & 8]
            check(fields_seen == captured, 'stub-capture-order-or-closure')
            check(returns == result, 'stub-return-adaptation')
            if op == 0xb9:
                check(i+2 <= len(code) and code[i] == sum(width(t) for t in expected) and code[i+1] == 0, 'stub-interface-operands')
                i += 2
            check(method not in ('<init>','<clinit>'), 'stub-constructor')
            invoke = (owner, method, sig); values = []; continue
        check(invoke is not None and op == return_ops[load_family(result)] and i == len(code), 'stub-extra-logic-or-return')
        returned = True
        break
    check(invoke is not None and returned, 'stub-missing-return')
    owner, method, sig = invoke
    check(owner in classes, 'stub-host-unbound')
    host = classes[owner]
    check((target_frame['class'],target_frame['method'],target_frame['signature']) == invoke, 'stub-wrong-adjacent-target')
    check(target_frame['loader'] == frame['loader'], 'stub-wrong-loader')
    check(target_frame['constant_pool_sha256'] == host['constant_pool_sha256'] and
          target_frame['method_sha256'] == host['methods'].get(method+sig), 'stub-host-bytecode')
    public_hosts = ('org.idempiere.test.LightyearOperationsTest', 'org.idempiere.test.JourneySupport')
    if not (any(owner == n or owner.startswith(n + '$') for n in public_hosts)
            or owner.startswith(('org.compiere.', 'org.adempiere.'))):
        entry = host_entries.get(owner)
        check(entry is not None and entry['entry_sha256'] == host['class_sha256'], 'stub-framework-jar-entry')
    return {'stub_method_sha256': raw['method_sha256'], 'stub_constant_pool_sha256': raw['constant_pool_sha256'],
            'host_class': owner, 'host_class_sha256': host['class_sha256'], 'host_method': method,
            'host_signature': sig, 'loader': frame['loader'], 'definition_id': raw['definition_id']}


def receipt_records(events):
    """Lossless receipt commitments, without evaluating/approving the stubs."""
    records, adjacencies = {}, {}
    for item in events:
        event = item['event']
        if event['kind'] == 'frame-definition':
            raw = event['definition']; definition(raw)
            key = raw['definition_id']
            check(key not in records, 'stub-duplicate-definition')
            records[key] = {'class':raw['class'], 'method':raw['method'], 'signature':raw['signature'],
                            'loader':raw['loader'], 'method_sha256':raw['method_sha256'],
                            'constant_pool_sha256':raw['constant_pool_sha256'],
                            'event_sha256':item['content_sha256']}
        frames = event.get('frames', [])
        for index, frame in enumerate(frames):
            # Keep both neighbours verbatim. The explicit plan chooses direction.
            # Recording a relation is not verification or acceptance of its host.
            if '/' not in frame['class']:
                continue
            neighbours = {name: frames[j] if 0 <= j < len(frames) else None
                          for name,j in (('younger',index-1),('older',index+1))}
            key = frame['definition_id'] + ':' + ':'.join(
                n['definition_id'] if n else 'absent' for n in neighbours.values())
            adjacencies.setdefault(key, {'stub_definition_id':frame['definition_id'],
                'stub_method_sha256':frame['method_sha256'], 'observed_neighbours':neighbours,
                'first_event_sha256':item['content_sha256'], 'host_verified':False})
    return {'definitions':records, 'generated_adjacencies':adjacencies}
