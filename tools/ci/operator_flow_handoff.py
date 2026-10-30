"""Bounded original public producer artifact reader; never admission authority.

Expected run/artifact/executable/digest must come from the separately reviewed
publication configuration. Do not obtain expectations from a proof or report.
This reader does not verify the signed decision, current consumer identity,
metadata HEAD, current trust policy, or native nonce/context admission.
"""
from hashlib import sha256
from io import BytesIO
import json,os,re,stat,zipfile
from tools.ci.operator_flow_download import _capture_bounded_stdout

REPOSITORY='howardweale/lightyear-carddemo-modernization'
WORKFLOW='.github/workflows/operator-flow-producer.yml'
ARTIFACT='operator-native-public-handoff'
LIMITS={'plan.json':1048576,'contract.json':1048576,'proof.json':2097152,
        'public.pem':4096,'trust.json':4096,'producer.json':524288}
MAX_ARCHIVE=4*1024*1024
MAX_EXPANDED=4*1024*1024

def require(condition,reason):
    if not condition:raise ValueError(reason)

def strict_json(raw):
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('handoff-duplicate-json-key')
            result[key]=value
        return result
    def nonfinite(value):raise ValueError('handoff-nonfinite-json')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite)

def read_public_archive(raw,expected_sha256):
    # Pure bounded byte decoding only. Synthetic archives never acquire trust
    # from passing this function; no extraction or filesystem write occurs.
    require(type(raw) is bytes and 0<len(raw)<=MAX_ARCHIVE,'handoff-archive-size')
    require(type(expected_sha256) is str and re.fullmatch('[0-9a-f]{64}',expected_sha256)
        and sha256(raw).hexdigest()==expected_sha256,'handoff-archive-digest')
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        rows=archive.infolist()
        require(len(rows)==len(LIMITS) and {x.filename for x in rows}==set(LIMITS),
            'handoff-exact-files')
        require(sum(x.file_size for x in rows)<=MAX_EXPANDED,'handoff-expanded-size')
        result={}
        for row in rows:
            mode=(row.external_attr>>16)&0xffff
            require(not row.is_dir() and not row.flag_bits&1
                and stat.S_IFMT(mode) in (0,stat.S_IFREG)
                and row.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED),
                'handoff-regular-unencrypted-file')
            require(0<row.file_size<=LIMITS[row.filename]
                and 0<row.compress_size<=MAX_ARCHIVE
                and row.file_size<=max(4096,row.compress_size*200),'handoff-entry-size')
            # Read only declared bounded bytes plus one. ZipFile checks CRC.
            with archive.open(row) as stream:
                value=stream.read(LIMITS[row.filename]+1)
            require(len(value)==row.file_size,'handoff-entry-length')
            result[row.filename]=value
    return result

