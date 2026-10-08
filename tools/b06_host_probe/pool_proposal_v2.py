"""Prospective general overpass comparison; NEVER used for native admission.

Expected methods come from a byte-bound superclass/interface closure. Default methods are allowed but only inherited abstract interface requirements
absent from the class hierarchy are proposed as overpasses. The approved single-class production rule is unchanged.
"""
from collections import Counter
import hashlib
from .pool_analysis import original_pool,semantic,encode,check_methods
from tools.ms94_b06_forwarding_stub import pool,text

def expected_methods(source,closure):
    from .generation_replay import class_file
    root=class_file(source);seen=set();requirements={};class_methods={};hashes={};interfaces={}
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
            if interface:requirements.setdefault(key,[]).append((name,m['name'],m['signature'],m['flags']))
        if interface:interfaces[name]={text(c['pool'],c['pool'][i][1]) for i in c['interfaces']}
        parents=list(c['interfaces'])+([c['parent']] if c['parent'] else [])
        for p in parents:
            name=text(c['pool'],c['pool'][p][1])
            if name not in closure:raise ValueError('missing-bound-hierarchy-class')
            parent=closure[name]
            if class_file(parent)['name']!=name:raise ValueError('hierarchy-class-name')
            visit(parent,p in c['interfaces'],active+(c['name'],))
    visit(source)
    def extends(child,parent):
        return parent in interfaces.get(child,set()) or any(extends(p,parent) for p in interfaces.get(child,set()))
    # HotSpot creates overpasses only when this hierarchy has a default method.
    if not any(not flags&0x400 for declarations in requirements.values() for _,_,_,flags in declarations):
        return root['name'],[],hashes
    abstract=[]
    for key,declarations in requirements.items():
        if key in class_methods:continue
        maximal=[d for d in declarations if not any(other[0]!=d[0] and extends(other[0],d[0]) for other in declarations)]
        defaults=[d for d in maximal if not d[3]&0x400]
        if len(defaults)>1:raise ValueError('ambiguous-interface-defaults')
        if not defaults:abstract.append((maximal[0][1],maximal[0][2]))
    return root['name'],sorted(abstract),hashes

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


def reviewed_host_modifiers(source,observed):
    """Diagnostic proposal ONLY: no production imports or admission change.

    Preserve exact low class-file flags. Use the general JDWP synthetic
    high-word marker, including signed 32-bit wire representation. This is
    the same rule used in production replay; no class-name exception.
    """
    import copy
    from .pool_analysis import method_flags
    flags=method_flags(source);out=copy.deepcopy(observed);changes=[]
    for method in out:
        key=method['name']+method['signature'];actual=method.get('modifiers');expected=flags.get(key)
        if expected is None:raise ValueError('unbound-host-method')
        wire=expected | (0xf0000000 if expected & 0x1000 else 0)
        if wire>=0x80000000:wire-=0x100000000
        if actual!=wire:raise ValueError('method-wire-flags-differ')
        if actual!=expected:changes.append(dict(method=key,class_file_flags=expected,jdi_modifiers=actual))
        method['modifiers']=expected
    return out,changes
