"""Fixed CI caller for native disposable publication review; no publisher.

Inputs are independently reviewed public scalars and preprepared public paths.
Parsing grants no approval. No values are inferred from artifact/proof content.
"""
import os,re,sys
from pathlib import Path
from tools.ci.operator_flow_publication_review import (
    review_publication,_independent_expectations,REVIEW_JOB,REPOSITORY)
from tools.ci.operator_flow_metadata import require

SCALARS=('executable','metadata_head','producer_run_id','artifact_id','archive_sha256',
    'plan_sha256','decision_sha256','journal_head_sha256','public_key_sha256','nonce_sha256','commit_epoch')
PATHS=('metadata_root','trust_path')

def _parse_args(argv):
    require(type(argv) is list and all(type(x) is str for x in argv)
        and len(argv)==2*(len(SCALARS)+len(PATHS)),'review-cli-exact-arguments')
    flags={'--'+key.replace('_','-'):key for key in SCALARS+PATHS}
    values={}
    for flag,value in zip(argv[::2],argv[1::2]):
        require(flag in flags and flags[flag] not in values and 0<len(value)<=4096,
            'review-cli-unknown-duplicate-or-empty')
        values[flags[flag]]=value
    require(set(values)==set(SCALARS+PATHS),'review-cli-missing')
    for key in ('producer_run_id','artifact_id','commit_epoch'):
        require(re.fullmatch('[1-9][0-9]{0,19}',values[key]),'review-cli-integer')
        values[key]=int(values[key])
    _independent_expectations(**{key:values[key] for key in SCALARS})
    require(all(Path(values[key]).is_absolute() for key in PATHS),'review-cli-absolute-paths')
    return values

def _caller_source(root,executable):
    from hashlib import sha256
    from tools.ci.operator_flow_review_source import _source_bytes,LIMIT
    from tools.ci.operator_flow_consumer import clean_root,git
    root=Path(root);relative='tools/ci/operator_flow_review_cli.py';path=root/relative
    require(__name__=='tools.ci.operator_flow_review_cli'
        and Path(__file__)==path and __spec__ is not None and __spec__.origin==str(path),
        'review-cli-original-module')
    clean_root(root)
    require(git(root,'rev-parse','HEAD').decode().strip()==executable,'review-cli-exact-E')
    raw=_source_bytes(path);ref=executable+':'+relative
    size=git(root,'cat-file','-s',ref).decode().strip()
    require(re.fullmatch('[1-9][0-9]{0,7}',size) and int(size)<=LIMIT,'review-cli-source-size')
    committed=git(root,'show',ref)
    require(len(committed)==int(size) and raw==committed,'review-cli-committed-source')
    return sha256(raw).hexdigest()

def main():
    # Reject scratch and other jobs before parsing, file reads or native API.
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY
        and os.environ.get('GITHUB_EVENT_NAME')=='pull_request'
        and os.environ.get('GITHUB_JOB')==REVIEW_JOB
        and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','review-cli-original-job-only')
    values=_parse_args(sys.argv[1:]);root=Path.cwd()
    observation=_caller_source(root,values['executable'])
    # Original entry obtains its own live reviewer/producer observations,
    # prepares exact local M and performs native proof/runtime verification.
    review_publication(root,**values)
    require(_caller_source(root,values['executable'])==observation,'review-cli-source-changed')
    # Do not serialize proof, object bodies, paths or a publication decision.
    print('DISPOSABLE PUBLICATION REVIEW RETURNED; NO PUBLICATION, ADMISSION OR QUALIFICATION AUTHORITY')
    return 0

if __name__=='__main__':
    # Preserve canonical module origin for source checks under python -m.
    from tools.ci.operator_flow_review_cli import main as original_main
    raise SystemExit(original_main())
