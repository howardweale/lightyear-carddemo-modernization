"""Host experiment replay. This module never grants native admission.

No name-pattern attribution: linkage comes from a suspended generator invocation,
its actual Class return, and the bound host's exact invokedynamic instruction.
"""
import hashlib
from tools.ms94_b06_classfile import Reader
from tools.ms94_b06_forwarding_stub import pool, text, member, descriptor, load_family, width
from tools.b06_host_probe.pool_analysis import original_pool, check_methods, compare_extension, ENGINE
import copy


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def class_file(raw):
    count, cpraw = original_pool(raw)
    cp = pool(cpraw, count)
    r = Reader(raw)
    r.take(10 + len(cpraw))
    flags, this, parent = r.u2(), r.u2(), r.u2()
    interfaces = [r.u2() for _ in range(r.u2())]
    def attributes():
        out = {}
        for _ in range(r.u2()):
            name = text(cp, r.u2())
            need(name not in out, 'duplicate-attribute')
            out[name] = r.take(r.u4())
        return out
    def members():
        out = {}
        for _ in range(r.u2()):
            access, name, desc = r.u2(), text(cp, r.u2()), text(cp, r.u2())
            need(name + desc not in out, 'duplicate-member')
            attrs = attributes()
            item = {'name': name, 'signature': desc, 'flags': access, 'attributes': attrs}
            if 'Code' in attrs:
                c = Reader(attrs['Code'])
                item['max_stack'], item['max_locals'] = c.u2(), c.u2()
                item['code'] = c.take(c.u4())
                item['exception_table'] = [tuple(c.u2() for _ in range(4)) for _ in range(c.u2())]
                for _ in range(c.u2()):
                    c.take(2); c.take(c.u4())
                need(c.offset == len(c.data), 'code-trailing-data')
            out[name + desc] = item
        return out
    fields, methods, attrs = members(), members(), attributes()
    need(r.offset == len(raw), 'class-trailing-data')
    bootstraps = []
    if 'BootstrapMethods' in attrs:
        b = Reader(attrs['BootstrapMethods'])
        for _ in range(b.u2()):
            handle = b.u2()
            bootstraps.append((handle, [b.u2() for _ in range(b.u2())]))
        need(b.offset == len(b.data), 'bootstrap-trailing-data')
    return {'pool': cp, 'pool_raw': cpraw, 'count': count, 'flags': flags, 'this_index':this,
            'name': text(cp, cp[this][1]), 'parent': parent, 'interfaces': interfaces,
            'fields': fields, 'methods': methods, 'bootstraps': bootstraps}


def method_type(value):
    need(value.get('class') == 'java.lang.invoke.MethodType', 'method-type-object')
    f = value['fields']
    return '(' + ''.join(p['signature'] for p in f['java.lang.invoke.MethodType.ptypes']) + ')' + f['java.lang.invoke.MethodType.rtype']['signature']


def method_handle(cp, index):
    need(index in cp and cp[index][0] == 15, 'bootstrap-handle-type')
    kind, ref = cp[index][1]
    return kind, member(cp, ref, {10, 11})


