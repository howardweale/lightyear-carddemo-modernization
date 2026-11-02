"""Proposed one-use CI reservation for a genuine human-approved drill plan.

Inactive until reviewed CLI integration exists. A reservation is evidence of
consumption, never an admission receipt, role credential or execution grant.
No read-back API converts an existing claim into permission to resume.
"""
from copy import deepcopy
import json
import os
import re
import subprocess

from lightyear_factory.contracts import canonical_hash
from .contracts import ExecutionContractError
from .tower_drill_admission import verify_human_drill_plan


_REPOSITORY = 'howardweale/lightyear-carddemo-modernization'
_PREFIX = '/repos/' + _REPOSITORY


def _github_subprocess_environment():
    # Exclude these names BEFORE looking up values. Other entries, including
    # existing GitHub authentication, PATH and proxy configuration, are copied
    # only into the child environment. No environment values are logged or
    # persisted. This does not erase the caller's environment or memory.
    excluded = {'openai_api_key', 'factory_transport_key'}
    return {name: os.environ[name] for name in os.environ
            if name.casefold() not in excluded}


class _GitHubAPI:
    """Use existing job authentication; never emit or persist credential values."""

    def request(self, method, path, payload=None):
        if method not in {'GET', 'POST'} or not path.startswith(_PREFIX + '/'):
            raise ExecutionContractError('drill-reservation-api-scope')
        command = ['gh', 'api', '--hostname', 'github.com', '--method', method,
                   '-H', 'Accept: application/vnd.github+json', path]
        data = None
        if payload is not None:
            command += ['--input', '-']
            data = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        try:
            result = subprocess.run(command, input=data, capture_output=True,
                                    timeout=45, check=False,
                                    env=_github_subprocess_environment())
            if result.returncode != 0 or len(result.stdout) > 2 * 1024 * 1024:
                raise ValueError('request refused')
            return json.loads(result.stdout)
        except Exception:
            # A failed POST has an unknown outcome. No retry, probe-and-resume,
            # credential-bearing stderr, delete or overwrite is permitted.
            raise ExecutionContractError('drill-reservation-api-failed-stop-no-retry') from None


def _ci_identity(binding, head, api, environment):
    ci = binding['ci']
    run_id = environment.get('GITHUB_RUN_ID', '')
    if (environment.get('GITHUB_ACTIONS') != 'true'
            or environment.get('GITHUB_REPOSITORY') != _REPOSITORY
            or environment.get('GITHUB_EVENT_NAME') != 'pull_request'
            or environment.get('GITHUB_RUN_ATTEMPT') != '1'
            or environment.get('GITHUB_JOB') != ci['job']
            or not re.fullmatch('[1-9][0-9]{0,19}', run_id)):
        raise ExecutionContractError('drill-reservation-ci-environment')
    run = api.request('GET', _PREFIX + '/actions/runs/' + run_id)
    workflow_path = ci['workflow_ref'].split('@')[0][len(_REPOSITORY) + 1:]
    if (type(run.get('id')) is not int or str(run['id']) != run_id
            or type(run.get('run_attempt')) is not int or run['run_attempt'] != 1
            or run.get('event') != 'pull_request' or run.get('status') != 'in_progress'
            or run.get('head_sha') != head
            or run.get('head_repository', {}).get('full_name') != _REPOSITORY
            or type(run.get('workflow_id')) is not int or run['workflow_id'] <= 0):
        raise ExecutionContractError('drill-reservation-live-run')
    workflow = api.request('GET', _PREFIX + '/actions/workflows/' + str(run['workflow_id']))
    if workflow.get('path') != workflow_path:
        raise ExecutionContractError('drill-reservation-live-workflow')
    jobs = api.request('GET', _PREFIX + '/actions/runs/' + run_id + '/attempts/1/jobs?per_page=100')
    rows = jobs.get('jobs')
    if (not isinstance(rows, list) or type(jobs.get('total_count')) is not int
            or jobs['total_count'] != len(rows) or len(rows) > 100):
        raise ExecutionContractError('drill-reservation-job-list-incomplete')
    matched = [row for row in rows if row.get('name') == ci['job']]
    if len(matched) != 1:
        raise ExecutionContractError('drill-reservation-job-ambiguous')
    job = matched[0]
    if (type(job.get('id')) is not int or job['id'] <= 0
            or job.get('status') != 'in_progress' or job.get('head_sha') != head
            or type(job.get('run_id')) is not int or str(job['run_id']) != run_id
            or ('run_attempt' in job and
                (type(job['run_attempt']) is not int or job['run_attempt'] != 1))):
        raise ExecutionContractError('drill-reservation-live-job')
    # GitHub's documented job shape omits run_attempt. Attempt 1 is bound by
    # the attempt-specific endpoint plus the independently checked run record.
    # Environment variables alone are not identity proof. These API checks are
    # within the reviewed-workflow/GitHub-runner trust boundary; they are not
    # independent process attestation and must not be labelled as such.
    return dict(repository=_REPOSITORY, run_id=int(run_id), run_attempt=1,
                job=ci['job'], job_id=job['id'], workflow_id=run['workflow_id'],
                workflow_ref=ci['workflow_ref'], head_sha=head)


