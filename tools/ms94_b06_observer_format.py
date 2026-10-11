"""Versioned bounded observer decoding. Historical records pass through unchanged."""
import base64
import binascii
from tools.ms94_b06_admission import check

FORMAT = 'bounded-observer-v1'
BINARY_FIELDS = {'constant_pool_base64': 'constant_pool_hex',
                 'bytecode_base64': 'bytecode_hex',
                 'definition_input_base64': 'definition_input_hex',
                 'returned_bytes_base64': 'returned_bytes_hex'}


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in BINARY_FIELDS:
            target = BINARY_FIELDS[key]
            check(target not in value and isinstance(item, str) and len(item) <= 1398104,
                  'observer-bounded-binary-shape')
            try:
                raw = base64.b64decode(item, validate=True)
            except (ValueError, binascii.Error):
                check(False, 'observer-bounded-binary-encoding')
            check(len(raw) <= 1024*1024 and base64.b64encode(raw).decode('ascii') == item,
                  'observer-bounded-binary-bound')
            result[target] = raw.hex()
        else:
            result[key] = decode(item)
    return result


def normalize(event):
    event = diagnostic_wire(event)
    if event.get('observer_format') != FORMAT:
        check(event.get('kind') != 'class-definition-v3', 'observer-bounded-unannounced')
        return event
    result = decode(event)
    if result['kind'] == 'class-definition-v3':
        result['kind'] = 'class-definition-v2'
    return result