def declared_definition(raw, observed, test_engine=None):
    """Recheck exact source, pool, all original methods and interface declarations."""
    need('constant_pool_hex' in observed and 'methods' in observed, 'unprepared-definition-not-admitted')
    cls = class_file(raw)
    need(observed['class'].replace('.', '/') == cls['name'], 'source-name')
    runtime = bytes.fromhex(observed['constant_pool_hex'])
    need(hashlib.sha256(runtime).hexdigest() == observed['constant_pool_sha256'], 'runtime-pool-hash')
    if runtime != cls['pool_raw']:
        need(cls['name'] == ENGINE and test_engine is not None, 'unapproved-pool-reconstitution')
        compare_extension(raw, runtime.hex(), observed['constant_pool_count'])
        interface = class_file(test_engine)
        need(interface['name'] == 'org/junit/platform/engine/TestEngine' and interface['flags'] & 0x200, 'bound-interface-identity')
        names = [text(cls['pool'], cls['pool'][i][1]) for i in cls['interfaces']]
        need(interface['name'] in names, 'host-interface-binding')
        for sig in ('getId()Ljava/lang/String;', 'discover(Lorg/junit/platform/engine/EngineDiscoveryRequest;Lorg/junit/platform/engine/UniqueId;)Lorg/junit/platform/engine/TestDescriptor;'):
            m = interface['methods'].get(sig)
            need(m is not None and m['flags'] & 0x400 and not m['flags'] & 8 and 'code' not in m, 'bound-interface-abstract-declaration')
    else:
        need(observed['constant_pool_count'] == cls['count'], 'runtime-pool-count')
    for m in observed['methods']:
        if 'bytecode_hex' in m:
            need(hashlib.sha256(bytes.fromhex(m['bytecode_hex'])).hexdigest() == m['sha256'], 'runtime-method-hash')
    # JDWP Methods adds its documented 0xf0000000 synthetic marker. Compare
    # the complete expected wire value; never mask arbitrary high bits away.
    # Raw modifiers remain in the observation and are replayed on every read.
    decoded = copy.deepcopy(observed['methods'])
    for m in decoded:
        original = cls['methods'].get(m['name'] + m['signature'])
        need(original is not None, 'additional-runtime-method')
        expected = original['flags']
        wire = expected | (0xf0000000 if expected & 0x1000 else 0)
        if wire >= 0x80000000:
            wire -= 0x100000000
        need(m['modifiers'] == wire, 'method-wire-flags-differ')
        m['modifiers'] = expected
    check_methods(raw, decoded)
    return cls


def ordinary_definition(record, observed, artifact_bytes, code_source, *, test_engine=None):
    """Prove a loader's actual definition/return against an admitted artifact.

    `artifact_bytes` and `code_source` must come from an independently bound
    artifact; values asserted by the observed program are never the catalogue.
    This host diagnostic does not itself admit a native loader or artifact.
    """
    need(record.get('kind') == 'ordinary-definition' and record.get('entry_method') ==
         'java.lang.ClassLoader.defineClass(Ljava/lang/String;[BIILjava/security/ProtectionDomain;)Ljava/lang/Class;',
         'ordinary-definition-boundary')
    raw = bytes.fromhex(record['definition_input_hex'])
    need(raw == artifact_bytes and hashlib.sha256(raw).hexdigest() == record['definition_input_sha256'],
         'ordinary-definition-bytes-differ')
    returned = record['returned_class']
    need(returned['class_object_id'] == observed['class_object_id'] and
         returned['class'] == observed['class'] and
         returned['loader'] == observed['loader'] == record['defining_loader'],
         'ordinary-definition-return-differs')
    need(record['requested_name'] in (None, observed['class']) and record.get('code_source') == code_source,
         'ordinary-definition-origin-differs')
    declared_definition(raw, observed, test_engine)
    return {'definition_return_verified': True, 'class_sha256': hashlib.sha256(raw).hexdigest(),
            'class_object_id': observed['class_object_id'], 'native_admission': False}


