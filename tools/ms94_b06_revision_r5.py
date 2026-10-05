"""Bind offline compilation corrections without rewriting historical schedules."""
from copy import deepcopy
from lightyear_calibration.contracts import seal, verify
from tools.ms94_b06_admission import check

SUMMARY = 'd2360cb6f3aa93db322246e9f499a390321ebd3c8bc924fa0a12eb33b6a41f9b'


def revise(draft, summary, catalogs, classpath_audit):
    for item in (draft, catalogs, classpath_audit): verify(item)
    verify({k:v for k,v in summary.items() if k != 'signature'})
    check(summary['content_sha256'] == SUMMARY, 'r5-wrong-compilation-summary')
    result = deepcopy(draft)
    result.pop('content_sha256'); result.pop('signature', None)
    revisions = summary['source_revisions']
    check(len(revisions) == 4, 'r5-source-revision-inventory')
    changed = []
    for slot in result['schedule']:
        before = slot['source']['sha256']
        for revision in revisions:
            if revision['original_sha256'] != before: continue
            # The fourth correction materializes ONLY the declared duplicate
            # control; the same retained source remains in reference slots.
            if 'duplicate-trace' in revision['reason'] and slot['control'] != 'duplicate-trace-key': continue
            slot['source']['sha256'] = revision['revised_sha256']
            changed.append({'slot_id':slot['id'], **revision})
        source = slot['source']['sha256']
        catalog = catalogs['sources'][source]['catalog']; verify(catalog)
        check(catalog['source_sha256'] == source, 'r5-candidate-catalog-source')
        slot['source'].update(compiled=True, native_qualified_here=False,
            compilation_record_sha256=catalog['compilation_record_sha256'],
            class_catalog_sha256=catalog['content_sha256'])
    result.update(artifact_type='ms94-b06-qualification-assembly-specification/5',
        previous_assembly_sha256=draft['content_sha256'], source_revisions=changed,
        compilation_summary_sha256=SUMMARY, classpath_audit_sha256=classpath_audit['content_sha256'],
        executable_snapshot_sha256=None, status='blocked-before-executable-conversion',
        execution_blockers=['Resolved Tycho/Surefire/OSGi terminal class identity is unavailable.',
            'Native posting-cause closed projection and full private per-slot input assembly remain unsealed.'],
        native_pairs=0, model_calls=0, measurement_authorized=False, docker_runs_authorized=False)
    return seal(result)
