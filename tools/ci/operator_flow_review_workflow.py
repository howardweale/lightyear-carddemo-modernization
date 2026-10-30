"""Prospective read-only reviewer workflow entry; no remote publication.

External public values are configuration, never authority. This entry is not
enabled on scratch. Native current reviewer and proof checks remain required.
"""
import base64,hashlib,json,os,subprocess,sys
from pathlib import Path
from tools.ci.operator_flow_review_cli import SCALARS,_parse_args,_caller_source
from tools.ci.operator_flow_publication_review import (
    REVIEW_JOB,REPOSITORY,_review_current_identity,review_publication)
from tools.ci.operator_flow_consumer import clean_root,git
from tools.ci.operator_flow_metadata import require

def _configuration(environment,temporary):
    values={key:environment.get('OPERATOR_REVIEW_'+key.upper(),'') for key in SCALARS}
    base=Path(temporary)/'operator-publication-review-inputs'
    values.update(metadata_root=str(base/'metadata'),trust_path=str(base/'public'/'trust.json'))
    args=[v for key,value in values.items() for v in ('--'+key.replace('_','-'),value)]
    values=_parse_args(args)
    encoded=environment.get('OPERATOR_REVIEW_PUBLIC_KEY_BASE64','')
    require(type(encoded) is str and 0<len(encoded)<=87384,'review-workflow-public-key-size')
    try:public=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError):raise ValueError('review-workflow-public-key-encoding') from None
    require(0<len(public)<=65536 and base64.b64encode(public).decode()==encoded
        and hashlib.sha256(public).hexdigest()==values['public_key_sha256'],
        'review-workflow-independent-public-key')
    return values,public

def _source(root,executable):
    from tools.ci.operator_flow_review_source import _source_bytes,LIMIT
    relative='tools/ci/operator_flow_review_workflow.py';path=root/relative
    require(__name__=='tools.ci.operator_flow_review_workflow' and Path(__file__)==path
        and __spec__ is not None and __spec__.origin==str(path),'review-workflow-original-module')
    clean_root(root);require(git(root,'rev-parse','HEAD').decode().strip()==executable,'review-workflow-exact-E')
    raw=_source_bytes(path);ref=executable+':'+relative
    size=git(root,'cat-file','-s',ref).decode().strip()
    require(size.isdecimal() and 0<int(size)<=LIMIT,'review-workflow-source-size')
    committed=git(root,'show',ref)
    require(len(committed)==int(size) and raw==committed,'review-workflow-source-bytes')
    return hashlib.sha256(raw).hexdigest()

def _trust_bytes(head):
    # Exact existing producer canonical encoding; no new trust schema.
    return json.dumps(dict(scope='factory',public_key='public.pem',journal_head_sha256=head),
        sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def _write_new(path,raw):
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())

def _clone_checkout(root,metadata,empty,executable):
    # Local disposable preparation only; caller performs live identity checks.
    temporary=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(os.environ.get('GITHUB_ACTIONS')=='true' and metadata.is_absolute()
        and metadata.parent.resolve(strict=True)==metadata.parent
        and metadata.is_relative_to(temporary) and not metadata.exists()
        and not metadata.is_relative_to(root) and not root.is_relative_to(metadata),
        'review-workflow-fresh-clone')
    require(empty.resolve(strict=True)==empty and empty.is_relative_to(temporary)
        and not list(empty.iterdir()) and not empty.is_symlink(),'review-workflow-empty-template')
    clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==executable,'review-workflow-source-E')
    # Do not inherit global/system Git hooks, templates, filters, signing or
    # caller-supplied GIT_* overrides. No source config is copied by clone.
    env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')
        and k.upper() not in ('OPENAI_API_KEY','FACTORY_TRANSPORT_KEY','FACTORY_CANDIDATE_SIGNING_KEY')}
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TEMPLATE_DIR=str(empty))
    def local_git(*args):
        result=subprocess.run(['git','-c','core.hooksPath='+str(empty),'-c','core.autocrlf=false',*args],
            env=env,capture_output=True,timeout=120)
        require(result.returncode==0,'review-workflow-local-clone-refused')
    local_git('clone','--no-hardlinks','--no-checkout','--template='+str(empty),str(root),str(metadata))
    local_git('-C',str(metadata),'config','core.autocrlf','false')
    local_git('-C',str(metadata),'checkout','--detach',executable)
    clean_root(root);clean_root(metadata)
    require(git(metadata,'rev-parse','HEAD').decode().strip()==executable,'review-workflow-clone-E')