def lambda_linkage(record, definitions, host_bytes, *, test_engine=None):
    """Validate a metafactory return against a single exact bound bootstrap site.

    Returns linkage only, not an adapter-body or runtime-origin admission.
    """
    need(record.get('entry_method') == 'java.lang.invoke.InnerClassLambdaMetafactory.spinInnerClass()Ljava/lang/Class;', 'wrong-generator-boundary')
    f = record['lambda_factory']
    host = f['targetClass']
    observed = definitions[str(host['class_object_id'])]
    cls = declared_definition(host_bytes, observed, test_engine)
    need(host['class'] == observed['class'] and host['loader'] == observed['loader'], 'host-runtime-binding')
    returned = record['returned_class']
    generated = definitions[str(returned['class_object_id'])]
    need(returned['class'] == generated['class'] and returned['loader'] == generated['loader'] == host['loader'], 'generated-loader-or-return-binding')
    cp = cls['pool']
    sites = []
    for frame in record['stack']:
        if frame['class_object_id'] != host['class_object_id']:
            continue
        need(frame['class'] == host['class'] and frame['loader'] == host['loader'], 'site-host-binding')
        method = cls['methods'].get(frame['method'] + frame['signature'])
        need(method is not None and 'code' in method, 'site-method-unbound')
        code, pos = method['code'], frame['code_index']
        if not (0 <= pos <= len(code)-5 and code[pos] == 0xba):
            continue
        need(code[pos+3:pos+5] == b'\0\0', 'invokedynamic-reserved-operands')
        index = int.from_bytes(code[pos+1:pos+3], 'big')
        need(cp[index][0] == 18, 'invokedynamic-pool-tag')
        bootstrap, nt = cp[index][1]
        need(cp[nt][0] == 12 and 0 <= bootstrap < len(cls['bootstraps']), 'bootstrap-index')
        name_index, desc_index = cp[nt][1]
        name, desc = text(cp, name_index), text(cp, desc_index)
        handle, args = cls['bootstraps'][bootstrap]
        kind, target = method_handle(cp, handle)
        need(kind == 6 and target == ('java.lang.invoke.LambdaMetafactory', 'metafactory', '(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;'), 'unsupported-bootstrap-recipe')
        need(len(args) == 3 and cp[args[0]][0] == cp[args[2]][0] == 16, 'bootstrap-argument-layout')
        implementation = method_handle(cp, args[1])
        sam, dynamic = text(cp, cp[args[0]][1]), text(cp, cp[args[2]][1])
        if (name, desc, sam, dynamic) != (f['interfaceMethodName'], method_type(f['factoryType']), method_type(f['interfaceMethodType']), method_type(f['dynamicMethodType'])):
            continue
        info = f['implInfo']['fields']
        actual_member = info['java.lang.invoke.InfoFromMemberName.member']['fields']
        actual_target = (actual_member['java.lang.invoke.MemberName.clazz']['class'], actual_member['java.lang.invoke.MemberName.name'], f['implMethodDesc'])
        need(implementation == (int(info['java.lang.invoke.InfoFromMemberName.referenceKind']), actual_target), 'implementation-handle-mismatch')
        need(f['implClass']['class'] == actual_target[0] and f['implMethodName'] == actual_target[1], 'resolved-implementation-mismatch')
        opcode_kind=int(f['implKind'])
        if opcode_kind != implementation[0]:
            target_method=cls['methods'].get(actual_target[1]+actual_target[2])
            need(implementation[0]==7 and opcode_kind==5 and actual_target[0]==host['class'] and
                 target_method is not None and target_method['flags'] & 2 and not target_method['flags'] & 8,
                 'unsupported-reference-kind-adaptation')
        need(f['isSerializable'] == 'false' and not f['altInterfaces'] and not f['altMethods'] and f['useImplMethodHandle'] == 'false', 'unsupported-adapter-recipe')
        sites.append({'host_class_sha256': hashlib.sha256(host_bytes).hexdigest(), 'host_class':host['class'],
                      'host_method':frame['method']+frame['signature'], 'code_index':pos, 'bootstrap_index':bootstrap,
                      'implementation_kind':implementation[0], 'implementation_opcode_kind':opcode_kind, 'implementation':implementation[1], 'sam':sam,
                      'instantiated':dynamic, 'factory_type':desc, 'loader':host['loader'],
                      'generated_class_object_id':returned['class_object_id']})
    need(len(sites) == 1, 'missing-or-ambiguous-bootstrap-site')
    return {**sites[0], 'native_admission':False, 'adapter_body_verified':False}


