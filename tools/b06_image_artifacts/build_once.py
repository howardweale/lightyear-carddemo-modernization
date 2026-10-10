"""Build-once practice contracts and replay. No subprocesses or native admission.

The base identity is the exact shared content view, without manifest normalization.
Only the enumerated probe .class differs, and its bytes require separate evidence.
"""
import copy,hashlib,json,re
from pathlib import Path
from lightyear_evidence.build_once import descriptor, compare_package, verify_consumer_states
from .bundle_content import bundle_content_view
from .tycho_runtime import path,option,properties
from .application_identity import records as application_records,copies_at as application_copies
from .transient_sources import classify,copies_at,catalogue
from .runtime_capture import digest_file

LAYER='/opt/lightyear/b06-build-once'
TEST_ROOT='/application/org.idempiere.test'
TEST_ENTRY='target/classes/org/idempiere/test/B06RuntimeCatalogTest.class'
TEST_CLASS='org/idempiere/test/B06RuntimeCatalogTest'
CLASS_PATH=TEST_ROOT+'/'+TEST_ENTRY


def require(ok,message):
 if not ok:raise ValueError(message)

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def seal(value):return dict(value,content_sha256=digest(value))
def verify(value):require(value.get('content_sha256')==digest({k:v for k,v in value.items() if k!='content_sha256'}),'build-once-manifest-hash')


def application_maps(out):
 out=Path(out);obs=json.loads((out/'worker-observation.json').read_bytes())
 # Existing proof checks still bind agent observation, capture fidelity and archives.
 application_records(obs,application_copies(obs,out))
 result={}
 for b in obs['bundles']:
  c=b.get('application_copy')
  if not c:continue
  origin=path(b['location'],path(obs['install_area']))
  kind='jar' if c['kind']=='jar' else 'folder-archive'
  entries=bundle_content_view(out/'runtime-application'/f"{b['id']}.jar",kind=kind)['entries']
  key=b['symbolic_name'];require(key not in result,'duplicate-layer-bundle')
  result[key]=dict(path=origin,version=b['version'],kind=kind,entries=entries,
                  jar_sha256=c['sha256'] if kind=='jar' else None)
 return result

def compare_applications(base,current,expected_class):
 require(set(base)==set(current),'layer-bundle-set')
 for name,left in base.items():
  right=current[name];replacements={}
  if name=='org.idempiere.test':
   require(left['path']==right['path']==TEST_ROOT and left['kind']==right['kind']=='folder-archive','layer-test-origin')
   replacements={TEST_ENTRY:dict(kind='file',**expected_class)}
  compare_package(left,right,replacements,missing='per-run-class-missing',changed='per-run-captured-class-bytes',different='non-candidate-layer-content-differs:'+name)
 return True

def direct_command(fork):
 require(isinstance(fork,list) and fork and fork[0]=='/opt/java/openjdk/bin/java','direct-java-required')
 require(fork.count('-jar')==1 and option(fork,'-testproperties')==TEST_ROOT+'/target/surefire.properties','direct-fork-shape')
 require(option(fork,'-install')==TEST_ROOT+'/target/work' and option(fork,'-configuration')==TEST_ROOT+'/target/work/configuration' and option(fork,'-data')==TEST_ROOT+'/target/work/data','direct-fork-paths')
 # Exact captured JVM argv plus two declared additions; no shell/build command.
 require(not any(x.startswith(('-Djava.io.tmpdir=','-javaagent:/results/per-run-agent.jar')) for x in fork),'unexpected-per-run-agent')
 args=list(fork);args[1:1]=['-Djava.io.tmpdir=/results/java-tmp','-javaagent:/results/per-run-agent.jar=/results/per-run-class.json']
 return args

def runtime_manifest(out):
 out=Path(out);obs=json.loads((out/'worker-observation.json').read_bytes());inv=json.loads((out/'measured-inventory.json').read_bytes())
 sources=classify(obs,copies_at(obs,out),catalogue((out/'runtime-catalogue.tsv').read_bytes()))
 apps=application_maps(out);require(len(apps)==44 and len(sources)==102,'build-once-census')
 fork=json.loads((out/'fork-command.json').read_bytes());args=direct_command(fork)
 artifacts={r['path']:dict(sha256=r['sha256'],bytes=r['bytes']) for r in inv['artifacts'] if r.get('kind')!='captured-application-bundle'}
 return dict(schema='b06-built-runtime-manifest/1',base_applications=apps,artifacts=artifacts,
  source_files={r['original_path']:dict(symbolic_name=r['symbolic_name'],version=r['version'],**{k:r['preserved_copy'][k] for k in ('sha256','bytes')}) for r in sources},
  source_copies={r['original_path']:r['preserved_copy']['path'] for r in sources},
  fork=fork,consumer_argv=args,per_run_class=dict(name=TEST_CLASS,path=CLASS_PATH,entry=TEST_ENTRY),
  config_path=option(fork,'-configuration'),data_path=option(fork,'-data'),testproperties_path=option(fork,'-testproperties'),
  historical_content_required=False,native_admission=False,model_calls=0)

