"""Operator-run VM export of one authenticated R3 run. No network, signing or execution."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import socket
import zipfile

REPORT='97116694c110465c639180a79b3ba3512d44566a49b529d8f24ce7713e69e2ef'
KEY='f65a408bc46828860fd140518486734879fa9c35aacf2366000e0b1477ae3864'
FILES=1889  # Signed report.files entries; report.json itself is the 1,890th file.
PACKAGE='tsql-r9-evidence-2026-10-21.zip'
MAX_FILE=64*1024*1024
MAX_TOTAL=2*1024*1024*1024
SECRET_KEY=re.compile(r'(?i)(?:^|[_-])(?:password|passwd|pwd|secret|token|credential|credentials|private[_-]?key|access[_-]?key|api[_-]?key|client[_-]?secret|authorization)(?:$|[_-])')
SECRET_TEXT=re.compile(r'''(?ix)-----BEGIN[^\r\n]{0,48}PRIVATE\sKEY-----|(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,}|ya29\.[A-Za-z0-9_-]+)|\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_.=-]{8,}|://[^\s/:@]+:[^\s/@]+@|(?:password|passwd|pwd|secret|credential|api_key|token|client_secret|access_token|refresh_token)["']?\s*[=:]\s*["']?[^\s,;]+''')
IDENTIFIER_KEY=re.compile(r'(?i)^(?:host|hostname|server|project|project_id|projectid|gcp_project|google_cloud_project)$')
HOST=re.compile(r'(?i)\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|internal|local|cloud|dev)\b|\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate-json-key')
        result[k]=v
    return result


def decode(raw):
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite-json')))


def relative(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or '\0' in name:
        raise ValueError('unsafe-manifest-path')
    path=PurePosixPath(name)
    if path.is_absolute() or any(p in ('','..','.') for p in name.split('/')):
        raise ValueError('unsafe-manifest-path')
    if re.search(r'(?i)(?:^|/)(?:\.ssh|\.aws|\.config|credentials?|id_rsa|id_ed25519)(?:/|$)|private[-_]?key|recorder[-_]?key',name):
        raise ValueError('credential-filename')
    return path


def identity(info):
    return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_nlink


def read_file(root,name):
    relative(name);path=root/name
    for part in (path,*path.parents):
        if part==root:break
        if part.is_symlink():raise ValueError('linked-evidence-path')
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>MAX_FILE:
        raise ValueError('nonregular-or-large-evidence')
    with path.open('rb') as stream:
        if identity(os.fstat(stream.fileno()))!=identity(info):raise ValueError('evidence-changed')
        raw=stream.read(MAX_FILE+1)
        if identity(os.fstat(stream.fileno()))!=identity(info):raise ValueError('evidence-changed')
    if len(raw)!=info.st_size or identity(path.stat())!=identity(info):raise ValueError('evidence-changed')
    return raw


def envelope(value,public):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    body={k:v for k,v in value.items() if k not in ('signature','content_sha256')}
    raw=canonical(body)
    if sha(raw)!=value['content_sha256']:raise ValueError('report-content-hash')
    Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(value['signature'],validate=True),raw)
    return body


def scan(value,path,identifiers,depth=0,budget=None):
    """Fail closed on credential fields/markers; inspect bounded encoded strings too."""
    budget=budget if budget is not None else [0]
    budget[0]+=1
    if depth>128 or budget[0]>2000000:raise ValueError('secret-scan-limit')
    if isinstance(value,dict):
        for key,child in value.items():
            # TDS 'token' is a numeric protocol discriminator, not a credential.
            numeric_tds=key=='token' and type(child) is int and 0<=child<=255
            normalized_key=re.sub(r'([a-z0-9])([A-Z])',r'\1_\2',key)
            if SECRET_KEY.search(normalized_key) and child not in (None,'',False) and not numeric_tds:
                raise ValueError('credential-field:'+path)
            if IDENTIFIER_KEY.fullmatch(key) and isinstance(child,str) and child:
                identifiers.add((path,key,child))
            scan(key,path,identifiers,depth+1,budget);scan(child,path,identifiers,depth+1,budget)
    elif isinstance(value,list):
        for child in value:scan(child,path,identifiers,depth+1,budget)
    elif isinstance(value,str):
        if SECRET_TEXT.search(value):raise ValueError('secret-marker:'+path)
        if value.lstrip().startswith(('{','[')):
            try:nested=decode(value)
            except ValueError:nested=None
            if nested is not None:scan(nested,path,identifiers,depth+1,budget)
        for host in HOST.findall(value):identifiers.add((path,'hostname-or-address',host))
        for project in re.findall(r'(?i)(?:projects/|(?:gcr\.io|pkg\.dev)/)([a-z][a-z0-9-]{4,61}[a-z0-9])',value):
            identifiers.add((path,'project-id',project))
        # Decode only complete bounded scalar encodings; limits refuse, never truncate.
        if 32<=len(value)<=MAX_FILE and len(value)%4==0 and re.fullmatch('[A-Za-z0-9+/]+={0,2}',value):
            try:decoded=base64.b64decode(value,validate=True).decode('utf-8')
            except (ValueError,UnicodeError):decoded=None
            if decoded and decoded!=value:scan(decoded,path,identifiers,depth+1,budget)
        if len(value)>=32 and len(value)%2==0 and re.fullmatch('[a-fA-F0-9]+',value):
            try:decoded=bytes.fromhex(value).decode('utf-8')
            except UnicodeError:decoded=None
            if decoded and decoded!=value:scan(decoded,path,identifiers,depth+1,budget)


def locate(search):
    if search.is_symlink():raise ValueError('linked-search-root')
    search=search.resolve(strict=True);matches=[];count=0
    for parent,dirs,files in os.walk(search,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in ('.ssh','.aws','.config','.git') and not (Path(parent)/d).is_symlink())
        count+=len(files)+len(dirs)
        if count>100000:raise ValueError('search-limit-use-narrower-root')
        if 'report.json' not in files:continue
        root=Path(parent)
        try:
            value=decode(read_file(root,'report.json'))
        except (ValueError,OSError):continue
        if isinstance(value,dict) and value.get('content_sha256')==REPORT:matches.append(root)
    if len(matches)!=1:raise ValueError('expected-exactly-one-revision9-run-found-'+str(len(matches)))
    return matches[0]


def inspect(root):
    root=root.resolve(strict=True)
    report_raw=read_file(root,'report.json');report=decode(report_raw)
    public=read_file(root,'evidence-public-key.bin')
    if sha(public)!=KEY or len(public)!=32 or report.get('content_sha256')!=REPORT:
        raise ValueError('wrong-revision9-report-or-key')
    body=envelope(report,public)
    if body['schema']!='tsql-native-run-report/1' or body['model_calls']!=0 or not body['qualification_passed']:
        raise ValueError('revision9-report-contract')
    files=body['files']
    if len(files)!=FILES or 'report.json' in files:raise ValueError('expected-1889-manifest-files')
    allowed=set(files)|{'report.json'}
    for name in allowed:relative(name)
    actual=set()
    for parent,dirs,names in os.walk(root,followlinks=False):
        for name in dirs:
            p=Path(parent)/name
            if p.is_symlink():raise ValueError('linked-evidence-directory')
            rel=p.relative_to(root).as_posix()
            if not any(f.startswith(rel+'/') for f in allowed):raise ValueError('unmanifested-directory')
        for name in names:actual.add((Path(parent)/name).relative_to(root).as_posix())
    if actual!=allowed:raise ValueError('run-file-closure')
    identifiers=set();inventory={};total=0
    for name in sorted(allowed):
        raw=read_file(root,name);total+=len(raw)
        if total>MAX_TOTAL:raise ValueError('run-size-limit')
        if name!='report.json' and sha(raw)!=files[name]:raise ValueError('signed-file-hash-mismatch:'+name)
        if name.endswith('public-key.bin'):
            if len(raw)!=32:raise ValueError('unexpected-public-key-size')
            signed_name=str(PurePosixPath(name).parent/'report.json')
            envelope(decode(read_file(root,signed_name)),raw)
        elif name.endswith('.json'):scan(decode(raw),name,identifiers)
        else:
            try:text=raw.decode('utf-8')
            except UnicodeError:raise ValueError('unreviewed-binary-file:'+name) from None
            scan(text,name,identifiers)
        inventory[name]=dict(bytes=len(raw),sha256=sha(raw))
    plan=envelope(decode(read_file(root,'plan.json')),public)
    records=body['records']
    if plan.get('comparison_revision')!=9 or len(records)!=108 or len({r['index'] for r in records})!=108:
        raise ValueError('revision9-108-pair-count')
    for record in records:
        if record['status']=='failed':raise ValueError('failed-native-pair')
        pair=f'pair-{record["index"]:03d}-{record["id"]}-{record["variant"]}-{record["repeat"]}'
        value=decode(read_file(root,pair+'/manifest.json'))
        if value['content_sha256']!=record['manifest_sha256']:raise ValueError('pair-manifest-binding')
        envelope(value,public)
    required=('coverage-control-evidence/','pair-')
    if any(not any(p.startswith(prefix) for p in files) for prefix in required):raise ValueError('missing-native-evidence')
    review=[dict(path=p,kind=k,value=v) for p,k,v in sorted(identifiers)]
    return dict(schema='tsql-r9-export/1',report_content_sha256=REPORT,report_file_sha256=sha(report_raw),
        public_key_sha256=KEY,signed_file_count=FILES,packaged_file_count=len(inventory),native_pairs=108,
        files=inventory,total_bytes=total,identifiers=review,identifiers_sha256=sha(canonical(review)))


def package(root,out,reviewed):
    current=inspect(root)
    previous=decode((out/'inspection.json').read_bytes())
    if current!=previous or reviewed!=current['identifiers_sha256']:
        raise ValueError('reviewed-inspection-changed')
    destination=out/PACKAGE
    # Exclusive creation: never overwrite an earlier reviewed package.
    try:
        with destination.open('xb') as stream,zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as archive:
            for name,row in current['files'].items():
                raw=read_file(root,name)
                if len(raw)!=row['bytes'] or sha(raw)!=row['sha256']:raise ValueError('evidence-changed-during-package')
                info=zipfile.ZipInfo('revision-9/'+name,date_time=(2026,10,21,0,0,0))
                info.external_attr=0o100444<<16;info.create_system=3
                archive.writestr(info,raw)
    except FileExistsError:raise
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    # Verify the actual archive member set and all bytes before issuing a manifest.
    with zipfile.ZipFile(destination) as archive:
        if set(archive.namelist())!={'revision-9/'+n for n in current['files']} or len(archive.infolist())!=FILES+1:
            raise ValueError('package-file-closure')
        for name,row in current['files'].items():
            if sha(archive.read('revision-9/'+name))!=row['sha256']:raise ValueError('package-byte-mismatch')
    digest=hashlib.sha256()
    with destination.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    current.update(package=PACKAGE,package_sha256=digest.hexdigest(),package_bytes=destination.stat().st_size)
    with (out/'export-manifest.json').open('xb') as stream:stream.write(canonical(current)+b'\n')
    print(json.dumps({k:current[k] for k in ('package','package_sha256','package_bytes','packaged_file_count','native_pairs')}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=('inspect','package'))
    p.add_argument('--search-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--reviewed-identifiers-sha256');a=p.parse_args()
    if socket.gethostname().split('.')[0]!='ly-tsql-m0':raise ValueError('run-only-on-ly-tsql-m0')
    root=locate(a.search_root);out=a.out.resolve()
    if out==root or root in out.parents:raise ValueError('output-must-be-outside-run')
    if a.phase=='inspect':
        value=inspect(root);out.mkdir(parents=True,exist_ok=False)
        (out/'inspection.json').write_bytes(canonical(value)+b'\n')
        (out/'identifiers.json').write_text(json.dumps(value['identifiers'],indent=2)+'\n')
        print(json.dumps(dict(run_directory=str(root),signed_files=FILES,packaged_files=FILES+1,
            native_pairs=108,identifiers=len(value['identifiers']),identifiers_sha256=value['identifiers_sha256'],package_created=False)))
    else:package(root,out,a.reviewed_identifiers_sha256)


if __name__=='__main__':
    try:main()
    except Exception as failure:
        # Never print source content, credentials, tokens or a traceback with locals.
        code=str(failure)
        if not re.fullmatch(r'[a-z0-9-]+(?::[A-Za-z0-9_./-]+)?',code):code='input-or-dependency-check-failed'
        print('EXPORT REFUSED: '+type(failure).__name__+': '+code)
        raise SystemExit(1)