def java_json(value):
    """The v3 writer's compact UTF-8 JSON; control escapes are always u00xx."""
    import json
    if isinstance(value, dict):
        return '{' + ','.join(java_json(str(k)) + ':' + java_json(v) for k,v in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ','.join(java_json(v) for v in value) + ']'
    if isinstance(value, str):
        return '"' + ''.join(('\\' + c if c in ('"', '\\') else
                              '\\u%04x' % ord(c) if ord(c) < 32 else c) for c in value) + '"'
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def audit_detail(event):
    """Expand the versioned lossless detail only; quotas/signatures use wire bytes."""
    event=diagnostic_wire(event)
    detail=event.get('detail')
    if not isinstance(detail,dict) or 'encoding' not in detail:return event
    import hashlib
    import json
    import zlib
    check(event.get('observer_format') == FORMAT and event.get('kind') == 'observer-audit' and
          event.get('action') == 'jdi-event' and set(detail)=={'encoding','base64','bytes','sha256'} and
          detail['encoding']=='deflate-json-v1' and type(detail['bytes']) is int and
          0 < detail['bytes'] <= 256*1024 and isinstance(detail['base64'],str) and
          len(detail['base64']) <= 350000, 'observer-detail-encoding')
    try:
        compressed=base64.b64decode(detail['base64'],validate=True)
        check(base64.b64encode(compressed).decode('ascii')==detail['base64'],'observer-detail-base64')
        decoder=zlib.decompressobj()
        raw=decoder.decompress(compressed,256*1024+1)
        check(len(raw)==detail['bytes'] and decoder.eof and not decoder.unconsumed_tail and
              not decoder.unused_data and hashlib.sha256(raw).hexdigest()==detail['sha256'],
              'observer-detail-bound-or-digest')
        def unique(pairs):
            value={}
            for key,item in pairs:
                check(key not in value,'observer-detail-duplicate-key');value[key]=item
            return value
        unpacked=json.loads(raw.decode('utf-8'),object_pairs_hook=unique)
        check(isinstance(unpacked,dict),'observer-detail-object')
    except (ValueError,UnicodeError,zlib.error,binascii.Error):
        check(False,'observer-detail-invalid')
    return {**event,'detail':unpacked}


DIAGNOSTIC_KINDS = ('observer-audit', 'breakpoint-lifecycle', 'watched-class-prepare',
                    'observer-heap-telemetry')


def diagnostic_dictionary():
    """Fixed public templates, never learned from observations or prior records.

    The algorithm and order are the d3 wire contract, duplicated in the Java
    writer and checked by a real-Java round trip. All IDs, hashes and clocks in
    templates are synthetic zeros. Only public JDK symbols enter the dictionary.
    """
    from itertools import permutations
    locations = [dict(zip(('class','method','signature','code_index'), (*row,0))) for row in (
        ('java.lang.invoke.InnerClassLambdaMetafactory','spinInnerClass','()Ljava/lang/Class;'),
        ('java.lang.invoke.MethodHandles$Lookup$ClassDefiner','defineClass','(ZLjava/lang/Object;)Ljava/lang/Class;'),
        ('java.lang.invoke.InvokerBytecodeGenerator','generateCustomizedCodeBytes','()[B'),
        ('java.lang.invoke.InvokerBytecodeGenerator','generateLambdaFormInterpreterEntryPointBytes','()[B'),
        ('java.lang.invoke.InvokerBytecodeGenerator','generateNamedFunctionInvokerImpl','(Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/MemberName;'))]
    patterns=[]
    for location in locations:
        for fields in permutations(location):patterns.append({key:location[key] for key in fields})
        for action in ('created','enabled','disabled','deleted'):
            patterns.append(dict(action=action,request_id=0,location=location,request_kind='breakpoint',
                                 thread_filter=0,monotonic_ns=0,audit_index=0,observer_format=FORMAT))
        for armed in (False,True):
            detail=dict(event_type='breakpoint',request_id=0,thread_id=0,thread_name_sha256='0'*64,
                        location=location,depth=0,top_location=location,selected_generation=True,
                        return_breakpoint=armed,catch_breakpoint=False,pending_count=int(armed),
                        pending=[0] if armed else [],set_size=1,suspend_policy=2)
            if armed:detail['arm']=dict(request_id=0,method=location['class']+'.'+location['method']+location['signature'],
                                       depth=0,generation_id=0)
            patterns.append(dict(policy='structural-jdi-v2',audit_index=0,event_set_id=0,event_position=0,
                                 action='jdi-event',detail=detail,observer_format=FORMAT))
    patterns.append(dict(policy='structural-jdi-v2',audit_index=0,event_set_id=0,event_position=0,
                         action='event-set-close',detail=dict(dispatch_completed=1,resume_requested=1,resume_completed=1),
                         observer_format=FORMAT))
    return java_json(patterns).encode('utf-8')[-32768:]


DIAGNOSTIC_DICTIONARY = diagnostic_dictionary()


def diagnostic_wire(event):
    """Losslessly expand one d3 diagnostic; never mutate the sealed wire object.

    A zlib preset dictionary is fixed by this version, not cross-record state.
    Framing stays visible; the bounded body retains every other actual field.
    Signatures and byte quotas must be applied to the original event, not this view.
    """
    if 'd3' not in event:return event
    import json
    import zlib
    check(set(event)=={'kind','sequence','checkpoint','d3'} and event['kind'] in DIAGNOSTIC_KINDS and
          event['checkpoint'] is False and type(event['sequence']) is int and event['sequence']>0 and
          isinstance(event['d3'],str) and len(event['d3'])<=350000,'observer-diagnostic-wire-shape')
    try:
        packed=base64.b64decode(event['d3'],validate=True)
        check(base64.b64encode(packed).decode('ascii')==event['d3'],'observer-diagnostic-wire-base64')
        check(len(packed)>=6 and packed[1] & 32 and
              int.from_bytes(packed[2:6],'big')==zlib.adler32(DIAGNOSTIC_DICTIONARY),
              'observer-diagnostic-wire-dictionary')
        decoder=zlib.decompressobj(zdict=DIAGNOSTIC_DICTIONARY)
        raw=decoder.decompress(packed,256*1024+1)
        check(0<len(raw)<=256*1024 and decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data,
              'observer-diagnostic-wire-bound')
        def unique(pairs):
            body={}
            for key,value in pairs:
                check(key not in body,'observer-diagnostic-wire-duplicate-key');body[key]=value
            return body
        def invalid_constant(value):raise ValueError('non-JSON number')
        body=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=invalid_constant)
        check(isinstance(body,dict) and body.get('observer_format')==FORMAT and
              not ({'kind','sequence','checkpoint','d3'} & body.keys()),'observer-diagnostic-wire-body')
    except (ValueError,UnicodeError,zlib.error,binascii.Error):
        check(False,'observer-diagnostic-wire-invalid')
    return {'kind':event['kind'],**body,'sequence':event['sequence'],'checkpoint':False}
