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


def full_lambda_fixture():
    """A complete authored bootstrap, factory return, host and generated body."""
    import hashlib
    from tools.b06_host_probe.generation_replay import class_file
    owner='org.idempiere.test.LightyearOperationsTest'
    target_desc='()Ljava/lang/Object;';factory_desc='()Ljava/util/function/Supplier;'
    entries,put,utf,cls=pool_builder()
    def nt(n,d):return put(12,u2(utf(n))+u2(utf(d)))
    def ref(o,n,d):return put(10,u2(cls(o))+u2(nt(n,d)))
    this=cls(owner.replace('.','/'));parent=cls('java/lang/Object');code_name=utf('Code')
    target=ref(owner.replace('.','/'),'target',target_desc)
    impl=put(15,bytes([6])+u2(target))
    meta=ref('java/lang/invoke/LambdaMetafactory','metafactory','(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;')
    bootstrap=put(15,bytes([6])+u2(meta));sam=put(16,u2(utf(target_desc)))
    indy=put(18,u2(0)+u2(nt('get',factory_desc)));attribute=utf('BootstrapMethods')
    def method(name,desc,code):
        body=u2(1)+u2(0)+struct.pack('>I',len(code))+code+u2(0)+u2(0)
        return u2(9)+u2(utf(name))+u2(utf(desc))+u2(1)+u2(code_name)+struct.pack('>I',len(body))+body
    methods=method('make',factory_desc,b'\xba'+u2(indy)+b'\x00\x00\xb0')+method('target',target_desc,b'\x01\xb0')
    attr=u2(1)+u2(bootstrap)+u2(3)+u2(sam)+u2(impl)+u2(sam)
    host=b'\xca\xfe\xba\xbe'+u2(0)+u2(52)+u2(len(entries)+1)+b''.join(entries)+u2(0x21)+u2(this)+u2(parent)+u2(0)+u2(0)+u2(2)+methods+u2(1)+u2(attribute)+struct.pack('>I',len(attr))+attr
    c=class_file(host)
    def observed_method(m):
        raw=m['code'];return dict(name=m['name'],signature=m['signature'],modifiers=m['flags'],bytecode_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest())
    h=dict(class_object_id=1,**{'class':owner},loader='77',signature='L'+owner.replace('.','/')+';',constant_pool_hex=c['pool_raw'].hex(),constant_pool_count=c['count'],constant_pool_sha256=hashlib.sha256(c['pool_raw']).hexdigest(),methods=[observed_method(m) for m in c['methods'].values()])
    entries,put,utf,cls=pool_builder()
    method_ref=put(10,u2(cls(owner.replace('.','/')))+u2(nt('target',target_desc)))
    object_init=put(10,u2(cls('java/lang/Object'))+u2(nt('<init>','()V')))
    cp=b''.join(entries);code=b'\xb8'+u2(method_ref)+b'\xb0';ctor=b'\x2a\xb7'+u2(object_init)+b'\xb1'
    generated=dict(class_object_id=2,**{'class':'fixture.Generated/0x1'},loader='77',signature='Lfixture/Generated.0x1;',fields=[],constant_pool_hex=cp.hex(),constant_pool_count=len(entries)+1,constant_pool_sha256=hashlib.sha256(cp).hexdigest(),methods=[dict(name='<init>',signature='()V',modifiers=2,bytecode_hex=ctor.hex(),sha256=hashlib.sha256(ctor).hexdigest()),dict(name='get',signature=target_desc,modifiers=1,bytecode_hex=code.hex(),sha256=hashlib.sha256(code).hexdigest())])
    def mt(ret):return {'class':'java.lang.invoke.MethodType','fields':{'java.lang.invoke.MethodType.ptypes':[],'java.lang.invoke.MethodType.rtype':{'signature':ret}}}
    ident={k:h[k] for k in ('class','loader','class_object_id')}
    f=dict(targetClass=ident,interfaceMethodName='get',factoryType=mt('Ljava/util/function/Supplier;'),interfaceMethodType=mt('Ljava/lang/Object;'),dynamicMethodType=mt('Ljava/lang/Object;'),implMethodDesc=target_desc,implClass={'class':owner},implMethodName='target',implKind='6',isSerializable='false',altInterfaces=[],altMethods=[],useImplMethodHandle='false',argDescs=[],argNames=[],implInfo={'fields':{'java.lang.invoke.InfoFromMemberName.referenceKind':'6','java.lang.invoke.InfoFromMemberName.member':{'fields':{'java.lang.invoke.MemberName.clazz':{'class':owner},'java.lang.invoke.MemberName.name':'target'}}}})
    record=dict(entry_method='java.lang.invoke.InnerClassLambdaMetafactory.spinInnerClass()Ljava/lang/Class;',lambda_factory=f,returned_class={k:generated[k] for k in ('class','loader','class_object_id')},stack=[dict(ident,method='make',signature=factory_desc,code_index=0)])
    raw=dict(definition_id='stub',**{'class':generated['class']},class_signature=generated['signature'],method='get',signature=target_desc,loader='77',class_modifiers=0x1010,method_modifiers=1,native_or_abstract=False,fields=[],constant_pool_count=generated['constant_pool_count'],constant_pool_hex=cp.hex(),constant_pool_sha256=generated['constant_pool_sha256'],bytecode_hex=code.hex(),method_sha256=hashlib.sha256(code).hexdigest(),generation=dict(record=record,definitions={'1':h,'2':generated}))
    frame={k:raw[k] for k in ('definition_id','class','method','signature','loader','constant_pool_sha256','method_sha256')}
    target_frame=dict(definition_id='host',**{'class':owner},method='target',signature=target_desc,loader='77',constant_pool_sha256=h['constant_pool_sha256'],method_sha256=hashlib.sha256(b'\x01\xb0').hexdigest())
    classes={owner:dict(class_bytes_hex=host.hex(),class_sha256=hashlib.sha256(host).hexdigest(),constant_pool_sha256=h['constant_pool_sha256'],methods={m['name']+m['signature']:m['sha256'] for m in h['methods']})}
    return raw,frame,target_frame,classes
