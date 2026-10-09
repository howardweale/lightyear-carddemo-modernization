"""Experimental LambdaForm expression replay; never native admission authority."""
import hashlib
from tools.b06_host_probe.generation_replay import need, class_file
from tools.b06_host_probe.pool_analysis import check_methods
from tools.ms94_b06_forwarding_stub import pool, text, member, descriptor, width


class Graph:
    def __init__(self, value):
        need(isinstance(value, dict) and set(value)=={'root','nodes'}, 'form-graph-missing')
        self.nodes=value['nodes'];self.root=value['root']
    def node(self, ref):
        if isinstance(ref, dict):
            need(set(ref)=={'ref'}, 'form-reference-shape');ref=ref['ref']
        need(ref in self.nodes,'form-reference-missing')
        return self.nodes[ref]
    def field(self, ref, cls, name):
        n=self.node(ref);need(n['class']==cls,'form-object-class')
        return n['fields'][cls+'.'+name]
    def value(self, ref):
        n=self.node(ref)
        need('value' in n,'form-value-missing');return n['value']
    def array(self, ref):
        n=self.node(ref);need(n['class'].endswith('[]'),'form-array-class')
        f=n['fields'];need(set(f)=={str(i) for i in range(len(f))},'form-array-index')
        return [f[str(i)] for i in range(len(f))]
    def method_type(self, ref):
        n=self.node(ref)
        if n['class']=='java.lang.String':return n['value']
        need(n['class']=='java.lang.invoke.MethodType','form-method-type')
        return '('+''.join(self.value(v)['signature'] for v in self.array(self.field(ref,n['class'],'ptypes')))+')'+self.value(self.field(ref,n['class'],'rtype'))['signature']
    def member(self, ref):
        cls='java.lang.invoke.MemberName'
        f=self.node(ref)['fields'];need(self.node(ref)['class']==cls,'form-member-name')
        owner=self.value(f[cls+'.clazz'])['class'];name=self.value(f[cls+'.name'])
        kind=(int(f[cls+'.flags'])>>24)&15
        typ=f[cls+'.type']
        desc=self.value(typ)['signature'] if kind in (1,2,3,4) else self.method_type(typ)
        return kind,owner,name,desc


def emission_definition_binding(emission, definition, runtime):
    """Exact external-JDI emission -> byte array -> returned Class binding.

    The caller must separately admit the generator's pinned bytes and origins;
    matching these records alone never supplies that trust.
    """
    need(emission.get('entry_method')=='java.lang.invoke.InvokerBytecodeGenerator.generateCustomizedCodeBytes()[B', 'unapproved-form-generator')
    need(definition.get('entry_method')=='java.lang.invoke.MethodHandles$Lookup$ClassDefiner.defineClass(ZLjava/lang/Object;)Ljava/lang/Class;', 'unapproved-form-definer')
    need(emission['thread_id']==definition['thread_id'] and emission['returned_bytes_object_id']==definition['definition_input_object_id'], 'form-emission-object-binding')
    raw=bytes.fromhex(emission['returned_bytes_hex'])
    need(raw==bytes.fromhex(definition['definition_input_hex']) and hashlib.sha256(raw).hexdigest()==emission['returned_bytes_sha256']==definition['definition_input_sha256'], 'form-emitted-bytes-changed')
    need(expression_recipe(emission['lambda_form_graph'])==expression_recipe(definition['lambda_form_graph']), 'form-generator-graph-changed')
    returned=definition['returned_class']
    need(returned['class_object_id']==runtime['class_object_id'] and returned['class']==runtime['class'] and returned['loader']==runtime['loader']=='bootstrap' and runtime['module']=='java.base', 'form-runtime-return-binding')
    lookup=definition['definer']['lookup']['fields']['java.lang.invoke.MethodHandles$Lookup.lookupClass']
    need(lookup['class']=='java.lang.invoke.LambdaForm' and lookup['loader']=='bootstrap', 'form-defining-host-differs')
    cls=class_file(raw);observed=pool(bytes.fromhex(runtime['constant_pool_hex']),runtime['constant_pool_count'])
    need(hashlib.sha256(bytes.fromhex(runtime['constant_pool_hex'])).hexdigest()==runtime['constant_pool_sha256'], 'form-runtime-pool-hash')
    prefix,sep,suffix=runtime['class'].rpartition('/')
    need(sep and prefix.replace('.','/')==cls['name'] and runtime['signature']=='L'+cls['name']+'.'+suffix+';', 'form-hidden-identity')
    need(runtime['constant_pool_count']==cls['count']+1, 'form-hidden-pool-count')
    expected=dict(cls['pool']);expected[cls['this_index']]=(7,cls['count'])
    expected[cls['count']]=(1,(cls['name']+'+'+suffix).encode('ascii'))
    need(observed==expected, 'form-hidden-pool-reconstitution-differs')
    check_methods(raw,runtime['methods'])
    for m in runtime['methods']:
        need(hashlib.sha256(bytes.fromhex(m['bytecode_hex'])).hexdigest()==m['sha256'],'form-method-material-differs')
    return {'emission_definition_bound':True,'emitted_class_sha256':hashlib.sha256(raw).hexdigest(),
            'runtime_pool_sha256':runtime['constant_pool_sha256'],'native_admission':False}


