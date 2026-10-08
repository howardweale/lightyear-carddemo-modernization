"""Prospective runtime-closure worker; requires its own Tower-authorized host launch."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

TARGETS = {'org/compiere/acct/Doc','org/compiere/acct/DocManager','org/compiere/model/PO','org/compiere/util/DB',
           'org/junit/platform/engine/support/hierarchical/NodeTestTask',
           'org/junit/platform/launcher/core/ExecutionListenerAdapter'}


def accept(root, returncode):
    root=Path(root)
    if returncode or (root/'loaded/FAILED').exists():raise ValueError('Runtime probe failed; preserve output')
    rows=[r.split('\t') for r in (root/'loaded/loaded.tsv').read_text(encoding='utf-8').splitlines()]
    if {r[0] for r in rows} != TARGETS:raise ValueError('Incomplete loaded target inventory')
    for name in TARGETS:
        selected=[r for r in rows if r[0]==name]
        if len(selected)!=1:raise ValueError('Ambiguous class loader identity')
        _,sha,origin,loader=selected[0]
        if origin=='unavailable' or hashlib.sha256((root/'loaded'/(sha+'.class')).read_bytes()).hexdigest()!=sha:
            raise ValueError('Loaded byte binding missing')
    reports=list((root/'runtime').rglob('TEST-*.xml'))
    cases=[c for p in reports for c in ET.parse(p).getroot().iter('testcase')]
    if len(cases)!=1 or cases[0].get('classname')!='org.idempiere.test.B06RuntimeCatalogTest' or list(cases[0].iter('failure')) or list(cases[0].iter('error')) or list(cases[0].iter('skipped')):
        raise ValueError('No-database test inventory differs')
    if not list((root/'runtime').rglob('config.ini')):raise ValueError('Resolved OSGi configuration missing')
    return rows


def launch_arguments():
    try:from tools.ms94_b06_observed_worker import maven_arguments
    except ImportError:from ms94_b06_observed_worker import maven_arguments
    measured=maven_arguments()
    args=[]
    for value in measured:
        if value=='-Dtest=LightyearOperationsTest':value='-Dtest=B06RuntimeCatalogTest'
        elif value.startswith('-Dp1='):
            parts=value[5:].split()
            # No DB settings or journey output and no suspended debugger in this
            # separate no-candidate process. Every difference is explicit.
            allowed=['-DPropertyFile=/secrets/application.properties','-Dlightyear.output=/results/journey.xml',
                '-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=*:5005']
            if not all(p in parts for p in allowed):raise ValueError('measured-launch-shape-changed')
            parts=[p for p in parts if p not in allowed]
            parts+=['-javaagent:/results/agent.jar=/results/loaded','-javaagent:/results/closure-agent.jar=/results/closure-observation.json']
            value='-Dp1='+' '.join(parts)
        args.append(value)
    return measured,args


def main():
    app,out=Path('/application'),Path('/results')
    if not (app/'org.idempiere.test/pom.xml').is_file() or any(out.iterdir()):raise ValueError('Fresh pinned container output required')
    started=time.monotonic();code=None
    (out/'agent').mkdir();(out/'loaded').mkdir();(out/'runtime').mkdir()
    try:
        subprocess.run(['javac','-d',str(out/'agent'),'/source/B06RuntimeCatalogAgent.java','/source/RuntimeClosureAgent.java'],check=True,timeout=90)
        (out/'agent/MANIFEST.MF').write_text('Premain-Class: B06RuntimeCatalogAgent\n',encoding='ascii')
        subprocess.run(['jar','cfm',str(out/'agent.jar'),str(out/'agent/MANIFEST.MF'),'-C',str(out/'agent'),'.'],check=True,timeout=30)
        (out/'agent/CLOSURE.MF').write_text('Premain-Class: RuntimeClosureAgent\n',encoding='ascii')
        subprocess.run(['jar','cfm',str(out/'closure-agent.jar'),str(out/'agent/CLOSURE.MF'),'-C',str(out/'agent'),'.'],check=True,timeout=30)
        target=app/'org.idempiere.test/src/org/idempiere/test/B06RuntimeCatalogTest.java'
        if target.exists():raise ValueError('Probe source already exists')
        shutil.copyfile('/source/B06RuntimeCatalogTest.java',target)
        previous=app/'org.idempiere.test/target/surefire-reports'
        if previous.exists():shutil.move(str(previous),str(out/'previous-reports'))
        measured,args=launch_arguments()
        (out/'measured-command.json').write_text(json.dumps(measured),encoding='utf-8')
        (out/'command.json').write_text(json.dumps(args),encoding='utf-8')
        with (out/'maven.log').open('xb') as log:
            code=subprocess.run(args,cwd=app,stdout=log,stderr=subprocess.STDOUT,timeout=1800).returncode
    finally:
        target=app/'org.idempiere.test/target'
        for name in ('work','surefire-reports','surefire','test-runtime','configuration'):
            path=target/name
            if path.exists():shutil.copytree(path,out/'runtime'/name)
        metadata={'exit_code':code,'elapsed_seconds':round(time.monotonic()-started,3),
                  'model_calls':0,'native_pairs':0,'database_containers':0,
                  'qualified':False,'clock_manipulation':False}
        (out/'attempt.json').write_text(json.dumps(metadata,sort_keys=True),encoding='utf-8')
    rows=accept(out,code)
    # Required even if Maven/test XML passed. A daemon failure must not disappear.
    observation=json.loads((out/'closure-observation.json').read_bytes())
    if observation.get('schema')!='b06-runtime-launch-observation/1':raise ValueError('closure-observation-required')
    from resolved_runtime import file_path,read
    config_path=Path(file_path(observation['configuration_url']))/'config.ini'
    config=config_path.read_bytes()
    # Preserve all candidates, but accept only one distinct effective property
    # file containing the required runtime classpath keys. No guessed fallback.
    candidates={}
    for path in (out/'runtime').rglob('*'):
        if path.is_file() and path.suffix=='.properties':
            raw=path.read_bytes()
            if b'ClassPathUrl.' in raw or b'classPathUrl.' in raw:
                read(config,raw);candidates[hashlib.sha256(raw).hexdigest()]=raw
    if len(candidates)!=1:raise ValueError('unambiguous-surefire-configuration-required')
    surefire=next(iter(candidates.values()))
    (out/'effective-config.ini').write_bytes(config);(out/'effective-surefire.properties').write_bytes(surefire)
    parsed=read(config,surefire)
    from runtime_inventory import measure
    inventory=measure(observation,out/'runtime-inventory',parsed['surefire_booter_classpath'])
    (out/'measured-inventory.json').write_text(json.dumps(inventory,sort_keys=True),encoding='utf-8')
    (out/'result.json').write_text(json.dumps({'loaded_classes':rows,**metadata,'passed':True},sort_keys=True),encoding='utf-8')


if __name__=='__main__':main()
