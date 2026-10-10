"""Explicit host-only generator for the tiny public JVM build-once example.

Never used by replay/tests; refuses overwriting existing generated evidence.
"""
import argparse, json, os, shutil, subprocess, tempfile
from pathlib import Path
from lightyear_evidence.build_once import canonical, descriptor, seal, replay_saved


def generate(root, jdk):
 root, jdk = Path(root).resolve(), Path(jdk).resolve()
 if (root/'contract.json').exists() or any((root/n).exists() for n in ('shared','one','two')):
  raise ValueError('fresh-output-required')
 exe = '.exe' if os.name == 'nt' else ''
 javac, java = jdk/('bin/javac'+exe), jdk/('bin/java'+exe)
 def run(argv, **kwargs):
  return subprocess.run(list(map(str,argv)),capture_output=True,timeout=20,check=True,**kwargs)
 version=run([java,'-version'])
 with tempfile.TemporaryDirectory() as temp:
  out=Path(temp)
  # Shared + Main are built ONCE, with the first consumer class.
  run([javac,'-g:none','-d',out,root/'source/Shared.java',root/'source/Main.java',root/'source/one/Probe.java'])
  (root/'shared').mkdir();(root/'one').mkdir();(root/'two').mkdir()
  for name in ('Shared.class','Main.class'):shutil.copyfile(out/name,root/'shared'/name)
  shutil.copyfile(out/'Probe.class',root/'one/Probe.class')
  # Only the second consumer class is compiled; the shared output is reused.
  run([javac,'-g:none','-d',root/'two',root/'source/two/Probe.java'])
 shared={p.relative_to(root).as_posix():descriptor(p.read_bytes()) for p in sorted((root/'shared').iterdir())}
 specs={}
 for name,expected in [('one',b'21'),('two',b'35')]:
  specs[name]=dict(directory=name,candidate_file='Probe.class',candidate=descriptor((root/name/'Probe.class').read_bytes()),
   argv=['java','-cp','shared'+os.pathsep+name,'Main'],returncode=0,
   stdout=descriptor(expected+os.linesep.encode()),stderr=descriptor(b''))
 contract=seal(dict(schema='build-once-consumer-contract/1',shared_files=shared,consumers=specs))
 (root/'contract.json').write_bytes(canonical(contract))
 for name,spec in specs.items():
  state=dict(manifest_sha256=contract['content_sha256'],variant=name,verified=True)
  (root/name/'before.json').write_bytes(canonical(state))
  before={n:descriptor((root/n).read_bytes()) for n in shared};candidate_before=descriptor((root/name/'Probe.class').read_bytes())
  result=run([java,*spec['argv'][1:]],cwd=root)
  after={n:descriptor((root/n).read_bytes()) for n in shared};candidate_after=descriptor((root/name/'Probe.class').read_bytes())
  for stream,raw in [('stdout',result.stdout),('stderr',result.stderr)]: (root/name/(stream+'.txt')).write_bytes(raw)
  record=seal(dict(manifest_sha256=contract['content_sha256'],consumer=name,argv=spec['argv'],returncode=result.returncode,
   shared_before=before,shared_after=after,candidate_before=candidate_before,candidate_after=candidate_after,
   stdout=descriptor(result.stdout),stderr=descriptor(result.stderr)))
  (root/name/'execution.json').write_bytes(canonical(record));(root/name/'after.json').write_bytes(canonical(state))
 replay=replay_saved(root,contract,contract['content_sha256'])
 generation=seal(dict(schema='public-jvm-fixture-generation/1',jdk_version=(version.stdout+version.stderr).decode(),
  java=descriptor(java.read_bytes()),javac=descriptor(javac.read_bytes()),shared_compilations=1,consumer_compilations=2,
  source_files={p.relative_to(root).as_posix():descriptor(p.read_bytes()) for p in sorted((root/'source').rglob('*.java'))},
  generator=descriptor(Path(__file__).read_bytes()),replay=replay,models=0,docker_commands=0,
  limitation='Public host JVM example only. Unsigned digest integrity; not production execution attestation or B06 qualification.'))
 (root/'generation.json').write_bytes(canonical(generation));print(json.dumps(generation))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--jdk',required=True);a=p.parse_args();generate(a.output,a.jdk)