def observed_dynamic_target(handle_graph, frames, definitions, ordinary_bindings, jdk_class_ids, *,
                            generated_dispatch_ids=(), captured_fields=()):
    """Conservative actual-use check, never infer a target from a generated name.

    Only one non-JDK member may occur in the reachable handle graph. Multiple
    targets are unresolved, not an invitation to select the one matching a
    deeper candidate frame. The caller supplies independently admitted JDK IDs
    and byte-bound ordinary definitions; package spelling is not authority.
    Optional generated dispatch IDs require separate emission/body proof.
    Captured-field tuples permit only independently verified read-only data
    access, never an invocation or frame admission for that holder.
    """
    g=Graph(handle_graph);found={}
    # Require closure of the graph rooted at the observed argument, rather than
    # searching unrelated appended records for a convenient target.
    queue=[g.root];seen=set()
    while queue:
        ref=queue.pop()
        if ref in seen:continue
        seen.add(ref);node=g.node(ref)
        for value in node.get('fields',{}).values():
            if isinstance(value,dict) and set(value)=={'ref'}:queue.append(value['ref'])
        if node['class']!='java.lang.invoke.MemberName':continue
        value=node['fields']['java.lang.invoke.MemberName.clazz']
        klass=g.value(value);identity=str(klass['class_object_id'])
        if identity in jdk_class_ids or identity in generated_dispatch_ids:continue
        kind,owner,name,desc=g.member(ref)
        if kind == 1 and (identity,owner,name,desc) in captured_fields:continue
        need(kind in (5,6,7,8,9),'unsupported-dynamic-member-kind')
        need(identity in ordinary_bindings and identity in definitions,'dynamic-target-not-byte-bound')
        bound=ordinary_bindings[identity]
        need(owner==bound['class'] and klass['loader']==bound['loader'],'dynamic-target-origin-differs')
        observed=definitions[identity]
        method=next((m for m in observed['methods'] if m['name']==name and m['signature']==desc),None)
        need(method is not None and method.get('sha256')==bound['methods'].get(name+desc),'dynamic-target-method-differs')
        found[(identity,owner,name,desc)]=bound
    need(len(found)==1,'dynamic-target-missing-or-ambiguous')
    target,bound=next(iter(found.items()));identity,owner,name,desc=target
    matches=[f for f in frames if str(f['class_object_id'])==identity and (f['class'],f['method'],f['signature'])==(owner,name,desc)]
    need(len(matches)==1 and matches[0]['loader']==bound['loader'],'actual-dynamic-target-frame-missing-or-ambiguous')
    return {'actual_target':{'class':owner,'method':name,'signature':desc,'class_object_id':identity},
            'class_sha256':bound['class_sha256'],'member_graph_and_actual_frame_agree':True,
            'resolved_vm_pointer_claimed':False,'native_admission':False}