def _expected(value):
    require(type(value) is dict and set(value)=={'executable','producer_run_id','artifact_id','archive_sha256'},
        'handoff-expectation-fields')
    require(type(value['executable']) is str and re.fullmatch('[0-9a-f]{40}',value['executable'])
        and type(value['archive_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['archive_sha256'])
        and all(type(value[k]) is int and 0<value[k]<10**20 for k in ('producer_run_id','artifact_id')),
        'handoff-expectation-values')
    return dict(value)

def _original_producer(api,expected):
    prefix='/repos/'+REPOSITORY;run_id=expected['producer_run_id'];head=expected['executable']
    run=api.request('GET',prefix+'/actions/runs/'+str(run_id))
    require(type(run.get('id')) is int and run['id']==run_id
        and type(run.get('run_attempt')) is int and run['run_attempt']==1
        and run.get('event')=='pull_request' and run.get('head_sha')==head
        and run.get('head_repository',{}).get('full_name')==REPOSITORY
        and run.get('status')=='completed' and run.get('conclusion')=='success'
        and type(run.get('workflow_id')) is int and run['workflow_id']>0,'handoff-original-producer-run')
    workflow=api.request('GET',prefix+'/actions/workflows/'+str(run['workflow_id']))
    require(workflow.get('path')==WORKFLOW,'handoff-producer-workflow')
    jobs=api.request('GET',prefix+'/actions/runs/'+str(run_id)+'/attempts/1/jobs?per_page=100')
    rows=jobs.get('jobs')
    require(type(rows) is list and type(jobs.get('total_count')) is int
        and jobs['total_count']==len(rows)<=100,'handoff-complete-producer-jobs')
    selected=[x for x in rows if x.get('name')=='operator-producer']
    require(len(selected)==1,'handoff-unique-producer-job')
    job=selected[0]
    require(type(job.get('id')) is int and job['id']>0 and job.get('run_id')==run_id
        and job.get('head_sha')==head and job.get('status')=='completed' and job.get('conclusion')=='success'
        and ('run_attempt' not in job or type(job['run_attempt']) is int and job['run_attempt']==1),
        'handoff-original-producer-job')
    listing=api.request('GET',prefix+'/actions/runs/'+str(run_id)+'/artifacts?per_page=100')
    artifacts=listing.get('artifacts')
    require(type(artifacts) is list and type(listing.get('total_count')) is int
        and listing['total_count']==len(artifacts)<=100,'handoff-complete-artifact-list')
    matches=[x for x in artifacts if x.get('name')==ARTIFACT]
    require(len(matches)==1 and matches[0].get('id')==expected['artifact_id'],'handoff-unique-artifact')
    artifact=api.request('GET',prefix+'/actions/artifacts/'+str(expected['artifact_id']))
    for key in ('id','name','digest','expired','size_in_bytes'):
        require(artifact.get(key)==matches[0].get(key),'handoff-artifact-list-binding')
    require(type(artifact.get('id')) is int and artifact['id']==expected['artifact_id']
        and artifact.get('name')==ARTIFACT and artifact.get('expired') is False
        and type(artifact.get('size_in_bytes')) is int and 0<artifact['size_in_bytes']<=MAX_ARCHIVE
        and artifact.get('digest')=='sha256:'+expected['archive_sha256']
        and artifact.get('workflow_run',{}).get('id')==run_id
        and artifact.get('workflow_run',{}).get('head_sha')==head,'handoff-original-artifact')
    return dict(repository=REPOSITORY,executable=head,run_id=run_id,run_attempt=1,
        job_id=job['id'],workflow_id=run['workflow_id'],workflow_path=WORKFLOW,
        artifact_id=artifact['id'],artifact_digest=artifact['digest'],archive_bytes=artifact['size_in_bytes'])

def fetch_producer_handoff(expected):
    # Public entry always constructs the real API; no caller API, downloader,
    # verifier or passed authority/context is accepted.
    expected=_expected(expected)
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY,'handoff-ci-only')
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    api=_GitHubAPI();observed=_original_producer(api,expected)
    path='/repos/'+REPOSITORY+'/actions/artifacts/'+str(expected['artifact_id'])+'/zip'
    original_bytes=_capture_bounded_stdout(['gh','api','--hostname','github.com','--method','GET',path],
        max_bytes=observed['archive_bytes'],timeout=45)
    require(len(original_bytes)==observed['archive_bytes'],
        'handoff-download-stop-no-retry')
    files=read_public_archive(original_bytes,expected['archive_sha256'])
    require(_original_producer(api,expected)==observed,'handoff-producer-changed')
    report=strict_json(files['producer.json']);trust=strict_json(files['trust.json'])
    require(type(report) is dict and report.get('producer_stage_passed') is True
        and report.get('fixture_only') is True and report.get('full_route_passed') is False
        and report.get('real_pack_ready') is False,'handoff-producer-report-state')
    identity={k:observed[k] for k in ('repository','executable','run_id','run_attempt','job_id','workflow_id','workflow_path')}
    require(report.get('producer')==identity,'handoff-reported-producer-binding')
    hashes=report.get('public_handoff_hashes')
    require(type(hashes) is dict and set(hashes)==set(LIMITS)-{'producer.json'}
        and all(hashes[k]==sha256(files[k]).hexdigest() for k in hashes),'handoff-public-bytes-binding')
    require(type(trust) is dict and set(trust)=={'scope','public_key','journal_head_sha256'}
        and trust.get('scope')=='factory' and trust.get('public_key')=='public.pem'
        and type(trust.get('journal_head_sha256')) is str
        and re.fullmatch('[0-9a-f]{64}',trust['journal_head_sha256']),'handoff-public-trust-shape')
    # Native proof, source/runtime, live consumer and current trust checks are
    # deliberately still owed. Never return an admission, context or passed GO.
    return files,observed
