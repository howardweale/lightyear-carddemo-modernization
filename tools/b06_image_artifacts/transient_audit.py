"""Read-only audit of every preserved bundle location; never fabricates copies."""
import hashlib,json,re
from collections import Counter
from pathlib import Path
from .tycho_runtime import path,properties

def audit(current,previous):
    current,previous=Path(current),Path(previous)
    raw=(current/'closure-observation.json').read_bytes();obs=json.loads(raw)
    old_raw=(previous/'closure-observation.json').read_bytes();old=json.loads(old_raw)
    previous_install=path(properties((previous/'runtime/work/configuration/config.ini').read_bytes())['osgi.install.area'])
    old_paths={path(b['location'],previous_install) for b in old['bundles'] if b['id']!=0}
    install=path(obs['install_area']);counts=Counter();rows=[]
    prefix='/application/org.idempiere.test/target/work/'
    for b in obs['bundles']:
        if b['id']==0: continue
        loc=path(b['location'],install)
        root=next((r for r in ('/root/.m2','/application','/tmp') if loc.startswith(r+'/')),'other')
        counts[root]+=1
        preserved=None
        if loc.startswith(prefix):preserved=(current/'runtime/work'/loc.removeprefix(prefix)).exists()
        manifest_evidence=[]
        if re.search(r'13\.0\.0\.20[0-9]{10}',loc):
            stable=re.sub(r'13\.0\.0\.20[0-9]{10}','13.0.0.TIMESTAMP',loc)
            for run,folder,paths in (('current',current,[loc]),('previous',previous,old_paths)):
                for candidate in paths:
                    if re.sub(r'13\.0\.0\.20[0-9]{10}','13.0.0.TIMESTAMP',candidate)!=stable:continue
                    manifest=folder/'runtime/work'/candidate.removeprefix(prefix)/'META-INF/MANIFEST.MF'
                    if manifest.is_file():
                        data=manifest.read_bytes()
                        versions=[line.split(': ',1)[1] for line in data.decode('utf-8').splitlines() if line.startswith('Bundle-Version: ')]
                        manifest_evidence.append(dict(run=run,path=candidate,sha256=hashlib.sha256(data).hexdigest(),bundle_versions=versions))
        rows.append(dict(bundle_id=b['id'],symbolic_name=b.get('symbolic_name'),location=loc,root=root,manifest_evidence=manifest_evidence,
          matches_tycho_source_path=bool(re.fullmatch(r'/tmp/tycho_wrapped_source[0-9]+\.jar',loc)),
          path_present_in_previous_observation=loc in old_paths,
          build_timestamp_in_path=bool(re.search(r'13\.0\.0\.20[0-9]{10}',loc)),
          retained_work_copy_exists=preserved,
          source_only_proof_available=False if root=='/tmp' else None,
          bytes_stable_across_runs='not established'))
    return dict(schema='b06-bundle-location-audit/1',observation_sha256=hashlib.sha256(raw).hexdigest(),
       previous_observation_sha256=hashlib.sha256(old_raw).hexdigest(),
       system_bundles_excluded=sum(b['id']==0 for b in obs['bundles']),
       bundle_count=len(rows),root_counts={r:counts[r] for r in ('/root/.m2','/application','/tmp','other')},
       changed_non_tmp_paths=[r['location'] for r in rows if r['root']!='/tmp' and not r['path_present_in_previous_observation']],
       bundles=rows,model_calls=0,docker_commands=0,native_admission=False,
       limitations=['No Linux filesystem is accessed. Survival is established only for retained target/work copies.',
       'Old observations lack source headers, versions, in-JVM copies and a complete runtime class catalogue.',
       'Stable paths do not prove stable bytes. Maven-built application bundles and the test folder need exact binding.',
       'Timestamped non-source folder bundles receive no path or hash exception.'])