def verify_live(manifest,expected_class,*,resolve=Path):
 """Read-only pre/post checks inside consumer; filesystem map injectable for tests."""
 verify(manifest)
 for name,row in manifest['base_applications'].items():
  original=resolve(row['path']);kind='jar' if row['kind']=='jar' else 'folder'
  entries=bundle_content_view(original,kind=kind)['entries'];base=copy.deepcopy(row)
  current=dict(base,entries=entries,jar_sha256=digest_file(original) if kind=='jar' else None)
  compare_applications({name:base},{name:current},expected_class)
 for p,row in manifest['artifacts'].items():
  f=resolve(p);require(f.is_file() and not f.is_symlink() and f.stat().st_size==row['bytes'] and digest_file(f)==row['sha256'],'layer-artifact-changed:'+p)
 for p,row in manifest['source_files'].items():
  require(re.fullmatch(r'/tmp/tycho_wrapped_source[0-9]+\.jar',p) is not None,'layer-source-path')
  f=resolve(p);require(f.is_file() and not f.is_symlink() and f.stat().st_size==row['bytes'] and digest_file(f)==row['sha256'],'layer-source-changed:'+p)
 for p,row in manifest['sealed_files'].items():
  f=resolve(p);require(f.is_file() and not f.is_symlink() and descriptor(f.read_bytes())==row,'sealed-runtime-file-changed:'+p)
 return True

def verify_consumer(manifest,out,variant):
 """Independent read-only binding of captured outputs to the built runtime."""
 verify(manifest);out=Path(out);require(variant in ('1','2'),'practice-variant')
 expected=manifest['variants'][variant]['class'];obs=json.loads((out/'worker-observation.json').read_bytes())
 require(obs['fork_command']==manifest['consumer_argv'],'consumer-command-differs')
 require(digest_file(out/'effective-config.ini')==manifest['base_config_sha256'],'consumer-config-changed')
 require(descriptor((out/'effective-surefire.properties').read_bytes())==manifest['sealed_files'][manifest['testproperties_path']],'consumer-properties-changed')
 dev=obs.get('dev_properties');require(dev and descriptor(dev['utf8'].encode('iso-8859-1'))==manifest['sealed_files'].get(dev['path']),'consumer-dev-properties-changed')
 compare_applications(manifest['base_applications'],application_maps(out),expected)
 inventory=json.loads((out/'measured-inventory.json').read_bytes())
 current={r['path']:dict(sha256=r['sha256'],bytes=r['bytes']) for r in inventory['artifacts'] if r.get('kind')!='captured-application-bundle'}
 require(current==manifest['artifacts'],'consumer-runtime-artifacts-differ')
 sources=classify(obs,copies_at(obs,out),catalogue((out/'runtime-catalogue.tsv').read_bytes()))
 current_sources={r['original_path']:dict(symbolic_name=r['symbolic_name'],version=r['version'],**{k:r['preserved_copy'][k] for k in ('sha256','bytes')}) for r in sources}
 require(current_sources==manifest['source_files'],'consumer-source-files-differ')
 record=json.loads((out/'per-run-class.json').read_bytes())
 require(record.get('schema')=='b06-practice-class-observation/1' and record.get('name')==TEST_CLASS and record.get('origin')=='file:'+TEST_ROOT+'/target/classes/' and record.get('loader') not in (None,'','bootstrap'),'practice-class-origin')
 require({k:record.get(k) for k in ('bytes','sha256')}==expected,'practice-observed-class-bytes')
 require(not (out/'per-run-class-error.json').exists(),'practice-class-observer-error')
 require(any(r['name']==TEST_CLASS and r['origin']==record['origin'] for r in catalogue((out/'runtime-catalogue.tsv').read_bytes())),'practice-class-catalogue-binding')
 verify_consumer_states([json.loads((out/filename).read_bytes()) for filename in ('before.json','after.json')],manifest['content_sha256'],variant)
 return dict(passed=True,variant=variant,manifest_sha256=manifest['content_sha256'],non_candidate_bundles=44,per_run_class=expected,
             native_admission=False,claim='Zero-candidate practice observation; production JDI admission remains separate')
