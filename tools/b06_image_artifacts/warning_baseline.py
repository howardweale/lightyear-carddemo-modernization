"""Closed, hash-bound intersection of prior log severity messages; no suppression."""
import collections,hashlib,json,re
SCHEMA='b06-warning-baseline/1'
RULES=['ISO UTC timestamp -> <timestamp>','Maven log UUID -> <run-id>',
 '14-digit OSGi build qualifier -> <qualifier>',
 'Tycho temporary source number -> <source-id>',
 '/application and /root/.m2 roots -> stable root markers; suffix retained']

def digest(raw):return hashlib.sha256(raw).hexdigest()

def normalize(line):
 line=re.sub(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b','<timestamp>',line)
 line=re.sub(r'\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b','<run-id>',line)
 line=re.sub(r'(?<=\.)20\d{12}\b','<qualifier>',line)
 line=re.sub(r'/tmp/tycho_wrapped_source[0-9]+\.jar','/tmp/tycho_wrapped_source<source-id>.jar',line)
 return line.replace('/application/','<application>/').replace('/root/.m2/','<maven>/')

def extract(raw):
 rows=[]
 for n,line in enumerate(raw.decode('utf-8',errors='strict').splitlines(),1):
  # MissingManifestStrategy = ERROR on INFO configuration lines is not log severity.
  if re.search(r'\[(?:WARN(?:ING)?|ERROR)\]|(?:^|\s)(?:WARN(?:ING)?|ERROR)(?::|\s)',line) and 'MissingManifestStrategy = ERROR' not in line:
   rows.append(dict(line=n,text=line,normalized=normalize(line)))
 return rows

def build(logs):
 if len(logs)<3:raise ValueError('three-prior-warning-logs-required')
 runs={name:dict(sha256=digest(raw),rows=extract(raw)) for name,raw in sorted(logs.items())}
 sets=[{r['normalized'] for r in v['rows']} for v in runs.values()]
 common=set.intersection(*sets)
 value=dict(schema=SCHEMA,normalization=RULES,accepted=sorted(common),runs=runs,
  unaccepted={name:sorted({r['normalized'] for r in v['rows']}-common) for name,v in runs.items()})
 value['content_sha256']=digest(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
 return value

def check(raw,baseline):
 body={k:v for k,v in baseline.items() if k!='content_sha256'}
 if baseline.get('schema')!=SCHEMA or baseline.get('normalization')!=RULES or digest(json.dumps(body,sort_keys=True,separators=(',',':')).encode())!=baseline.get('content_sha256'):raise ValueError('warning-baseline-binding')
 rows=extract(raw);new=sorted({r['normalized'] for r in rows}-set(baseline['accepted']))
 return dict(passed=not new,new=new,lines=len(rows),log_sha256=digest(raw),baseline_sha256=baseline['content_sha256'])
