"""Derive closure inputs from a pinned probe observed at a no-candidate launch.

The host launcher must sign the raw output and exact probe/image/JVM/config
bindings. That launcher requires a NEW Tower window; inventory-only approval
never permits this agent or any target JVM. No process is launched here.
"""
import hashlib,json
from pathlib import PurePosixPath
from lightyear_control_tower.decisions import verify_envelope
from .resolved_runtime import read,file_path

def h(raw):return hashlib.sha256(raw).hexdigest()

def produce(raw,config,surefire,inventory,receipt,key,expected):
    if not verify_envelope(receipt,key):raise ValueError("runtime-launch-signature")
    if receipt.get('schema')!='b06-runtime-launch-receipt/1' or receipt.get('passed') is not True:
        raise ValueError('successful-trusted-runtime-launch-required')
    if receipt.get('bindings')!=expected or set(expected)!={'probe_sha256','image','java_sha256','plan_sha256','tower_decision_sha256'}:
        raise ValueError('runtime-launch-bindings')
    outputs={'observation':h(raw),'config.ini':h(config),'surefire.properties':h(surefire),'inventory':h(json.dumps(inventory,sort_keys=True).encode())}
    if receipt.get('outputs')!=outputs:raise ValueError('runtime-output-changed')
    obs=json.loads(raw)
    if obs['schema']!='b06-runtime-launch-observation/1':raise ValueError('runtime-observation-schema')
    parsed=read(config,surefire);bundles=obs['bundles']
    ids=[b['id'] for b in bundles]
    if not bundles or len(ids)!=len(set(ids)) or 0 not in ids:raise ValueError('runtime-bundle-closure')
    if any(b['state'] not in (4,8,16,32) or b['id']==0 and b['state']!=32 for b in bundles):raise ValueError('unresolved-runtime-bundle')
    framework=file_path(obs['framework_url'])
    paths=[file_path(b['location']) for b in bundles if b['id']!=0]
    classpath=[]
    for p in obs['java_class_path'].split(':'):
        if not p.startswith('/') or '..' in PurePosixPath(p).parts or '*' in p:raise ValueError('runtime-classpath-not-exact')
        classpath.append(p)
    java=PurePosixPath(obs['java_home']);modules=str(java/'lib/modules');tool=str(java/'bin/jimage')
    records={r['path']:r for r in inventory['artifacts']}
    selected=set(paths+classpath+parsed['surefire_booter_classpath']+[framework,modules,tool])
    if not selected<=set(records):raise ValueError('runtime-path-not-in-inventory')
    if records[str(java/'bin/java')]['sha256']!=expected['java_sha256']:raise ValueError('runtime-java-changed')
    jdk=records[modules]
    if not jdk.get('expanded_class_entries') or not jdk.get('expanded_class_bytes'):raise ValueError('measured-jimage-inventory-required')
    return dict(schema='b06-resolved-runtime/2',resolved=True,launch_observed=True,
        installation_inputs=parsed,equinox_bundles=paths,resolved_bundle_states=bundles,
        surefire_booter_classpath=list(dict.fromkeys(classpath+parsed['surefire_booter_classpath'])),
        framework_jar=framework,jdk_modules=modules,jdk_class_entries=jdk['expanded_class_entries'],
        jdk_expanded_bytes=jdk['expanded_class_bytes'],jimage_tool=dict(path=tool,sha256=records[tool]['sha256']),
        artifact_sha256={p:records[p]['sha256'] for p in selected},launch_receipt=receipt,
        configuration_utf8={'config.ini':config.decode(),'surefire.properties':surefire.decode()},
        observation_utf8=raw.decode(),native_admission=False)
