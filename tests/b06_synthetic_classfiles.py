"""Tiny authored class files for offline CI only, not captured JVM evidence."""
import struct
from tools.b06_host_probe.pool_analysis import original_pool

def u2(v):return struct.pack('>H',v)
def pool_builder():
    entries=[]
    def put(tag,payload):entries.append(bytes([tag])+payload);return len(entries)
    def utf(s):b=s.encode();return put(1,u2(len(b))+b)
    def cls(s):return put(7,u2(utf(s)))
    return entries,put,utf,cls

def abstract_class(name='fixture/Subject',interface=False):
    entries,put,utf,cls=pool_builder()
    this=cls(name);parent=cls('java/lang/Object') if name!='java/lang/Object' else 0
    interface_index=cls('fixture/Contract') if name=='fixture/Subject' else None
    methods=b'';count=0
    if interface:
        methods=u2(0x401)+u2(utf('run'))+u2(utf('()V'))+u2(0);count=1
    return (b'\xca\xfe\xba\xbe'+u2(0)+u2(52)+u2(len(entries)+1)+b''.join(entries)+
        u2(0x601 if interface else 0x421)+u2(this)+u2(parent)+u2(bool(interface_index))+
        (u2(interface_index) if interface_index else b'')+u2(0)+u2(count)+methods+u2(0))

def extended(source,name='fixture/Subject'):
    count,raw=original_pool(source);entries=[]
    def put(tag,payload):entries.append(bytes([tag])+payload);return count+len(entries)-1
    def utf(s):b=s.encode();return put(1,u2(len(b))+b)
    error=utf('java/lang/AbstractMethodError');cls=put(7,u2(error))
    init=utf('<init>');desc=utf('(Ljava/lang/String;)V');nt=put(12,u2(init)+u2(desc));put(10,u2(cls)+u2(nt))
    msg=utf('Method '+name+'.run()V is abstract');put(8,u2(msg));utf('run');utf('()V')
    return (raw+b''.join(entries)).hex(),count+len(entries)

def reviewed_shape_pool():
    """Authored 145+14 shape; never the reviewed class's production identity."""
    source=abstract_class();count,raw=original_pool(source)
    padding=b''.join(b'\x01'+u2(len(s))+s for s in
                     (('unused'+str(i)).encode() for i in range(145-count)))
    source=source[:8]+u2(145)+raw+padding+source[10+len(raw):]
    _,raw=original_pool(source);entries=[]
    def put(tag,payload):entries.append(bytes([tag])+payload);return 145+len(entries)-1
    def utf(s):b=s.encode();return put(1,u2(len(b))+b)
    cls=put(7,u2(utf('java/lang/AbstractMethodError')))
    init=utf('<init>');desc=utf('(Ljava/lang/String;)V')
    nt=put(12,u2(init)+u2(desc));put(10,u2(cls)+u2(nt))
    owner='org/junit/platform/engine/support/hierarchical/HierarchicalTestEngine'
    methods=[('getId','()Ljava/lang/String;'),('discover','(Lorg/junit/platform/engine/EngineDiscoveryRequest;Lorg/junit/platform/engine/UniqueId;)Lorg/junit/platform/engine/TestDescriptor;')]
    for name,sig in methods:
        msg=utf('Method '+owner+'.'+name+sig+' is abstract');put(8,u2(msg));utf(name);utf(sig)
    return source,(raw+b''.join(entries)).hex()

def identity_class():
    entries,put,utf,cls=pool_builder()
    this=cls('java/lang/invoke/LambdaForm$Fixture');parent=cls('java/lang/Object')
    name=utf('identity');desc=utf('(Ljava/lang/Object;)Ljava/lang/Object;');code_name=utf('Code')
    body=u2(1)+u2(1)+struct.pack('>I',2)+b'\x2a\xb0'+u2(0)+u2(0)
    method=u2(8)+u2(name)+u2(desc)+u2(1)+u2(code_name)+struct.pack('>I',len(body))+body
    return (b'\xca\xfe\xba\xbe'+u2(0)+u2(52)+u2(len(entries)+1)+b''.join(entries)+
        u2(0x20)+u2(this)+u2(parent)+u2(0)+u2(0)+u2(1)+method+u2(0))

def lambda_form_fixture():
    import hashlib
    from tools.b06_host_probe.generation_replay import class_file
    raw=identity_class();c=class_file(raw);cpraw=c['pool_raw'];count=c['count']
    # Reconstitute the exact self class reference as HotSpot does for hidden definitions.
    entries,put,utf,cls=pool_builder()
    from tools.ms94_b06_classfile import Reader
    r=Reader(cpraw);parts=[];index=1
    while index<count:
        start=r.offset;tag=r.u1()
        if tag==1:r.take(r.u2())
        else:r.take(2)
        parts.append(bytes([7])+u2(count) if index==c['this_index'] else cpraw[start:r.offset]);index+=1
    hidden=c['name']+'+0x1';b=hidden.encode();runtime_pool=b''.join(parts)+b'\x01'+u2(len(b))+b
    runtime=dict(class_object_id=2,**{'class':c['name'].replace('/','.')+'/0x1'},loader='bootstrap',module='java.base',
        signature='L'+c['name']+'.0x1;',constant_pool_count=count+1,constant_pool_hex=runtime_pool.hex(),
        constant_pool_sha256=hashlib.sha256(runtime_pool).hexdigest(),methods=[dict(name='identity',signature='(Ljava/lang/Object;)Ljava/lang/Object;',
        modifiers=8,bytecode_hex='2ab0',sha256=hashlib.sha256(b'\x2a\xb0').hexdigest())])
    form='java.lang.invoke.LambdaForm';name='java.lang.invoke.LambdaForm$Name'
    graph=dict(root='f',nodes={'f':{'class':form,'fields':{form+'.customized':None,form+'.names':{'ref':'a'},form+'.arity':'1',form+'.result':'0'}},
        'a':{'class':name+'[]','fields':{'0':{'ref':'n'}}},'n':{'class':name,'fields':{name+'.index':'0',name+'.function':None,name+'.arguments':None}}})
    h=hashlib.sha256(raw).hexdigest()
    emission=dict(entry_method='java.lang.invoke.InvokerBytecodeGenerator.generateCustomizedCodeBytes()[B',thread_id=1,
        returned_bytes_object_id=3,returned_bytes_hex=raw.hex(),returned_bytes_sha256=h,lambda_form_graph=graph)
    definition=dict(entry_method='java.lang.invoke.MethodHandles$Lookup$ClassDefiner.defineClass(ZLjava/lang/Object;)Ljava/lang/Class;',
        thread_id=1,definition_input_object_id=3,definition_input_hex=raw.hex(),definition_input_sha256=h,lambda_form_graph=graph,
        returned_class={k:runtime[k] for k in ('class','loader','class_object_id')},
        definer={'lookup':{'fields':{'java.lang.invoke.MethodHandles$Lookup.lookupClass':{'class':form,'loader':'bootstrap'}}}})
    return emission,definition,runtime,graph
