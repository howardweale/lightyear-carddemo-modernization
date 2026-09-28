"""Public application launcher. No private judge, reference oracle or capture reader."""
from pathlib import Path
import json
import shutil
import subprocess
import sys


def main():
    spec=json.load(sys.stdin);lane=spec['lane'];password=spec['password']
    assert lane in ('oracle','postgresql')
    assert not Path('/verifier').exists() and not Path('/output').exists()
    target=Path('/application/org.idempiere.test/src/org/idempiere/test/LightyearOperationsTest.java')
    shutil.copyfile('/candidate/LightyearOperationsTest.java',target)
    props=Path('/secrets/application.properties')
    port=1521 if lane=='oracle' else 5432;name='FREEPDB1' if lane=='oracle' else 'idempiere'
    connection=f'CConnection[name=Lightyear isolated,type={"Oracle" if lane=="oracle" else "PostgreSQL"},DBhost={lane},DBport={port},DBname={name},UID=adempiere,PWD={password}]'
    props.write_text('Connection='+connection+'\nTraceLevel=WARNING\nTraceFile=N\nToday=2026-09-26\n',encoding='ascii')
    props.chmod(0o600)
    args=['mvn','-o','-B','verify','-DskipTests=false','-Dtest=LightyearOperationsTest','-DfailIfNoTests=false',
          '-DmaterializeProduct=none','-DassembleRepository=none',
          '-Dp1=-DPropertyFile=/secrets/application.properties -Dlightyear.output=/results/journey.xml -Duser.timezone=UTC -Djunit.jupiter.execution.parallel.enabled=false']
    try:
        with Path('/results/maven.log').open('wb') as stream:
            code=subprocess.run(args,cwd='/application',stdout=stream,stderr=subprocess.STDOUT,
                                timeout=spec['timeout_seconds']).returncode
    except subprocess.TimeoutExpired:code=124
    finally:props.unlink(missing_ok=True)
    print(json.dumps({'exit_code':code}),flush=True)


if __name__=='__main__':main()