def class_data_initialization(definition):
    """Only the exact single-LambdaForm classData initializer is supported.

    No arbitrary initializer, constant bootstrap, class-data list, extra field,
    or exception handler is accepted. Other JDK recipes remain unresolved.
    """
    raw=bytes.fromhex(definition['definition_input_hex']);c=class_file(raw);cp=c['pool']
    need(hashlib.sha256(raw).hexdigest()==definition['definition_input_sha256'],'form-class-data-source-hash')
    data=definition['class_data_graph'];form=definition['lambda_form_graph']
    need(data['root']==form['root'] and expression_recipe(data)==expression_recipe(form),'form-class-data-object-differs')
    need(set(c['fields'])=={'_D_0Ljava/lang/invoke/LambdaForm;'} and
         c['fields']['_D_0Ljava/lang/invoke/LambdaForm;']['flags']==24,'form-class-data-fields')
    need(not c['bootstraps'] and len(c['methods'])==2 and '<clinit>()V' in c['methods'],'form-class-data-method-closure')
    need(all(m['flags']==8 and m['exception_table']==[] for m in c['methods'].values()),'form-class-data-method-flags-or-handler')
    code=c['methods']['<clinit>()V']['code'];i=0
    need(code and code[0] in (0x12,0x13),'form-class-data-self-load')
    width=1 if code[0]==0x12 else 2;i=1+width
    need(int.from_bytes(code[1:i],'big')==c['this_index'],'form-class-data-wrong-self')
    need(len(code)==i+10 and code[i]==0xb8 and code[i+3]==0xc0 and code[i+6]==0xb3 and code[i+9]==0xb1,'form-class-data-extra-logic')
    invoke=int.from_bytes(code[i+1:i+3],'big');cast=int.from_bytes(code[i+4:i+6],'big');field=int.from_bytes(code[i+7:i+9],'big')
    need(member(cp,invoke,{10})==('java.lang.invoke.MethodHandles','classData','(Ljava/lang/Class;)Ljava/lang/Object;'),'form-class-data-wrong-accessor')
    need(cp[cast][0]==7 and text(cp,cp[cast][1])=='java/lang/invoke/LambdaForm','form-class-data-wrong-cast')
    need(member(cp,field,{9})==(c['name'].replace('/','.'),'_D_0','Ljava/lang/invoke/LambdaForm;'),'form-class-data-wrong-field')
    return {'class_data_initialization_verified':True,'class_data_object_id':data['root'],
            'native_admission':False}


def expression_recipe(graph):
    g=Graph(graph);cls='java.lang.invoke.LambdaForm';nf='java.lang.invoke.LambdaForm$NamedFunction';namecls='java.lang.invoke.LambdaForm$Name'
    need(g.node(g.root)['class']==cls,'form-root-class')
    need(g.field(g.root,cls,'customized') is None,'customized-form-unsupported')
    names=g.array(g.field(g.root,cls,'names'));arity=int(g.field(g.root,cls,'arity'));result=int(g.field(g.root,cls,'result'))
    need(0<=arity<=len(names) and (result==-1 or 0<=result<len(names)),'form-shape')
    refs={v['ref']:i for i,v in enumerate(names)};expr=[];effects=[]
    for i,ref in enumerate(names):
        need(int(g.field(ref,namecls,'index'))==i,'form-name-order')
        fn=g.field(ref,namecls,'function');args=g.field(ref,namecls,'arguments')
        if i<arity:
            need(fn is None and args is None,'form-parameter-function');expr.append(('param',i));continue
        need(fn is not None and args is not None,'form-function-missing')
        target=g.member(g.field(fn,nf,'member'));argv=[]
        for a in g.array(args):
            if isinstance(a,dict) and a.get('ref') in refs:
                j=refs[a['ref']];need(j<i,'form-forward-reference');argv.append(expr[j])
            else:
                n=g.node(a);need(n['class'] in ('java.lang.Integer','java.lang.Long'),'unsupported-form-constant')
                argv.append(('constant',int(n['fields'][n['class']+'.value'])))
        op='getfield' if target[0]==1 else 'call'
        need(target[0] in (1,5,6,7,9),'unsupported-form-member-kind')
        e=(op,*target[1:],tuple(argv));expr.append(e);effects.append(e)
    return {'arity':arity,'effects':effects,'return':None if result==-1 else expr[result]}


