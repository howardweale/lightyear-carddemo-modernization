"""Build once, or consume a sealed layer. Invoked only by approved practice runner."""
import json,shutil,subprocess,time,traceback
from pathlib import Path
from . import build_once as contract
from . import runtime_worker
from .runtime_capture import atomic_json,digest_file

OUT=Path('/results');LAYER=Path(contract.LAYER)

def copy_new(source,dest):
 dest.parent.mkdir(parents=True,exist_ok=True)
 with Path(source).open('rb') as src,dest.open('xb') as dst:shutil.copyfileobj(src,dst,65536)

def restore_sources(manifest):
 for original,copy in manifest['source_copies'].items():
  p=Path(original);row=manifest['source_files'][original]
  contract.require(not p.exists(),'restored-source-already-exists')
  copy_new(Path(copy),p)
  contract.require(contract.descriptor(p.read_bytes())=={k:row[k] for k in ('bytes','sha256')},'restored-source-hash')

def build():
 contract.require(not LAYER.exists(),'fresh-build-layer-required')
 runtime_worker.run()
 manifest=contract.runtime_manifest(OUT);restore_sources(manifest)
 LAYER.mkdir(parents=True)
 for name in ('agent.jar','closure-agent.jar'):copy_new(OUT/name,LAYER/name)
 # The consumer never compiles. Build the independent byte recorder here.
 agent=LAYER/'agent-classes';agent.mkdir()
 javac='/opt/java/openjdk/bin/javac';jar='/opt/java/openjdk/bin/jar'
 subprocess.run([javac,'-d',str(agent),'/source/tools/b06_image_artifacts/B06PerRunClassAgent.java'],check=True,timeout=90)
 (LAYER/'AGENT.MF').write_text('Premain-Class: B06PerRunClassAgent\n',encoding='ascii')
 subprocess.run([jar,'cfm',str(LAYER/'per-run-agent.jar'),str(LAYER/'AGENT.MF'),'-C',str(agent),'.'],check=True,timeout=30)
 variants={};source=Path('/source/B06RuntimeCatalogTest.java').read_text(encoding='utf-8')
 needle='public class B06RuntimeCatalogTest {'
 contract.require(source.count(needle)==1,'variant-source-shape')
 cp=':'.join(sorted(p for p in manifest['artifacts'] if p.endswith('.jar')))
 for variant in ('1','2'):
  dest=LAYER/'variants'/variant;dest.mkdir(parents=True)
  if variant=='1':
   rawsource=source;copy_new(Path(contract.CLASS_PATH),dest/'probe.class');command=None
  else:
   rawsource=source.replace(needle,needle+'\n    public static final String B06_BUILD_ONCE_VARIANT="consumer-2";')
   src=dest/'B06RuntimeCatalogTest.java';src.write_text(rawsource,encoding='utf-8');classes=dest/'classes';classes.mkdir()
   command=[javac,'-cp',cp,'-d',str(classes),str(src)]
   subprocess.run(command,check=True,timeout=90)
   outputs=list(classes.rglob('*.class'))
   contract.require(len(outputs)==1 and outputs[0].relative_to(classes).as_posix()==contract.TEST_CLASS+'.class','variant-output-set')
   copy_new(outputs[0],dest/'probe.class')
  variants[variant]=dict(source_sha256=contract.descriptor(rawsource.encode())['sha256'],class_path=str(dest/'probe.class'),
    **{'class':contract.descriptor((dest/'probe.class').read_bytes())},compile_command=command)
 contract.require(variants['1']['class']!=variants['2']['class'],'variants-must-differ')
 manifest['variants']=variants
 manifest['compiler']=dict(path=javac,**contract.descriptor(Path(javac).read_bytes()),classpath=cp.split(':'))
 manifest['base_config_sha256']=digest_file(Path(manifest['config_path'])/'config.ini')
 # Preserve a seed, not mutable output from a preceding consumer.
 shutil.copytree(manifest['config_path'],LAYER/'configuration-seed',symlinks=False)
 manifest['sealed_files']={}
 for p in LAYER.rglob('*'):
  if p.is_file():manifest['sealed_files'][p.as_posix()]=contract.descriptor(p.read_bytes())
 for p in (Path(manifest['testproperties_path']),Path(contract.TEST_ROOT+'/target/work/dev.properties')):
  manifest['sealed_files'][p.as_posix()]=contract.descriptor(p.read_bytes())
 manifest=contract.seal(manifest)
 atomic_json(LAYER/'manifest.json',manifest);atomic_json(OUT/'layer-manifest.json',manifest)
 for variant in ('1','2'):copy_new(Path(variants[variant]['class_path']),OUT/('variant-'+variant+'.class'))
 shutil.copytree(LAYER/'configuration-seed',OUT/'configuration-seed')
 contract.verify_live(manifest,variants['1']['class'])


def consume(variant):
 manifest=json.loads((LAYER/'manifest.json').read_bytes());contract.verify(manifest)
 contract.require(variant in ('1','2') and not any(OUT.iterdir()),'fresh-consumer-output')
 expected=manifest['variants'][variant]['class'];contract.verify_live(manifest,expected)
 state=dict(manifest_sha256=manifest['content_sha256'],variant=variant,verified=True)
 atomic_json(OUT/'before.json',state)
 for name in ('agent.jar','closure-agent.jar','per-run-agent.jar'):copy_new(LAYER/name,OUT/name)
 for name in ('loaded','runtime','java-tmp'):(OUT/name).mkdir()
 args=manifest['consumer_argv'];atomic_json(OUT/'command.json',args)
 measured,_=runtime_worker.launch_arguments();atomic_json(OUT/'measured-command.json',measured)
 start=time.monotonic();code=None
 try:
  with (OUT/'runtime.log').open('xb') as log:
   code=subprocess.run(args,cwd='/application',stdout=log,stderr=subprocess.STDOUT,timeout=540).returncode
 finally:
  from .tycho_runtime import capture_properties
  target=Path(contract.TEST_ROOT)/'target'
  for name in ('work','surefire-reports'):
   if (target/name).exists():shutil.copytree(target/name,OUT/'runtime'/name)
  capture_properties(target,OUT/'runtime')
  atomic_json(OUT/'attempt.json',dict(exit_code=code,elapsed_seconds=time.monotonic()-start,model_calls=0,native_pairs=0,database_containers=0,qualified=False,clock_manipulation=False))
 runtime_worker.process_outputs(OUT,code)
 contract.require(digest_file(OUT/'effective-config.ini')==manifest['base_config_sha256'],'consumer-config-changed')
 contract.verify_live(manifest,expected);atomic_json(OUT/'after.json',state)
 atomic_json(OUT/'binding.json',contract.verify_consumer(manifest,OUT,variant))


def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('action',choices=['build','consume']);p.add_argument('--variant',choices=['1','2']);a=p.parse_args()
 try:
  if a.action=='build':build()
  else:consume(a.variant)
 except BaseException as e:
  atomic_json(OUT/'build-once-error.json',dict(stage=a.action,exception=type(e).__name__,message=str(e),traceback=traceback.format_exc()))
  raise
if __name__=='__main__':main()
