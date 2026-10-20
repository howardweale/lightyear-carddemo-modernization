"""Retain original public CardDemo CI bytes; emit only small publication metadata.

Runs in trusted workflow_run code. Downloaded artifacts are data, never code.
"""
from collections import Counter
from datetime import date
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

REPO='howardweale/lightyear-carddemo-modernization'
ARCHIVES=frozenset(('carddemo-compose-smoke','carddemo-proof-api','carddemo-proof-browser',
                   'carddemo-proof-mutation','carddemo-status-render','carddemo-unsigned-receipt','carddemo-web-foundation'))
JOBS=frozenset(('source-and-service-foundation','compose-smoke','full-slice-proof (api)',
                'full-slice-proof (browser)','full-slice-proof (mutation)','unsigned-receipt'))
STATUSES=frozenset(('KILLED','SURVIVED','NO_COVERAGE','TIMED_OUT','RUN_ERROR','NON_VIABLE','MEMORY_ERROR'))
MAX_ARCHIVE=100_000_000


def digest(raw):return hashlib.sha256(raw).hexdigest()

def encode(value):
    raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
    if len(raw)>=50_000:raise ValueError('Publication metadata must be under 50 KB')
    return raw

def validate_run(run,jobs,artifacts):
    if (run['conclusion']!='success' or run['status']!='completed' or
            run['event'] not in ('push','pull_request') or run['path']!='.github/workflows/carddemo-web.yml' or
            run['repository']['full_name']!=REPO or run['repository']['private'] or
            run['head_repository']['full_name']!=REPO or not re.fullmatch(r'[0-9a-f]{40}',run['head_sha'])):
        raise ValueError('Only successful public same-repository CardDemo proof runs may be retained')
    if len(jobs)!=len(JOBS) or {j['name'] for j in jobs}!=JOBS or any(j['conclusion']!='success' or j['status']!='completed' for j in jobs):
        raise ValueError('Complete successful proof jobs required')
    if len(artifacts)!=len(ARCHIVES) or {a['name'] for a in artifacts}!=ARCHIVES:
        raise ValueError('Exactly seven declared public proof archives required')
    for a in artifacts:
        if (a['expired'] or type(a['size_in_bytes']) is not int or not 0<a['size_in_bytes']<=MAX_ARCHIVE or
                not re.fullmatch(r'sha256:[0-9a-f]{64}',a.get('digest','')) or
                a.get('workflow_run',{}).get('id')!=run['id']):
            raise ValueError('Artifact identity, size, expiry or digest invalid')


def inspect_archive(raw,artifact):
    if len(raw)!=artifact['size_in_bytes'] or 'sha256:'+digest(raw)!=artifact['digest']:
        raise ValueError('Original GitHub archive digest/size mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names=set();total=0
        for item in archive.infolist():
            name=item.filename;parts=PurePosixPath(name).parts;mode=item.external_attr>>16
            if (name.casefold() in names or not parts or name.startswith('/') or '\\' in name or ':' in name or
                    any(p in ('.','..') for p in name.rstrip('/').split('/')) or item.flag_bits&1 or
                    stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)):
                raise ValueError('Unsafe or duplicate archive member')
            names.add(name.casefold());total+=item.file_size
        if len(names)>10000 or total>500_000_000:raise ValueError('Archive inventory bound exceeded')
        if artifact['name']=='carddemo-proof-mutation':
            item=archive.getinfo('pit-reports/mutations.xml')
            if item.file_size>10_000_000:raise ValueError('Mutation report bound exceeded')
            return archive.read(item)
    return None