def replay_body(raw_definition, graph, method_name):
    """Compare every executed expression and effect to the captured Name graph.

    This decoder deliberately rejects branching and unknown intrinsics.
    It cannot alone establish runtime origins or the dynamic invocation target.
    """
    recipe=expression_recipe(graph)
    cpraw=bytes.fromhex(raw_definition['constant_pool_hex'])
    need(hashlib.sha256(cpraw).hexdigest()==raw_definition['constant_pool_sha256'],'form-pool-hash')
    cp=pool(cpraw,raw_definition['constant_pool_count'])
    methods=[m for m in raw_definition['methods'] if m['name']==method_name]
    need(len(methods)==1,'form-method-ambiguous')
    m=methods[0];code=bytes.fromhex(m['bytecode_hex'])
    need(hashlib.sha256(code).hexdigest()==m['sha256'],'form-method-hash')
    args,ret=descriptor(m['signature']);need(len(args)==recipe['arity'] and m['modifiers'] & 8,'form-method-arity')
    locals_,slot={},0
    for i,t in enumerate(args):locals_[slot]=('param',i);slot+=width(t)
    stack=[];effects=[];casts=[];i=0;returned=False
    compact_load=((0x1a,'I'),(0x1e,'J'),(0x22,'F'),(0x26,'D'),(0x2a,'A'))
    compact_store=((0x3b,'I'),(0x3f,'J'),(0x43,'F'),(0x47,'D'),(0x4b,'A'))
    def popn(n):
        need(len(stack)>=n,'form-stack-underflow')
        if n==0:return []
        values=stack[-n:];del stack[-n:];return values
    while i<len(code):
        op=code[i];i+=1
        load=next((op-start for start,_ in compact_load if start<=op<start+4),None)
        store=next((op-start for start,_ in compact_store if start<=op<start+4),None)
        if op in range(0x15,0x1a) or op in range(0x36,0x3b):
            need(i<len(code),'form-truncated-local');index=code[i];i+=1
            if op<0x1a:load=index
            else:store=index
        if load is not None:
            need(load in locals_,'form-uninitialized-local');stack.append(locals_[load]);continue
        if store is not None:
            locals_[store]=popn(1)[0];continue
        if op==0x59:
            need(stack,'form-stack-underflow');stack.append(stack[-1]);continue
        if 0x02<=op<=0x08:stack.append(('constant',op-3));continue
        if op==0x32:  # The exact reference-array read intrinsic, not arbitrary code.
            e=('call','java.lang.invoke.MethodHandleImpl$ArrayAccessor','getElementL',
               '([Ljava/lang/Object;I)Ljava/lang/Object;',tuple(popn(2)))
            effects.append(e);stack.append(e);continue
        if op in (0xc0,0xb4,0xb6,0xb7,0xb8,0xb9):
            need(i+2<=len(code),'form-truncated-member');index=int.from_bytes(code[i:i+2],'big');i+=2
            if op==0xc0:
                need(index in cp and cp[index][0]==7 and stack,'form-cast-shape')
                casts.append((stack[-1],text(cp,cp[index][1])))
                continue
            owner,name,sig=member(cp,index,{9} if op==0xb4 else {10,11})
            if op==0xb4:
                e=('getfield',owner,name,sig,tuple(popn(1)));stack.append(e);effects.append(e);continue
            params,result=descriptor(sig)
            actual=popn(len(params)+(op!=0xb8))
            if op==0xb9:
                need(i+2<=len(code) and code[i]==1+sum(width(t) for t in params) and code[i+1]==0,'form-interface-operands');i+=2
            e=('call',owner,name,sig,tuple(actual));effects.append(e)
            if result!='V':stack.append(e)
            continue
        if op in (0xac,0xad,0xae,0xaf,0xb0,0xb1):
            result=None if op==0xb1 else popn(1)[0]
            need(not stack and i==len(code) and result==recipe['return'],'form-return-differs')
            returned=True;break
        need(False,'unsupported-form-opcode-'+hex(op))
    need(returned and effects==recipe['effects'],'form-expression-effects-differ')
    # Each cast must be a reference type required by that same expression's
    # graph operation. Reject casts to unrelated classes and duplicate checks.
    required={}
    for effect in recipe['effects']:
        op,owner,name,sig,argv=effect
        types=['L'+owner.replace('.','/')+';'] if op=='getfield' else descriptor(sig)[0]
        if op=='call' and len(argv)==len(types)+1:types=['L'+owner.replace('.','/')+';']+types
        need(len(types)==len(argv),'form-operation-arity')
        for expr,typ in zip(argv,types):
            if typ.startswith(('L','[')):
                required.setdefault(expr,set()).add(typ[1:-1] if typ.startswith('L') else typ)
    seen=set()
    for expr,cast in casts:
        need(cast!='java/lang/Object' and cast in required.get(expr,set()),'form-unrelated-reference-cast')
        need((expr,cast) not in seen,'form-duplicate-reference-cast');seen.add((expr,cast))
    # Still not admission: initialize class data, prove the runtime target and
    # bind the exact generator-emission/definition events and runtime origins.
    return {'expression_effects_match':True,'casts_checked_against_graph':len(casts),
            'adapter_body_verified':False,'native_admission':False}
