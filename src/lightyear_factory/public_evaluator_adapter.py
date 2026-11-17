"""Public-only build/feedback adapter; injected workers own execution/isolation.

No hidden evaluator, provider or graph interface. Raw observations stay outside
model requests. The controller independently validates the resulting envelope.
"""
import hashlib
import json
import re
import time
from tools.intcalc_reference_execution import strict, joined, comparison_policy
from lightyear_mainframe.records import load_copybook


class Refused(ValueError):
    pass


def require(ok,code):
    if not ok:raise Refused(code)


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def sha(raw):return hashlib.sha256(raw).hexdigest()
def hashed(value):return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None
def shape(x,keys,code):require(type(x) is dict and set(x)==set(keys.split()),code)
CHANNELS=('ACCTFILE','TRANSACT','stdout','stderr','exit')
CASE_EXECUTION_SECONDS=15
CASE_CLEANUP_SECONDS=5
OUTPUT_BYTES=8*1024*1024
PUBLIC_PHASE_SECONDS=600

PUBLIC_SUITE='6da875e28f95409290f77363c135ef98af395fe3448c9bf3e3da28b4cad370b2'
LAYOUTS={'ACCTFILE':('CVACT01Y.cpy','81a08bad15af5664326a6f0af3650f570821c4857ffdec3a6a39f91f07dca728'),
         'TRANSACT':('CVTRA05Y.cpy','d7bde0e78ff608497087b9909c889ed39e347269f964bda767b92b547fbb5fec')}
DIAGNOSTIC=re.compile(r'^(?:/source/)?Main\.java:(\d+):(\d+): (.+)$')
PATHS=re.compile(r'(?<![A-Za-z0-9_<])(?:[A-Za-z]:[\\/]|\\\\|/(?![/\s\'"<>;]))[^\s\'"<>|]*')
URIS=re.compile(r'\b[A-Za-z][A-Za-z0-9+.-]*://[^\s\'"<>]+')


def prefix(text,cap):
    lo,hi=0,len(text)
    while lo<hi:
        mid=(lo+hi+1)//2
        if len(canonical(text[:mid]))<=cap:lo=mid
        else:hi=mid-1
    return text[:lo]


def sanitize(message):
    # Not a generic slash prohibition: Java '/' and a/b remain ordinary text.
    message=URIS.sub('[path]',message)
    message=PATHS.sub('[path]',message)
    message=''.join(c if ord(c)>=32 or c in '\t\n\r' else '?' for c in message)
    return prefix(message,512)


def compiler_rows(stderr):
    require(type(stderr) is bytes,'compiler-response')
    truncated=len(stderr)>65536
    text=stderr[:65536].decode('utf-8','replace')
    rows=[];unknown=False
    for line in text.split('\n'):
        if not line or re.fullmatch(r'\d+ (?:error|errors|warning|warnings)\r?',line):continue
        match=DIAGNOSTIC.fullmatch(line.rstrip('\r'))
        if not match:
            unknown=True;continue  # Never forward source snippets or raw stderr.
        line_no,col=int(match[1]),int(match[2])
        if not (0<=line_no<=2147483647 and 0<=col<=2147483647):
            unknown=True;continue
        message=sanitize(match[3]);truncated|=message!=match[3]
        rows.append(dict(line=line_no,column=col,message=message))
    if unknown or not rows:
        rows.append(dict(line=0,column=0,message='compiler-diagnostic-unavailable'))
        truncated=True
    rows.sort(key=lambda x:(x['line'],x['column'],sha(x['message'].encode())))
    truncated|=len(rows)>4
    return rows[:4],truncated


def envelope(candidate,suite,kind,rows,truncated=False):
    require(hashed(candidate) and hashed(suite),'feedback-join')
    require(kind in ('COMPILE_FAILED','PUBLIC_DIVERGENCE'),'feedback-kind')
    key='diagnostics' if kind=='COMPILE_FAILED' else 'divergences'
    out=dict(schema='public-repair-feedback/1',candidate_sha256=candidate,
        public_suite_sha256=suite,kind=kind,divergences=[],diagnostics=[],truncated=truncated)
    cap=4 if key=='diagnostics' else 32
    for row in rows:
        if len(out[key])==cap:out['truncated']=True;break
        out[key].append(row)
        if len(canonical(out))>4096:
            out[key].pop();out['truncated']=True;break
    require(len(canonical(out))<=4096,'feedback-cap')
    return out


def lines(raw):
    if not raw:return []
    pieces=raw.split(b'\n')
    return pieces[:-1] if pieces[-1]==b'' else pieces


