"""Prepare a fresh runtime-closure Git-byte snapshot; no Docker or authority calls."""
import ast,hashlib,importlib.util,subprocess
from pathlib import Path
from datetime import timedelta
from lightyear_calibration.contracts import canonical,seal,digest
from .controller import IMAGE,check,utc

def prepare(repository,commit,snapshot,public,start,tower_key,java_sha256,public_ref,*,plan_id='b06-runtime-closure-r5'):
    repository,snapshot,public=map(Path,(repository,snapshot,public))
    check(not snapshot.exists() and not public.exists(),'freeze-output-already-exists')
    def git(*args):return subprocess.check_output(['git','-C',str(repository),*args],timeout=60)
    check(git('rev-parse',commit).decode().strip()==commit,'full-source-commit-required')
    names=git('ls-tree','-r','--name-only',commit).decode().splitlines()
    selected={'tools/b06_image_artifacts/runtime_closure.py','tools/b06_image_artifacts/runtime_launch.py','tools/ms94_b06_qualification_worker.py',
              'src/lightyear_control_tower/client.py','src/lightyear_control_tower/b06.py'}
    # Static repository import closure, including relative imports and package
    # initializers. External distributions are environment bindings, not src/.
    files=set(names);seen=set();queue=list(selected)
    def include(module):
        path=module.replace('.','/')
        for prefix in ('','src/'):
            for candidate in (prefix+path+'.py',prefix+path+'/__init__.py'):
                if candidate in files and candidate not in selected:
                    selected.add(candidate);queue.append(candidate)
        parts=module.split('.')
        for count in range(1,len(parts)):
            for prefix in ('','src/'):
                candidate=prefix+'/'.join(parts[:count])+'/__init__.py'
                if candidate in files and candidate not in selected:
                    selected.add(candidate);queue.append(candidate)
    while queue:
        name=queue.pop()
        if name in seen:continue
        check(name in files,'source-closure-missing');seen.add(name)
        module=name.removeprefix('src/').removesuffix('.py').replace('/','.')
        package=module.removesuffix('.__init__') if module.endswith('.__init__') else module.rpartition('.')[0]
        tree=ast.parse(git('cat-file','blob',commit+':'+name))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                for alias in node.names:include(alias.name)
            elif isinstance(node,ast.ImportFrom):
                target=importlib.util.resolve_name('.'*node.level+(node.module or ''),package) if node.level else node.module
                if target:
                    include(target)
                    for alias in node.names:
                        if alias.name!='*':include(target+'.'+alias.name)
    check(selected <= files,'source-closure-missing')
    selected.update({'tools/B06RuntimeCatalogAgent.java','tools/B06RuntimeCatalogTest.java','tools/b06_image_artifacts/RuntimeClosureAgent.java'})
    snapshot.mkdir(parents=True);public.mkdir(parents=True)
    mapping={n:n for n in selected}
    mapping.update({n.removeprefix('src/'):n for n in selected if n.startswith('src/lightyear_evidence/')})
    for n in ('runtime_launch.py','runtime_closure.py','runtime_producer.py','runtime_worker.py','runtime_inventory.py','resolved_runtime.py','tycho_runtime.py','transient_sources.py','application_identity.py','runtime_capture.py','bundle_content.py','archive.py','RuntimeClosureAgent.java'):
        mapping[n]='tools/b06_image_artifacts/'+n
    for n in ('B06RuntimeCatalogAgent.java','B06RuntimeCatalogTest.java','ms94_b06_observed_worker.py'):mapping[n]='tools/'+n
    hashes={}
    for name,source in sorted(mapping.items()):
        raw=git('cat-file','blob',commit+':'+source);path=snapshot/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        hashes[name]=hashlib.sha256(raw).hexdigest()
    from tools.ms94_b06_observed_worker import maven_arguments
    at=utc(start);prefix=public.resolve().relative_to(repository.resolve()).as_posix()
    plan=seal(dict(schema='b06-runtime-closure-plan/1',id=plan_id,source_commit=commit,image=IMAGE,
        model_calls=0,native_pairs=0,database_containers=0,retries=0,network='none',maximum_runtime_seconds=2700,cleanup_reserve_seconds=600,
        files_sha256=hashes,snapshot_sha256=digest(hashes),public_files=mapping,public_ref=public_ref,public_plan_path=prefix+'/plan.json',
        tower_public_key_sha256=hashlib.sha256(Path(tower_key).read_bytes()).hexdigest(),java_sha256=java_sha256,
        measured_maven_arguments=maven_arguments(),window=dict(not_before_utc=at.isoformat(),latest_start_utc=(at+timedelta(minutes=5)).isoformat(),deadline_utc=(at+timedelta(hours=1)).isoformat()),
        run_authorized=False,requires_exact_tower_decision=True,review='operator review; not independent attestation'))
    (public/'plan.json').write_bytes(canonical(plan));return plan