def mutation_counts(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('XML declarations refused')
    rows=ET.fromstring(raw).findall('mutation');counts=Counter(row.attrib.get('status') for row in rows)
    if not rows or set(counts)-STATUSES:raise ValueError('Raw mutation statuses missing or unsupported')
    return dict(total=len(rows),killed=counts['KILLED'],statuses=dict(sorted(counts.items())),timeout_credit=False)


def metadata(run,tag,assets,counts):
    day=run['run_started_at'][:10];date.fromisoformat(day)
    manifest=dict(schema='public-evidence-retention/1',prepared_on=day,repository=REPO,
                  source_evidence_date=day,scope='public CardDemo only',store='GitHub Release assets',
                  source_head=run['head_sha'],source_run=run['id'],source_attempt=run['run_attempt'],
                  release_url=f'https://github.com/{REPO}/releases/tag/{tag}',assets=assets)
    raw=encode(manifest)
    summary=dict(schema='carddemo-proof-summary/1',source_head=run['head_sha'],source_run=run['id'],
                 source_attempt=run['run_attempt'],measurement_date=day,manifest_sha256=digest(raw),
                 workflow_url=run['html_url'],release_url=manifest['release_url'],mutation=counts,
                 retained_original_archives=7,unsigned=True,merge_approval=False)
    return raw,encode(summary)


class Github:
    def api(self,path,method='GET',**fields):
        command=['gh','api','repos/'+REPO+'/'+path,'--method',method]
        if fields:command+=['--input','-']
        return json.loads(subprocess.check_output(command,input=json.dumps(fields).encode() if fields else None))

    def pages(self,path,key=None):
        result=[]
        for page in range(1,21):
            value=self.api(path+('\u0026' if '?' in path else '?')+f'per_page=100&page={page}')
            rows=value[key] if key else value;result.extend(rows)
            if len(rows)<100:return result
        raise ValueError('Pagination bound exceeded')

    def download(self,path):
        # Actions returns a ZIP redirect through its JSON API; Release assets
        # require the binary media type. Never apply one header to both routes.
        if re.fullmatch(r'actions/artifacts/[1-9][0-9]*/zip',path):
            accept='application/json'
        elif re.fullmatch(r'releases/assets/[1-9][0-9]*',path):
            accept='application/octet-stream'
        else:
            raise ValueError('Unsupported public proof download route')
        return subprocess.check_output(['gh','api','repos/'+REPO+'/'+path,'-H','Accept: '+accept])

    def release(self,tag):
        rows=[r for r in self.pages('releases') if r['tag_name']==tag]
        if len(rows)>1:raise ValueError('Ambiguous release')
        return rows[0] if rows else None

    def create(self,tag,head):
        # Fetch objects only. Never check out or execute source-run code.
        subprocess.run(['git','fetch','--no-tags','origin',head],check=True)
        remote=subprocess.check_output(['git','ls-remote','--tags','origin','refs/tags/'+tag],text=True).split()
        if remote and remote[0]!=head:raise ValueError('Existing tag points elsewhere')
        if not remote:subprocess.run(['git','-c','push.gpgSign=false','push','origin',head+':refs/tags/'+tag],check=True)
        subprocess.run(['gh','release','create',tag,'--repo',REPO,'--verify-tag','--draft','--prerelease',
                        '--title','Public CardDemo proof '+tag,'--notes','Original public CI proof bytes; unsigned retention only. No merge or activation approval.'],check=True)

    def upload(self,tag,path):
        subprocess.run(['gh','release','upload',tag,str(path),'--repo',REPO],check=True)


def match_asset(asset,raw):
    return asset['size']==len(raw) and asset.get('digest')=='sha256:'+digest(raw)


def public_reuse(client,release,run,artifacts,tag):
    assets=client.pages(f"releases/{release['id']}/assets")
    indexed={a['name']:a for a in assets}
    expected={a+'.zip' for a in ARCHIVES}|{'mutations.xml','retention-manifest.json','proof-summary.json'}
    if len(indexed)!=len(assets) or set(indexed)!=expected:raise ValueError('Published release asset closure changed')
    raw=client.download(f"releases/assets/{indexed['retention-manifest.json']['id']}")
    summary=client.download(f"releases/assets/{indexed['proof-summary.json']['id']}")
    if not match_asset(indexed['retention-manifest.json'],raw) or not match_asset(indexed['proof-summary.json'],summary):raise ValueError('Published metadata digest mismatch')
    m=json.loads(raw);s=json.loads(summary)
    if (m['schema']!='public-evidence-retention/1' or m['repository']!=REPO or m['scope']!='public CardDemo only' or
            m['source_run']!=run['id'] or m['source_head']!=run['head_sha'] or m['source_attempt']!=run['run_attempt'] or
            s['manifest_sha256']!=digest(raw) or s['source_run']!=run['id'] or s['source_head']!=run['head_sha']):
        raise ValueError('Published metadata source binding mismatch')
    if {a['name'] for a in m['assets']}!=expected-{'retention-manifest.json','proof-summary.json'} or len(m['assets'])!=8:
        raise ValueError('Published payload closure changed')
    for row in m['assets']:
        a=indexed[row['name']]
        if (a['size']!=row['bytes'] or a.get('digest')!='sha256:'+row['sha256'] or row['release']!=tag or
                row['url']!=f"https://github.com/{REPO}/releases/download/{tag}/{row['name']}"):
            raise ValueError('Published payload digest or URL changed')
    for a in artifacts:
        saved=indexed[a['name']+'.zip']
        if saved['digest']!=a['digest'] or saved['size']!=a['size_in_bytes']:raise ValueError('Published archive differs from original CI')
    if len(raw)>=50_000 or len(summary)>=50_000:raise ValueError('Oversized metadata')
    return raw,summary


def retain(client,run_id,root):
    run=client.api(f'actions/runs/{run_id}')
    if run['id']!=run_id:raise ValueError('Run identity mismatch')
    jobs=client.pages(f'actions/runs/{run_id}/attempts/{run["run_attempt"]}/jobs','jobs')
    artifacts=client.pages(f'actions/runs/{run_id}/artifacts','artifacts')
    validate_run(run,jobs,artifacts)
    tag='evidence-'+run['run_started_at'][:10]+f'-carddemo-run{run_id}'
    release=client.release(tag)
    if release:
        ref=client.api('git/ref/tags/'+tag)
        if ref['object']['sha']!=run['head_sha'] or ref['object']['type']!='commit':raise ValueError('Release tag identity changed')
    if release and not release['draft']:
        publication=public_reuse(client,release,run,artifacts,tag)
    else:
        files={};xml=None
        for artifact in artifacts:
            raw=client.download(f'actions/artifacts/{artifact["id"]}/zip')
            report=inspect_archive(raw,artifact)
            if report is not None:xml=report
            files[artifact['name']+'.zip']=raw
        if xml is None:raise ValueError('Raw mutation report missing')
        counts=mutation_counts(xml);files['mutations.xml']=xml
        rows=[dict(release=tag,name=name,url=f'https://github.com/{REPO}/releases/download/{tag}/{name}',
                   bytes=len(raw),sha256=digest(raw)) for name,raw in sorted(files.items())]
        publication=metadata(run,tag,rows,counts)
        files['retention-manifest.json'],files['proof-summary.json']=publication
        staging=root/'release-assets';staging.mkdir(parents=True,exist_ok=True)
        for name,raw in files.items():(staging/name).write_bytes(raw)
        if release is None:
            client.create(tag,run['head_sha']);release=client.release(tag)
            if release is None:raise ValueError('Release creation outcome unresolved; rerun only after inspection')
        current=client.pages(f'releases/{release["id"]}/assets')
        indexed={a['name']:a for a in current}
        if len(indexed)!=len(current) or set(indexed)-set(files):raise ValueError('Unexpected release asset')
        for name,raw in files.items():
            if name in indexed:
                if not match_asset(indexed[name],raw):raise ValueError('Existing release bytes differ; refusing overwrite')
            else:client.upload(tag,staging/name)
        verified=client.pages(f'releases/{release["id"]}/assets')
        if len(verified)!=len(files) or any(a['name'] not in files or not match_asset(a,files[a['name']]) for a in verified):
            raise ValueError('Uploaded asset digest mismatch')
        fresh=client.api(f'actions/runs/{run_id}')
        if (fresh['head_sha'],fresh['run_attempt'],fresh['conclusion'])!=(run['head_sha'],run['run_attempt'],'success'):
            raise ValueError('Source run changed during retention')
        ref=client.api('git/ref/tags/'+tag)
        if ref['object']['sha']!=run['head_sha'] or ref['object']['type']!='commit':raise ValueError('Tag changed during retention')
        published=client.api(f'releases/{release["id"]}',method='PATCH',draft=False,make_latest='false')
        if published['draft']:raise ValueError('Release publication incomplete')
        publication=public_reuse(client,published,run,artifacts,tag)
    # The publication artifact contains only these two small JSON files. A later
    # approved receipt PR commits them; this workflow never writes main or opens PRs.
    out=root/'publication';out.mkdir(parents=True,exist_ok=True)
    day=run['run_started_at'][:10]
    names=[f'evidence-retention-{day}-carddemo-run{run_id}.json',f'carddemo-proof-summary-{day}-run{run_id}.json']
    for name,raw in zip(names,publication):(out/name).write_bytes(raw)
    return dict(source_head=run['head_sha'],source_run=run_id,release=tag,publication_files=names)


if __name__=='__main__':
    if len(sys.argv)!=3 or not sys.argv[1].isdigit():raise SystemExit('usage: carddemo_release_retention.py RUN_ID OUTPUT')
    print(json.dumps(retain(Github(),int(sys.argv[1]),Path(sys.argv[2])),sort_keys=True))