def tally(cases,layouts):
    """Rows are aggregate counts, never values, offsets, record ids or case ids."""
    totals={}
    def add(channel,field,a,b):
        require(type(a) is int and type(b) is int and 0<=a<=b,'public-count')
        row=totals.setdefault((channel,field),[0,0]);row[0]+=a;row[1]+=b
        require(row[1]<=9999999999,'public-count')
    matched=0
    for observation in cases:
        expected,actual,compare_files=observation[:3]
        limited=observation[3] if len(observation)==4 else False
        channels=CHANNELS if compare_files else CHANNELS[2:]
        equal=not limited and all(expected[k]==actual[k] for k in channels);matched+=int(equal)
        for channel in channels:
            left,right=expected[channel],actual[channel]
            if channel=='exit':add(channel,'',int(limited or left!=right),1);continue
            require(type(left) is bytes and type(right) is bytes,'public-channel')
            if channel in ('stdout','stderr'):
                a,b=lines(left),lines(right);n=max(len(a),len(b))
                different=sum(i>=len(a) or i>=len(b) or a[i]!=b[i] for i in range(n))
                if limited and not compare_files and channel=='stdout':
                    different=max(1,different);n=max(1,n)
                add(channel,'',different,n)
                continue
            layout=layouts[channel];width=layout.record_length
            require(width>0 and not layout.variable and not layout.overlays and len(left)%width==0,'public-layout')
            a=[left[i:i+width] for i in range(0,len(left),width)]
            b=[right[i:i+width] for i in range(0,len(right),width)];n=max(len(a),len(b))
            add(channel,'',int(limited or len(a)!=len(b) or len(right)%width!=0),1)
            groups={}
            for f in layout.fields:
                require(0<=f.offset and 0<f.length and f.offset+f.length<=width,'public-layout')
                groups.setdefault(f.path.split('.')[-1],[]).append((f.offset,f.length))
            for field,slices in sorted(groups.items()):
                different=sum(i>=len(a) or i>=len(b) or any(a[i][o:o+l]!=b[i][o:o+l] for o,l in slices) for i in range(n))
                add(channel,field,different,n)
    rows=[dict(channel=c,field=f,records_different=v[0],records_compared=v[1])
          for (c,f),v in sorted(totals.items(),key=lambda x:(CHANNELS.index(x[0][0]),x[0][1])) if v[0]>0]
    return matched,rows


def public_suite(raw,root):
    require(sha(raw)==PUBLIC_SUITE,'public-suite-hash')
    suite=strict(raw)
    require([c['id'] for c in suite['cases']]==['PC-'+str(n).zfill(2) for n in range(1,17)],'public-suite')
    cases=[]
    for c in suite['cases']:
        files=comparison_policy(c)
        expected={channel:joined(root,row) for channel,row in c['hand_outputs'].items()}
        expected['exit']=c['hand_exit']
        cases.append(dict(inputs={dd:joined(root,row) for dd,row in c['inputs'].items()},
            expected=expected,compare_output_files=files,timestamp=c['timestamp'],processing_date=c['processing_date']))
    return cases


