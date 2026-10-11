"""Host-only 192 MiB production serializer peak test; no native application."""
import argparse,base64,hashlib,json,os,subprocess
from pathlib import Path

def run(jdk,out,observer_source=None):
    if out.exists():raise ValueError('transient-output-exists')
    root=Path(__file__).resolve().parents[2]
    observer_source=observer_source or root/'factory/idempiere/b06-observer/PostingObserver.java'
    source=root/'tools/b06_host_probe/TransientPeakHarness.java';out.mkdir(parents=True);classes=out/'classes';classes.mkdir()
    # Pin a read-only input copy so concurrent editing cannot change compilation provenance.
    observer_bytes=observer_source.read_bytes();observer_snapshot=out/'PostingObserver.java';observer_snapshot.write_bytes(observer_bytes)
    suffix='.exe' if os.name=='nt' else ''
    compiled=subprocess.run([str(jdk/'bin'/('javac'+suffix)),'--add-modules','jdk.jdi,jdk.management','-d',str(classes),str(observer_snapshot),str(source)],capture_output=True,timeout=120)
    (out/'compile.stdout').write_bytes(compiled.stdout);(out/'compile.stderr').write_bytes(compiled.stderr)
    if compiled.returncode:raise ValueError('transient-compile-failed')
    target=out/'serialized.json'
    process=subprocess.run([str(jdk/'bin'/('java'+suffix)),'--add-modules','jdk.jdi,jdk.management','-Xms192m','-Xmx192m','-cp',str(classes),'TransientPeakHarness',str(target)],capture_output=True,timeout=120)
    (out/'host.stdout').write_bytes(process.stdout);(out/'host.stderr').write_bytes(process.stderr)
    if process.returncode:raise ValueError('transient-host-failed')
    result=json.loads(process.stdout)
    definition=bytes(i%251 for i in range(1024*1024));nodes={str(i):{'type':'public.synthetic.Node','index':i,'next':(i+1)%4096} for i in range(4096)}
    expected={'definition_input_base64':base64.b64encode(definition).decode(),'class_data_graph':{'root':'0','nodes':nodes}}
    reference=json.dumps(expected,separators=(',',':')).encode();actual=target.read_bytes()
    if actual!=reference or result['sha256']!=hashlib.sha256(reference).hexdigest():raise ValueError('transient-reference-mismatch')
    if result['heap_before_bytes']/result['heap_max_bytes']<.85 or result['oom']:raise ValueError('transient-load-insufficient')
    result.update(observer_source_sha256=hashlib.sha256(observer_bytes).hexdigest(),harness_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),independent_reference_equal=True,native_runs=0,model_calls=0,qualification_credit=False,measurement_credit=False,
        limitation='Peak sampled at output-buffer writes; thread allocation upper bound separately retained; input and ballast are resident before timing.')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--jdk',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--observer-source',type=Path)
    a=p.parse_args();print(json.dumps(run(a.jdk.resolve(),a.out.resolve(),a.observer_source),indent=2))
