"""Host-only synthetic alternatives matrix; refuses output reuse, never invokes Docker."""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path

def executable(home, name):
    return home/'bin'/(name+('.exe' if os.name=='nt' else ''))

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def inventory(folder, pattern='*'):
    files=[p for p in folder.rglob(pattern) if p.is_file()]
    rows=[{'path':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(files)]
    return {'files':len(rows),'bytes':sum(r['bytes'] for r in rows),'manifest_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),'manifest':rows}

def run_matrix(jdk, out, iterations=24, repeats=3):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    java=executable(jdk,'java');javac=executable(jdk,'javac');jlink=executable(jdk,'jlink')
    root=Path(__file__).resolve().parents[2]; source=root/'tools/b06_host_probe'
    def run(cmd,folder,name,timeout=180):
        started=time.perf_counter();p=subprocess.run(list(map(str,cmd)),cwd=folder,capture_output=True,timeout=timeout)
        (folder/(name+'.stdout')).write_bytes(p.stdout);(folder/(name+'.stderr')).write_bytes(p.stderr)
        return dict(exit_code=p.returncode,elapsed_seconds=time.perf_counter()-started,stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),stderr_sha256=hashlib.sha256(p.stderr).hexdigest())
    compile_result=run([javac,'--add-modules','jdk.jdi','-d',classes,source/'AlternativesTarget.java',source/'AlternativesCounter.java'],out,'compile')
    if compile_result['exit_code']:raise RuntimeError('compile-failed')
    jar=out/'fixture.jar';package=run([executable(jdk,'jar'),'--create','--file',jar,'-C',classes,'.'],out,'package')
    if package['exit_code']:raise RuntimeError('jar-failed')
    target=['AlternativesTarget',str(iterations),str(classes/'AlternativesTarget$Bytes.class')]
    train=out/'training';train.mkdir();archive=train/'fixture.jsa'
    training=run([java,'-Djava.lang.invoke.MethodHandle.TRACE_RESOLVE=true','-XX:ArchiveClassesAtExit='+str(archive),'-cp',jar,*target],train,'training')
    if training['exit_code'] or not archive.is_file():raise RuntimeError('training-failed')
    trace=train/'training.stdout';image=out/'jli-image'
    control=out/'jli-control-image'
    control_build=run([jlink,'--module-path',jdk/'jmods','--add-modules','java.base,jdk.jdwp.agent','--disable-plugin','generate-jli-classes','--output',control],out,'jlink-control')
    linked=run([jlink,'--module-path',jdk/'jmods','--add-modules','java.base,jdk.jdwp.agent','--generate-jli-classes=@'+str(trace),'--output',image],out,'jlink')
    if linked['exit_code'] or control_build['exit_code']:raise RuntimeError('jlink-failed')
    cells=[]
    variants=[('baseline',jdk,[]),('jli-control',control,[]),('jli',image,[]),('cds',jdk,['-XX:SharedArchiveFile='+str(archive),'-Xlog:cds=info']),
      ('internals',jdk,['-Djdk.invoke.MethodHandle.dumpMethodHandleInternals=true']),
      ('lookup',jdk,['-Djdk.invoke.MethodHandle.dumpClassFiles=true']),
      ('proxy',jdk,['-Djdk.invoke.LambdaMetafactory.dumpProxyClassFiles=true']),
      ('all-dumps',jdk,['-Djdk.invoke.MethodHandle.dumpMethodHandleInternals=true','-Djdk.invoke.MethodHandle.dumpClassFiles=true','-Djdk.invoke.LambdaMetafactory.dumpProxyClassFiles=true'])]
    for name,home,flags in variants:
        for repetition in range(repeats):
            folder=out/(name+'-'+str(repetition));folder.mkdir()
            wall=run([executable(home,'java'),*flags,'-cp',jar,*target],folder,'wall')
            dumps=inventory(folder,'*.class')
            # JDI is a separate run: overhead timings above have no debugger attached.
            counter=folder/'counter';counter.mkdir()
            options=' '.join(flags+['-cp','"'+str(jar)+'"'])
            main=' '.join([target[0],target[1],'"'+target[2]+'"'])
            counted=run([java,'--add-modules','jdk.jdi','-cp',classes,'AlternativesCounter',home,options,main],counter,'counts')
            raw=(counter/'counts.stdout').read_text()
            try:counts=json.loads(raw)
            except ValueError:counts={'complete':False,'parse_error':True}
            cells.append(dict(variant=name,repetition=repetition,wall=wall,counted=counted,counts=counts,dumps=dumps))
            (out/'progress.json').write_text(json.dumps(cells,indent=2))
            if wall['exit_code'] or not counts.get('complete') or counted['exit_code']:
                raise RuntimeError('incomplete-cell: '+name)
            if 'fixture-complete iterations='+str(iterations) not in (folder/'wall.stdout').read_text():
                raise RuntimeError('fixture-completion-missing')
    result=dict(schema='b06-alternatives-host/1',jdk_java_sha256=digest(java),jdk_release=(jdk/'release').read_text(),
        fixture_source_sha256=digest(source/'AlternativesTarget.java'),counter_source_sha256=digest(source/'AlternativesCounter.java'),fixture_jar_sha256=digest(jar),
        iterations=iterations,repetitions=repeats,compile=compile_result,training=training,jlink=linked,
        jli_control_build=control_build,jli_control_image=inventory(control),trace_sha256=digest(trace),trace_bytes=trace.stat().st_size,archive=inventory(train,'*.jsa'),jli_image=inventory(image),cells=cells,
        model_calls=0,native_runs=0,qualification_credit=False,measurement_credit=False)
    (out/'result.json').write_text(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--jdk',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run_matrix(a.jdk.resolve(),a.out.resolve())