def _review_observation(candidate,requests,values,identity):
    """Hash-only disposable diagnostic, not approval or authenticated evidence.

    Pure inputs grant no origin. Only the fixed caller emits after original
    native review and final source checks; a reader must authenticate that job.
    """
    from tools.ci.operator_flow_publication_review import _independent_expectations
    expected={key:values[key] for key in SCALARS}
    _independent_expectations(**expected)
    require(type(candidate) is dict and candidate.get('parent')==expected['executable']
        and candidate.get('commit')==expected['metadata_head']
        and candidate.get('commit_epoch')==expected['commit_epoch'],'review-observation-candidate')
    for flag in ('native_proof_verified','full_guards_passed','publish_ready','publication_authorized',
                 'full_route_passed','real_pack_ready'):
        require(candidate.get(flag) is False,'review-observation-no-authority')
    require(type(requests) is tuple and 1<=len(requests)<=8
        and all(type(row) is tuple and len(row)==3 and row[0] in ('blobs','trees','commits')
            and type(row[1]) is str and len(row[1])==40 and all(c in '0123456789abcdef' for c in row[1])
            and type(row[2]) is dict for row in requests),'review-observation-requests')
    require(requests[-1][0:2]==('commits',expected['metadata_head'])
        and requests[-1][2].get('tree')==candidate.get('tree')
        and requests[-1][2].get('parents')==[expected['executable']],
        'review-observation-final-commit')
    fields={'pr','run','job','workflow','executable','tested_merge','base','workflow_revision',
            'workflow_sha256','event_sha256'}
    require(type(identity) is dict and set(identity)==fields
        and all(type(identity[k]) is int and 0<identity[k]<10**20 for k in ('pr','run','job','workflow'))
        and identity['executable']==expected['executable'],'review-observation-identity')
    for key,width in (('executable',40),('tested_merge',40),('base',40),('workflow_revision',40),
                      ('workflow_sha256',64),('event_sha256',64)):
        value=identity[key]
        require(type(value) is str and len(value)==width and all(c in '0123456789abcdef' for c in value),
            'review-observation-identity-hash')
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
            ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    # No raw proof, object bodies, public-key contents, paths or environment.
    return ('DISPOSABLE_REVIEW_BINDING E='+expected['executable']+' M='+expected['metadata_head']
        +' reviewer_run='+str(identity['run'])+' reviewer_job='+str(identity['job'])
        +' expectations_sha256='+digest(expected)+' identity_sha256='+digest(identity)
        +' requests_sha256='+digest(requests)+' request_count='+str(len(requests))
        +' pr='+str(identity['pr'])+' workflow='+str(identity['workflow'])
        +' base='+identity['base']+' tested_merge='+identity['tested_merge']
        +' workflow_revision='+identity['workflow_revision']
        +' workflow_sha256='+identity['workflow_sha256']+' event_sha256='+identity['event_sha256']
        +' publication_authorized=false admission_authorized=false qualification_evidence=false')

def main():
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY
        and os.environ.get('GITHUB_EVENT_NAME')=='pull_request'
        and os.environ.get('GITHUB_JOB')==REVIEW_JOB
        and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','review-workflow-original-job-only')
    root=Path.cwd();temporary=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    require(temporary.is_absolute() and not temporary.is_relative_to(root)
        and not root.is_relative_to(temporary),'review-workflow-external-temporary')
    values,public=_configuration(os.environ,temporary);executable=values['executable']
    source=(_source(root,executable),_caller_source(root,executable))
    identity=_review_current_identity(root,executable)
    base=temporary/'operator-publication-review-inputs'
    require(not base.exists(),'review-workflow-fresh-inputs-only');base.mkdir()
    # Exclusive local intent before clone/material writes. No retry or cleanup
    # can turn a partially prepared directory into a fresh attempt.
    _write_new(base/'intent.txt',b'DISPOSABLE LOCAL REVIEW INPUTS; NO AUTHORITY\n')
    empty=base/'empty-git-template';empty.mkdir();trust=base/'public';trust.mkdir()
    metadata=Path(values['metadata_root'])
    _clone_checkout(root,metadata,empty,executable)
    _write_new(trust/'public.pem',public)
    _write_new(trust/'trust.json',_trust_bytes(values['journal_head_sha256']))
    require(_review_current_identity(root,executable)==identity,'review-workflow-identity-changed')
    candidate,requests=review_publication(root,**values)
    require((_source(root,executable),_caller_source(root,executable))==source,'review-workflow-source-changed')
    print(_review_observation(candidate,requests,values,identity),flush=True)
    print('DISPOSABLE NATIVE REVIEW RETURNED; NO PUBLICATION, ADMISSION OR QUALIFICATION AUTHORITY')
    return 0

if __name__=='__main__':
    from tools.ci.operator_flow_review_workflow import main as original_main
    raise SystemExit(original_main())
