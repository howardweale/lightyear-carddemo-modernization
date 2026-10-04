"""Read JVM identities offline from compiled class bytes, never candidate claims."""
import hashlib
import struct
from tools.ms94_b06_admission import check


class Reader:
    def __init__(self, data): self.data, self.offset = data, 0
    def take(self, count):
        check(0 <= count <= len(self.data) - self.offset, 'truncated-class-file')
        value = self.data[self.offset:self.offset + count]; self.offset += count
        return value
    def u1(self): return self.take(1)[0]
    def u2(self): return struct.unpack('>H', self.take(2))[0]
    def u4(self): return struct.unpack('>I', self.take(4))[0]


def inspect_class(data):
    reader = Reader(data)
    check(reader.u4() == 0xCAFEBABE, 'invalid-class-magic')
    minor, major = reader.u2(), reader.u2()
    count = reader.u2(); start = reader.offset; pool = {}; index = 1
    while index < count:
        tag = reader.u1()
        if tag == 1:
            raw = reader.take(reader.u2())
            # Names and descriptors used here are ASCII. Other modified UTF-8
            # constants remain opaque bytes; no replacement decoding is trusted.
            pool[index] = ('utf8', raw)
        elif tag in (7, 8, 16, 19, 20): pool[index] = ('index', reader.u2())
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18): reader.take(4)
        elif tag in (5, 6): reader.take(8); index += 1
        elif tag == 15: reader.take(3)
        else: check(False, 'unsupported-class-pool-tag')
        index += 1
    cp_hash = hashlib.sha256(data[start:reader.offset]).hexdigest()
    def text(i):
        check(i in pool and pool[i][0] == 'utf8', 'invalid-class-name-reference')
        return pool[i][1].decode('ascii')
    reader.u2(); this = reader.u2(); reader.u2()
    check(this in pool and pool[this][0] == 'index', 'invalid-class-identity')
    name = text(pool[this][1]).replace('/', '.')
    reader.take(2 * reader.u2())
    def attributes():
        return [(text(reader.u2()), reader.take(reader.u4())) for _ in range(reader.u2())]
    for _ in range(reader.u2()):
        reader.take(6); attributes()
    methods = {}
    for _ in range(reader.u2()):
        access, method, signature = reader.u2(), text(reader.u2()), text(reader.u2())
        attrs = attributes(); codes = [value for key, value in attrs if key == 'Code']
        check(len(codes) <= 1 and (bool(codes) != bool(access & (0x0100 | 0x0400))), 'invalid-method-code')
        code_hash = 'unavailable'
        if codes:
            code = Reader(codes[0]); code.take(4)
            code_hash = hashlib.sha256(code.take(code.u4())).hexdigest()
            code.take(8 * code.u2())  # exception table
            for _ in range(code.u2()):
                text(code.u2()); code.take(code.u4())
            check(code.offset == len(code.data), 'trailing-method-code-bytes')
        identity = method + signature
        check(identity not in methods, 'duplicate-class-method')
        methods[identity] = code_hash
    attributes(); check(reader.offset == len(data), 'trailing-class-bytes')
    return {'class': name, 'class_sha256': hashlib.sha256(data).hexdigest(),
            'major': major, 'minor': minor, 'constant_pool_sha256': cp_hash, 'methods': methods,
            'utf8_constants_hex': {str(i): value[1].hex() for i, value in pool.items() if value[0] == 'utf8'}}
