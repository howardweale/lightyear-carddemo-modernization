"""PROPOSED Docker-only no-database runtime probe. No host launcher or approval."""
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


def main():
    app,out=Path('/application'),Path('/results')
    if not (app/'org.idempiere.test/pom.xml').is_file() or any(out.iterdir()):raise ValueError('Fresh pinned container output required')
    started=time.monotonic();code=None
    (out/'agent').mkdir();(out/'loaded').mkdir();(out/'runtime').mkdir()
    try:
        subprocess.run(['javac','-d',str(out/'agent'),'/source/B06RuntimeCatalogAgent.java'],check=True,timeout=90)
        (out/'agent/MANIFEST.MF').write_text('Premain-Class: B06RuntimeCatalogAgent\n',encoding='ascii')
        subprocess.run(['jar','cfm',str(out/'agent.jar'),str(out/'agent/MANIFEST.MF'),'-C',str(out/'agent'),'.'],check=True,timeout=30)
        target=app/'org.idempiere.test/src/org/idempiere/test/B06RuntimeCatalogTest.java'
        if target.exists():raise ValueError('Probe source already exists')
        shutil.copyfile('/source/B06RuntimeCatalogTest.java',target)
        previous=app/'org.idempiere.test/target/surefire-reports'
        if previous.exists():shutil.move(str(previous),str(out/'previous-reports'))
        args=['mvn','-o','-B','verify','-DskipTests=false','-Dtest=B06RuntimeCatalogTest','-DfailIfNoTests=false',
              '-DmaterializeProduct=none','-DassembleRepository=none',
              '-Dp1=-Duser.timezone=UTC -Djunit.jupiter.execution.parallel.enabled=false -verbose:class '
              '-javaagent:/results/agent.jar=/results/loaded']
        (out/'command.json').write_text(json.dumps(args),encoding='utf-8')
        with (out/'maven.log').open('xb') as log:
            code=subprocess.run(args,cwd=app,stdout=log,stderr=subprocess.STDOUT,timeout=2400).returncode
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
    (out/'result.json').write_text(json.dumps({'loaded_classes':rows,**metadata,'passed':True},sort_keys=True),encoding='utf-8')


if __name__=='__main__':main()
