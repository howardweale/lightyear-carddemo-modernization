"""CI-only read-only composition of original handoff and native candidate checks.

Both independent checkouts and external public trust must already be prepared.
No caller API/verifier/clock, authority receipt, CLI, publisher, object write,
reservation, context or controller is provided. Returned objects retain every
original false authority/readiness flag. Full publisher guards remain owed.
"""
import os,re
from pathlib import Path
from tools.ci.operator_flow_handoff import fetch_producer_handoff,_original_producer,REPOSITORY
from tools.ci.operator_flow_consumer import (clean_root,check_metadata,
    check_public_expectations,check_native_review,HASH_FIELDS)
from tools.ci.operator_flow_metadata import PREFIX,require
from tools.ci.operator_flow_publication_reconstruction import reconstruct_publication_objects


def _independent_expectations(*,executable,metadata_head,producer_run_id,artifact_id,
        archive_sha256,plan_sha256,decision_sha256,journal_head_sha256,public_key_sha256,
        nonce_sha256,commit_epoch):
    # Internal function arguments, not a new serialized approval or variable.
    values=dict(executable=executable,metadata_head=metadata_head,producer_run_id=producer_run_id,
        artifact_id=artifact_id,archive_sha256=archive_sha256,plan_sha256=plan_sha256,
        decision_sha256=decision_sha256,journal_head_sha256=journal_head_sha256,
        public_key_sha256=public_key_sha256,nonce_sha256=nonce_sha256)
    require(all(type(values[k]) is str and re.fullmatch('[0-9a-f]{64}',values[k]) for k in HASH_FIELDS)
        and all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (executable,metadata_head))
        and executable!=metadata_head,'publication-review-independent-hashes')
    require(all(type(v) is int and 0<v<10**20 for v in (producer_run_id,artifact_id))
        and type(commit_epoch) is int and 1<=commit_epoch<10**11,'publication-review-independent-identities')
    return values


def _prepared_trust(executable_root,metadata_root,trust_path,files):
    from lightyear_factory.model_admission import _bounded_regular_bytes
    trust_path=Path(trust_path)
    require(trust_path.is_absolute() and trust_path.resolve(strict=True)==trust_path
        and trust_path.name=='trust.json','publication-review-prepared-trust-path')
    for name in ('trust.json','public.pem'):
        path=trust_path.parent/name
        require(not any(path==root or path.is_relative_to(root) for root in (executable_root,metadata_root)),
            'publication-review-external-trust')
        require(_bounded_regular_bytes(path,65536,'publication-review-trust-bytes')==files[name],
            'publication-review-prepared-trust-mismatch')


def review_publication(executable_root,metadata_root,trust_path,*,executable,metadata_head,
        producer_run_id,artifact_id,archive_sha256,plan_sha256,decision_sha256,journal_head_sha256,
        public_key_sha256,nonce_sha256,commit_epoch):
    require(os.environ.get('GITHUB_ACTIONS')=='true'
        and os.environ.get('GITHUB_REPOSITORY')==REPOSITORY,'publication-review-ci-only')
    expected=_independent_expectations(executable=executable,metadata_head=metadata_head,
        producer_run_id=producer_run_id,artifact_id=artifact_id,archive_sha256=archive_sha256,
        plan_sha256=plan_sha256,decision_sha256=decision_sha256,journal_head_sha256=journal_head_sha256,
        public_key_sha256=public_key_sha256,nonce_sha256=nonce_sha256,commit_epoch=commit_epoch)
    executable_root=Path(executable_root);metadata_root=Path(metadata_root)
    clean_root(executable_root);clean_root(metadata_root)
    require(not executable_root.is_relative_to(metadata_root) and not metadata_root.is_relative_to(executable_root),
        'publication-review-separate-checkouts')
    for root in (executable_root,metadata_root):
        require(not (root/'.git/commondir').exists() and not (root/'.git/objects/info/http-alternates').exists(),
            'publication-review-independent-checkouts')
    from lightyear_factory.contracts import WorkOrder
    from lightyear_factory.model_admission import FactoryModelAdmission
    from lightyear_execution.contracts import ExecutionPolicy
    from lightyear_execution.tower_drill_admission import verify_human_drill_plan
    from lightyear_execution.tower_drill_reservation import _GitHubAPI
    from tools.ci.operator_flow_review_source import check_review_source
    source_observation=check_review_source(executable_root,executable)
    handoff={key:expected[key] for key in ('executable','producer_run_id','artifact_id','archive_sha256')}
    files,observed=fetch_producer_handoff(handoff)
    check_public_expectations(expected,files)
    _prepared_trust(executable_root,metadata_root,trust_path,files)
    candidate,requests=reconstruct_publication_objects(executable_root,files,
        expected_executable=executable,expected_candidate=metadata_head,commit_epoch=commit_epoch)
    check_metadata(metadata_root,expected,files)
    order=WorkOrder.load(metadata_root/'tests/fixtures/p5_public/human-clean-control/work-order.json')
    policy=ExecutionPolicy.load(metadata_root/(PREFIX+'execution-policy.json'))
    admission=FactoryModelAdmission.from_external_trust(metadata_root,PREFIX+'plan.json',PREFIX+'proof.json',
        PREFIX+'contract.json',trust_path)
    review=verify_human_drill_plan(admission,order,policy)
    check_native_review(expected,review)
    plan=admission._committed_json(PREFIX+'plan.json')
    runtime=admission.verify_runtime(order,source_root=metadata_root,
        input_paths={key:metadata_root/row['path'] for key,row in plan['bound_inputs'].items()},policy=policy)
    require(plan['executable_commit']==executable and runtime['executable_commit']==metadata_head,
        'publication-review-native-E-M')
    # Do not download a second archive or re-enter admission. Reobserve original
    # producer metadata, original source bytes and current external trust only.
    require(_original_producer(_GitHubAPI(),handoff)==observed,'publication-review-producer-changed')
    check_metadata(metadata_root,expected,files)
    require(reconstruct_publication_objects(executable_root,files,expected_executable=executable,
        expected_candidate=metadata_head,commit_epoch=commit_epoch)==(candidate,requests),
        'publication-review-reconstruction-changed')
    _prepared_trust(executable_root,metadata_root,trust_path,files)
    require(verify_human_drill_plan(admission,order,policy)==review,'publication-review-native-trust-changed')
    # No current consumer run, nonce, full guards or publication permission is
    # inferred. Caller must perform fresh complete guards before any mutation.
    require(check_review_source(executable_root,executable)==source_observation,
        'publication-review-source-observation-changed')
    return candidate,requests
