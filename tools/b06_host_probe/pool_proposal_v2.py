"""Prospective general overpass comparison; NEVER used for native admission.

Expected methods come from a byte-bound superclass/interface closure. Default
interface methods and conflicting declarations remain unsupported in this first
proposal. The approved single-class production rule is unchanged.
"""
from collections import Counter
import hashlib
from .pool_analysis import original_pool,semantic,encode,check_methods
from tools.ms94_b06_forwarding_stub import pool,text

def expected_methods(source,closure):
    from .generation_replay import class_file
    root=class_file(source);seen=set();requirements={};class_methods={};hashes={}
    if not root['flags']&0x400:raise ValueError('proposal-requires-abstract-class')
    def visit(raw,interface=False,active=()):
        c=class_file(raw);name=c['name']
        if name in active:raise ValueError('class-hierarchy-cycle')
        if name in seen:return
        seen.add(name);hashes[name]=hashlib.sha256(raw).hexdigest()
        for m in c['methods'].values():
            if m['name'].startswith('<') or m['flags']&(8|2):continue
            key=m['name']+m['signature']
            if not interface:class_methods.setdefault(key,m['flags'])
            if m['flags']&0x400:requirements[key]=(m['name'],m['signature'])
            elif interface:raise ValueError('default-interface-method-not-proposed')
        parents=list(c['interfaces'])+([c['parent']] if c['parent'] else [])
        for p in parents:
            name=text(c['pool'],c['pool'][p][1])
            if name not in closure:raise ValueError('missing-bound-hierarchy-class')
            parent=closure[name]
            if class_file(parent)['name']!=name:raise ValueError('hierarchy-class-name')
            visit(parent,p in c['interfaces'],active+(c['name'],))
    visit(source)
    return root['name'],sorted(v for k,v in requirements.items() if k not in class_methods or class_methods[k]&0x400),hashes

def extension_nodes(name,methods):
    def u(s):return [1,s.encode().hex()]
    cls=[7,u('java/lang/AbstractMethodError')];nt=[12,u('<init>'),u('(Ljava/lang/String;)V')]
    nodes=[u('java/lang/AbstractMethodError'),cls,u('<init>'),u('(Ljava/lang/String;)V'),nt,[10,cls,nt]]
    for method,desc in methods:
        msg=u('Method '+name+'.'+method+desc+' is abstract')
        nodes += [msg,[8,msg],u(method),u(desc)]
    return Counter(encode(n) for n in nodes)

def compare(source,closure,runtime_hex,runtime_count,methods):
    name,abstract,hashes=expected_methods(source,closure)
    if not abstract:raise ValueError('no-derived-overpass-methods')
    count,raw=original_pool(source);runtime=bytes.fromhex(runtime_hex)
    if not runtime.startswith(raw):raise ValueError('original-pool-prefix-changed')
    expected=extension_nodes(name,abstract)
    if runtime_count!=count+sum(expected.values()):raise ValueError('derived-extension-count')
    cp=pool(runtime,runtime_count)
    if Counter(encode(semantic(cp,i)) for i in range(count,runtime_count))!=expected:
        raise ValueError('derived-extension-differs')
    check_methods(source,methods)
    return dict(schema='proposed-bound-overpass-pool/2',bound_classes=hashes,derived_methods=abstract,
        original_pool_sha256=hashlib.sha256(raw).hexdigest(),production_admission=False,approval_required=True)