def _consume_verified_plan(review, api, environment, reverify):
    """Internal algorithm boundary for CI-only synthetic API tests.

    This function deliberately returns non-authorizing evidence even when all
    inputs are supplied by a test. Production callers must use the public
    verifier entry below; no caller-supplied dict grants execution authority.
    """
    if (review.get('status') != 'verified-plan-only'
            or review.get('execution_authorized') is not False
            or review.get('nonce_consumed') is not False):
        raise ExecutionContractError('drill-reservation-plan-state')
    binding = review['drill_binding']
    model = review['verified_model_admission']
    head = model['executable_commit']
    identity = _ci_identity(binding, head, api, environment)
    if reverify() != review:
        raise ExecutionContractError('drill-reservation-plan-or-trust-changed')
    # The namespace follows the nonce within the fixed repository. Changing a
    # plan, work order, run id or job cannot reuse the same signed nonce.
    name = 'factory-human-drill-consumed-' + binding['nonce_sha256']
    record = dict(schema='factory-human-drill-consumption/1',
                  case_id=binding['case_id'], nonce_sha256=binding['nonce_sha256'],
                  plan_sha256=model['plan_sha256'], decision_sha256=model['decision_sha256'],
                  trusted_journal_head=model['trusted_journal_head'],
                  work_order_sha256=binding['work_order_sha256'],
                  execution_policy_sha256=binding['execution_policy_sha256'], ci=identity,
                  consumed_before_execution=True, execution_authorized=False,
                  admission_receipt_issued=False)
    record['content_sha256'] = canonical_hash(record)
    message = json.dumps(record, sort_keys=True, separators=(',', ':'))
    # An annotated object binds the exact record. It is NOT cryptographically
    # signed. An orphan object after any failure is never execution authority.
    tag = api.request('POST', _PREFIX + '/git/tags',
                      dict(tag=name, message=message, object=head, type='commit'))
    if (not isinstance(tag.get('sha'), str) or not re.fullmatch('[0-9a-f]{40}', tag['sha'])
            or tag.get('tag') != name or tag.get('message') != message
            or tag.get('object') != {'type': 'commit', 'sha': head,
                                    'url': 'https://api.github.com' + _PREFIX + '/git/commits/' + head}):
        raise ExecutionContractError('drill-reservation-tag-object-stop')
    # Atomic create is the only consumption transition. Existing refs, including
    # claims by this same run, fail. No force, PATCH, DELETE or retry exists.
    ref = 'refs/tags/' + name
    result = api.request('POST', _PREFIX + '/git/refs', dict(ref=ref, sha=tag['sha']))
    if (result.get('ref') != ref or result.get('object', {}).get('sha') != tag['sha']
            or result.get('object', {}).get('type') != 'tag'):
        raise ExecutionContractError('drill-reservation-ref-binding-stop')
    readback = api.request('GET', _PREFIX + '/git/ref/tags/' + name)
    object_readback = api.request('GET', _PREFIX + '/git/tags/' + tag['sha'])
    if (readback.get('ref') != ref or readback.get('object', {}).get('sha') != tag['sha']
            or readback.get('object', {}).get('type') != 'tag'
            or object_readback.get('sha') != tag['sha']
            or object_readback.get('tag') != name or object_readback.get('message') != message
            or object_readback.get('object') != tag['object']):
        raise ExecutionContractError('drill-reservation-readback-stop')
    if reverify() != review or _ci_identity(binding, head, api, environment) != identity:
        raise ExecutionContractError('drill-reservation-post-create-binding-stop-consumed')
    return dict(schema='factory-human-drill-reservation-review/1', status='consumed-only',
                ref=ref, tag_object_sha=tag['sha'], record=deepcopy(record),
                execution_authorized=False, admission_receipt_issued=False,
                unresolved=['role-action-authorization', 'oci-runtime-binding',
                            'output-authenticity-verification', 'cli-dispatch'])


def reserve_human_drill_plan(admission, order, policy):
    """Proposed production boundary; no CLI dispatch or execution grant yet."""
    review = verify_human_drill_plan(admission, order, policy)
    identity_environment = {name: os.environ.get(name, '') for name in (
        'GITHUB_ACTIONS', 'GITHUB_REPOSITORY', 'GITHUB_EVENT_NAME',
        'GITHUB_RUN_ATTEMPT', 'GITHUB_RUN_ID', 'GITHUB_JOB')}
    return _consume_verified_plan(
        review, _GitHubAPI(), identity_environment,
        lambda: verify_human_drill_plan(admission, order, policy))