class PublicAdapter:
    """The worker is trusted: Docker/tool/image/deadline/cleanup proof is mandatory.

    Caller supplies hash-verified, qualified PUBLIC suite and pinned layouts.
    A private/held-out suite must never be wired to this class. There is no hidden
    port. Public source provenance is an admission prerequisite, not inferred
    from a JSON label alone. This library is not an execution authorization.
    """
    def __init__(self,worker,suite_raw,suite_root,source_root,retain,clock=time.monotonic):
        self.cases=public_suite(suite_raw,suite_root)
        layouts={}
        for dd,(name,expected) in LAYOUTS.items():
            p=source_root/'spec/mainframe/copybooks'/name
            require(sha(p.read_bytes())==expected,'public-layout-hash')
            layouts[dd]=load_copybook(p)
        self.worker=worker;self.suite=PUBLIC_SUITE
        self.layouts=layouts;self.retain=retain;self.clock=clock

    def before(self,deadline):require(self.clock()<deadline,'deadline')

    def build(self,source,round_no,deadline):
        self.before(deadline)
        require(type(source) is str and len(source.encode('utf-8'))<=65536,'source-bound')
        require(not any(ord(x)<32 and x not in '\t\n\r' for x in source),'source-control')
        identity=sha(source.encode('utf-8'))
        result=self.worker.compile(source,round_no,deadline)
        self.before(deadline)
        shape(result,'phase exit_code stderr artifact_sha256 receipt_sha256 cleanup daemon_ok image_match tool_hash_match timed_out diagnostic_mode','compiler-response')
        require(result['phase']=='javac' and result['diagnostic_mode']=='javac-XDrawDiagnostics'
                and all(result[k] is True for k in ('cleanup','daemon_ok','image_match','tool_hash_match'))
                and result['timed_out'] is False and result['artifact_sha256']==identity
                and hashed(result['receipt_sha256']) and type(result['exit_code']) is int,'build-infrastructure')
        require(result['exit_code'] in (0,1),'build-tool-fault')
        diagnostic=None
        if result['exit_code']==1:
            rows,truncated=compiler_rows(result['stderr'])
            diagnostic=envelope(identity,self.suite,'COMPILE_FAILED',rows,truncated)
        return dict(status='BUILT' if result['exit_code']==0 else 'COMPILE_FAILED',
            artifact_sha256=identity,build_receipt_sha256=result['receipt_sha256'],cleanup=True,feedback=diagnostic)

    def evaluate_public(self,built,suite_sha256,deadline):
        self.before(deadline)
        require(suite_sha256==self.suite and built['status']=='BUILT','public-join')
        observations=[];receipt_rows=[]
        deadline=min(deadline,self.clock()+PUBLIC_PHASE_SECONDS)
        for n,case in enumerate(self.cases):
            shape(case,'inputs expected compare_output_files timestamp processing_date','public-case')
            require(type(case['compare_output_files']) is bool,'public-policy')
            wanted=set(CHANNELS if case['compare_output_files'] else CHANNELS[2:])
            require(type(case['expected']) is dict and set(case['expected'])==wanted,'public-expected')
            require(type(case['expected']['exit']) is int,'public-exit')
            # Only public INPUT bytes/time are given to the execution worker.
            now=self.clock()
            execution_end=min(now+CASE_EXECUTION_SECONDS,deadline-CASE_CLEANUP_SECONDS)
            require(execution_end>now,'deadline')
            case_end=min(deadline,execution_end+CASE_CLEANUP_SECONDS)
            limits=dict(execution_deadline=execution_end,cleanup_deadline=case_end,output_bytes=OUTPUT_BYTES)
            actual=self.worker.run_public(dict(built),dict(case['inputs']),case['timestamp'],case['processing_date'],case_end,limits)
            self.before(deadline)
            shape(actual,'ACCTFILE TRANSACT stdout stderr exit cleanup receipt_sha256 artifact_sha256 build_receipt_sha256 timed_out output_capped','public-response')
            require(actual['cleanup'] is True and hashed(actual['receipt_sha256'])
                    and actual['artifact_sha256']==built['artifact_sha256']
                    and actual['build_receipt_sha256']==built['build_receipt_sha256']
                    and type(actual['timed_out']) is bool and type(actual['output_capped']) is bool
                    and type(actual['exit']) is int and all(type(actual[k]) is bytes for k in CHANNELS[:-1]),'public-response')
            require(self.clock()<=case_end,'public-worker-deadline')
            # The worker must kill/reap at its limit and return only bounded prefixes.
            # An oversized wire payload violates the worker contract, not the candidate.
            require(all(len(actual[k])<=OUTPUT_BYTES for k in CHANNELS[:-1]),'public-worker-output-contract')
            limited=actual['timed_out'] or actual['output_capped']
            values={k:actual[k] for k in CHANNELS}
            observations.append((case['expected'],values,case['compare_output_files'],limited))
            receipt_rows.append(dict(index=n,worker_receipt=actual['receipt_sha256'],
                timed_out=actual['timed_out'],output_capped=actual['output_capped'],
                actual={k:sha(v) if type(v) is bytes else v for k,v in values.items()}))
        matches,rows=tally(observations,self.layouts)
        record=dict(schema='public-evaluation-receipt/1',suite_sha256=self.suite,
                    artifact_sha256=built['artifact_sha256'],build_receipt_sha256=built['build_receipt_sha256'],observations=receipt_rows)
        raw=canonical(record);receipt=self.retain(raw)
        require(receipt==sha(raw),'public-receipt-readback')
        self.before(deadline)
        return dict(suite_sha256=self.suite,artifact_sha256=built['artifact_sha256'],
            build_receipt_sha256=built['build_receipt_sha256'],match=matches,different=len(self.cases)-matches,
            total=len(self.cases),complete=True,cleanup=True,receipt_sha256=receipt,
            feedback=envelope(built['artifact_sha256'],self.suite,'PUBLIC_DIVERGENCE',rows))
