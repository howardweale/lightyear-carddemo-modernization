"""Host diagnostic only. This proposed comparison is NOT native admission policy."""
import hashlib
import json
from collections import Counter
from tools.ms94_b06_classfile import Reader, inspect_class
from tools.ms94_b06_forwarding_stub import pool

ENGINE = 'org/junit/platform/engine/support/hierarchical/HierarchicalTestEngine'
CLASS_SHA = 'b6ebf7618c7572195ec833104be65f54aaa090263dc14297bd471f9c4a1cd056'
ABSTRACT = [('getId','()Ljava/lang/String;'),
            ('discover','(Lorg/junit/platform/engine/EngineDiscoveryRequest;Lorg/junit/platform/engine/UniqueId;)Lorg/junit/platform/engine/TestDescriptor;')]


def encode(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def original_pool(data):
    r=Reader(data)
    if r.u4()!=0xcafebabe:raise ValueError('class-magic')
    r.take(4);count=r.u2();start=r.offset;i=1
    while i<count:
        tag=r.u1()
        if tag==1:r.take(r.u2())
        elif tag in (7,8,16,19,20):r.take(2)
        elif tag==15:r.take(3)
        elif tag in (5,6):r.take(8);i+=1
        elif tag in (3,4,9,10,11,12,17,18):r.take(4)
        else:raise ValueError('unknown-pool-tag')
        i+=1
    return count,data[start:r.offset]


def semantic(cp,index,active=()):
    if index in active or index not in cp:raise ValueError('cyclic-or-missing-pool-reference')
    tag,value=cp[index];more=active+(index,)
    if tag==1:return [1,value.hex()]
    if tag in (7,8):return [tag,semantic(cp,value,more)]
    if tag in (10,12):return [tag,*[semantic(cp,v,more) for v in value]]
    raise ValueError('unapproved-extension-tag')


def expected_extension():
    def u(s):return [1,s.encode().hex()]
    cls=[7,u('java/lang/AbstractMethodError')]
    nt=[12,u('<init>'),u('(Ljava/lang/String;)V')]
    nodes=[u('java/lang/AbstractMethodError'),cls,u('<init>'),u('(Ljava/lang/String;)V'),nt,[10,cls,nt]]
    for method,desc in ABSTRACT:
        msg=u('Method '+ENGINE+'.'+method+desc+' is abstract')
        nodes += [msg,[8,msg],u(method),u(desc)]
    return Counter(encode(n) for n in nodes)


def compare_extension(source, runtime_hex, runtime_count):
    """Evaluate this exact class/pool proposal only; callers gain no run authority."""
    if hashlib.sha256(source).hexdigest()!=CLASS_SHA:raise ValueError('source-class-not-the-reviewed-class')
    count,raw=original_pool(source);runtime=bytes.fromhex(runtime_hex)
    if count!=145 or runtime_count!=159:raise ValueError('pool-count-differs')
    if not runtime.startswith(raw):raise ValueError('original-pool-prefix-changed')
    cp=pool(runtime,runtime_count)
    actual=Counter(encode(semantic(cp,i)) for i in range(count,runtime_count))
    if actual!=expected_extension():raise ValueError('extension-semantic-multiset-differs')
    body={'schema':'proposed-hierarchical-overpass-pool/1','source_class_sha256':CLASS_SHA,
          'original_pool_sha256':hashlib.sha256(raw).hexdigest(),
          'original_count':count,'extension_count':14,
          'extension':sorted(json.loads(n) for n in actual.elements())}
    return {'canonical_sha256':hashlib.sha256(encode(body)).hexdigest(),'canonical':body,
            'raw_sha256':hashlib.sha256(runtime).hexdigest(),'production_admission':False}


def check_methods(source, observed):
    expected=inspect_class(source)['methods']
    actual={m['name']+m['signature']:m.get('sha256','unavailable') for m in observed}
    if actual!=expected or len(actual)!=len(observed):raise ValueError('declared-methods-changed')
    flags=method_flags(source)
    if {m['name']+m['signature']:m.get('modifiers') for m in observed}!=flags:
        raise ValueError('declared-method-flags-changed')
    return len(actual)


def method_flags(source):
    """Read class-file access flags independently of JDI's reported metadata."""
    count, raw=original_pool(source)
    cp=pool(raw,count)
    r=Reader(source);r.take(10+len(raw));r.take(6)
    r.take(2*r.u2())
    def attrs():
        for _ in range(r.u2()):r.take(2);r.take(r.u4())
    for _ in range(r.u2()):r.take(6);attrs()
    result={}
    for _ in range(r.u2()):
        flags,name,descriptor=r.u2(),r.u2(),r.u2()
        if cp[name][0]!=1 or cp[descriptor][0]!=1:raise ValueError('invalid-method-text')
        key=cp[name][1].decode('ascii')+cp[descriptor][1].decode('ascii')
        if key in result:raise ValueError('duplicate-method')
        result[key]=flags;attrs()
    attrs()
    if r.offset!=len(source):raise ValueError('trailing-class-data')
    return result