def lambda_body(record, definitions, linkage):
    """Closed straight-line adapter recipe, derived from the linked bootstrap.

    Captures and arguments are consumed exactly once and in order. No branch,
    arithmetic, monitor, arbitrary helper invoke, field mutation in the SAM,
    extra method or static initializer is accepted. Reference casts must be the
    exact bootstrap-declared adaptation. Unsupported shapes remain untrusted.
    """
    f = record['lambda_factory']
    d = definitions[str(record['returned_class']['class_object_id'])]
    raw = bytes.fromhex(d['constant_pool_hex'])
    need(hashlib.sha256(raw).hexdigest() == d['constant_pool_sha256'], 'generated-pool-hash')
    cp = pool(raw, d['constant_pool_count'])
    captures, _ = descriptor(linkage['factory_type'])
    sam_args, sam_ret = descriptor(linkage['sam'])
    dynamic_args, dynamic_ret = descriptor(linkage['instantiated'])
    target_class, target_name, target_desc = linkage['implementation']
    target_args, target_ret = descriptor(target_desc)
    kind = linkage['implementation_opcode_kind']
    need(kind in (5, 6, 7, 8, 9), 'unsupported-implementation-kind')
    need(len(sam_args) == len(dynamic_args), 'instantiated-arity')
    need(f['argDescs'] == captures and len(f['argNames']) == len(captures), 'capture-layout')
    expected_fields = [{'name':name, 'signature':sig, 'modifiers':0x12} for name,sig in zip(f['argNames'],captures)]
    need(d['fields'] == expected_fields, 'generated-capture-fields')
    ctor_sig = '('+''.join(captures)+')V'
    methods = {m['name']+m['signature']:m for m in d['methods']}
    sam_key = f['interfaceMethodName']+linkage['sam']
    need(len(methods) == len(d['methods']) == 2 and set(methods) == {'<init>'+ctor_sig,sam_key}, 'generated-method-closure')
    # HotSpot reconstitutes a hidden class's self-reference with '+' while JDI
    # reports '/' in name() and '.' in signature(). Only compare this exact
    # returned Class identity, after host/site/loader linkage; this is not a
    # pattern that grants trust to a purported lambda.
    need('/' in d['class'], 'missing-runtime-hidden-identity')
    prefix, suffix = d['class'].rsplit('/',1)
    need(d['signature']=='L'+prefix.replace('.','/')+'.'+suffix+';', 'hidden-signature-differs')
    self_name = prefix+'+'+suffix

    def tokens(m):
        code = bytes.fromhex(m['bytecode_hex'])
        need(hashlib.sha256(code).hexdigest() == m['sha256'], 'generated-method-hash')
        result, i = [], 0
        compact = ((0x1a,'I'),(0x1e,'J'),(0x22,'F'),(0x26,'D'),(0x2a,'A'))
        while i < len(code):
            op = code[i]; i += 1
            loaded = next(((family,op-start) for start,family in compact if start <= op < start+4), None)
            if op in range(0x15,0x1a):
                need(i < len(code), 'truncated-adapter-load')
                loaded = ('IJFDA'[op-0x15],code[i]); i += 1
            if loaded is not None:
                result.append(('load',*loaded)); continue
            if op in (0xb4,0xb5,0xb6,0xb7,0xb8,0xb9,0xbb,0xc0):
                need(i+2 <= len(code), 'truncated-adapter-pool-index')
                index = int.from_bytes(code[i:i+2],'big'); i += 2
                if op in (0xbb,0xc0):
                    need(index in cp and cp[index][0] == 7, 'adapter-class-pool-tag')
                    result.append(('new' if op==0xbb else 'cast',text(cp,cp[index][1]).replace('/','.')))
                else:
                    ref = member(cp,index,{9} if op in (0xb4,0xb5) else {10,11})
                    result.append((op,*ref))
                    if op==0xb9:
                        args,_ = descriptor(ref[2])
                        need(i+2 <= len(code) and code[i] == 1+sum(width(t) for t in args) and code[i+1]==0,'adapter-interface-operands')
                        i += 2
                continue
            need(op in (0x59,0xac,0xad,0xae,0xaf,0xb0,0xb1), 'adapter-extra-logic')
            result.append((op,))
        return result

    # Constructor bytecode is a closed exact sequence: Object.<init> then stores.
    ctor = [('load','A',0),(0xb7,'java.lang.Object','<init>','()V')]
    slot = 1
    for name,sig in zip(f['argNames'],captures):
        ctor.extend([('load','A',0),('load',load_family(sig),slot),(0xb5,self_name,name,sig)])
        slot += width(sig)
    ctor.append((0xb1,))
    need(methods['<init>'+ctor_sig]['modifiers'] == 2 and tokens(methods['<init>'+ctor_sig]) == ctor, 'adapter-constructor-differs')
    need(methods[sam_key]['modifiers'] == 1, 'adapter-sam-modifiers')
    body = tokens(methods[sam_key])
    pos = 0
    def consume(expected):
        nonlocal pos
        need(pos < len(body) and body[pos] == expected, 'adapter-recipe-differs')
        pos += 1
    if kind == 8:
        need(target_name == '<init>' and target_ret == 'V', 'adapter-constructor-target')
        consume(('new',target_class));consume((0x59,))
    else:
        need(target_name not in ('<init>','<clinit>'), 'adapter-nonconstructor-target')
    for name,sig in zip(f['argNames'],captures):
        consume(('load','A',0));consume((0xb4,self_name,name,sig))
    expected = ([] if kind in (6,8) else ['L'+target_class.replace('.','/')+';']) + target_args
    need(len(captures)+len(dynamic_args)==len(expected), 'adapter-invoke-arity')
    need(captures==expected[:len(captures)], 'unsupported-capture-adaptation')
    boxes = {'Z':('Boolean','booleanValue'),'B':('Byte','byteValue'),'C':('Character','charValue'),
             'S':('Short','shortValue'),'I':('Integer','intValue'),'J':('Long','longValue'),
             'F':('Float','floatValue'),'D':('Double','doubleValue')}
    slot=1
    for source,dest,wanted in zip(sam_args,dynamic_args,expected[len(captures):]):
        consume(('load',load_family(source),slot));slot += width(source)
        if source != dest:
            need(source.startswith(('L','[')) and dest.startswith('L'), 'unsupported-primitive-adaptation')
            consume(('cast',dest[1:-1].replace('/','.')))
        if wanted in boxes and dest.startswith('L'):
            box,unbox=boxes[wanted]
            need(dest=='Ljava/lang/'+box+';', 'unboxing-type-mismatch')
            consume((0xb6,'java.lang.'+box,unbox,'()'+wanted))
        else:
            need(dest==wanted or (dest.startswith(('L','[')) and wanted=='Ljava/lang/Object;'), 'unsupported-target-argument-adaptation')
    invoke = {5:0xb6,6:0xb8,7:0xb7,8:0xb7,9:0xb9}[kind]
    consume((invoke,target_class,target_name,target_desc))
    result = 'L'+target_class.replace('.','/')+';' if kind==8 else target_ret
    if pos < len(body) and body[pos][0] == 'cast':
        need(sam_ret.startswith('L') and result.startswith(('L','[')), 'invalid-return-cast')
        consume(('cast',sam_ret[1:-1].replace('/','.')))
        result = sam_ret
    need(result==sam_ret or (result.startswith(('L','[')) and sam_ret.startswith(('L','['))), 'unsupported-return-adaptation')
    consume(({'I':0xac,'J':0xad,'F':0xae,'D':0xaf,'A':0xb0,'V':0xb1}[load_family(sam_ret)],))
    need(pos == len(body), 'adapter-trailing-logic')
    return {**linkage,'adapter_body_verified':True,'generated_pool_sha256':d['constant_pool_sha256'],
            'generated_methods_sha256':{k:v['sha256'] for k,v in methods.items()}}


def adjacent_target(proof, frames):
    matches=[i for i,f in enumerate(frames) if f['class_object_id']==proof['generated_class_object_id']]
    need(len(matches)==1 and matches[0]>0,'missing-or-ambiguous-adjacent-target')
    generated, target=frames[matches[0]],frames[matches[0]-1]
    need((target['class'],target['method'],target['signature'])==tuple(proof['implementation']), 'adjacent-target-differs')
    need(generated['loader']==target['loader']==proof['loader'], 'adjacent-target-loader-differs')
    return {**proof,'adjacent_target_verified':True,'adjacent_direction':'younger'}
