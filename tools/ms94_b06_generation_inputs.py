"""Validate genuine generation inputs; caller stacks never establish ownership."""
import base64
import hashlib
from tools.ms94_b06_admission import check

POLICY='generation-inputs-v1'
FACTORY='java.lang.invoke.InnerClassLambdaMetafactory.'
DEFINER='java.lang.invoke.MethodHandles$Lookup$ClassDefiner.'
INVOKER='java.lang.invoke.InvokerBytecodeGenerator.'
LOADER='java.lang.ClassLoader.defineClass('

def class_object(value):
    check(isinstance(value,dict) and set(value)=={'class','class_object_id','loader','signature'},'generation-input-class')
    check(type(value['class_object_id']) is int and value['class_object_id']>0 and
          all(isinstance(value[k],str) and value[k] for k in ('class','loader','signature')),'generation-input-identity')
    check(value['loader']=='bootstrap' or value['loader'].isdigit(),'generation-input-loader')
    return value

def validate(record):
    witness=record.get('class_input_witness')
    check(isinstance(witness,dict) and witness.get('policy')==POLICY,'generation-input-policy')
    method=record.get('entry_method','')
    if method.startswith(LOADER):
        check(set(witness)=={'policy','kind','sha256','bytes','defining_loader','classification'} and
              witness['kind']=='classfile-bytes' and witness['classification']=='unresolved-bytecode-input-only',
              'generation-input-bytecode-shape')
        try:raw=base64.b64decode(record['definition_input_base64'],validate=True)
        except Exception as exc:raise ValueError('generation-input-bytecode-encoding') from exc
        digest=hashlib.sha256(raw).hexdigest()
        check(0<len(raw)<=1024*1024 and type(witness['bytes']) is int and len(raw)==witness['bytes'] and
              digest==witness['sha256']==record.get('definition_input_sha256') and
              witness['defining_loader']==record.get('defining_loader') and
              isinstance(witness['defining_loader'],str) and witness['defining_loader'].isdigit(),
              'generation-input-bytecode-binding')
        return []  # Captured bytes are not a resulting runtime class identity.
    check(set(witness)=={'policy','kind','inputs'} and witness['kind']=='class-objects','generation-input-class-shape')
    inputs=witness['inputs'];check(isinstance(inputs,dict),'generation-input-fields')
    if method.startswith(FACTORY):expected={'receiver.targetClass'}
    elif method.startswith(DEFINER):expected={'receiver.lookup.lookupClass'}
    elif method.startswith(INVOKER):expected={'receiver.invokerType.rtype','receiver.invokerType.ptypes'}
    else:raise ValueError('generation-input-unsupported-method')
    check(set(inputs)==expected,'generation-input-field-paths')
    if method.startswith(INVOKER):
        check(isinstance(inputs['receiver.invokerType.ptypes'],list) and len(inputs['receiver.invokerType.ptypes'])<=255,'generation-input-parameters')
        return [class_object(inputs['receiver.invokerType.rtype']),*[class_object(v) for v in inputs['receiver.invokerType.ptypes']]]
    return [class_object(next(iter(inputs.values())))]
