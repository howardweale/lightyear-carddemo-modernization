"""Explicit applicability for the four historical offline source corrections."""
from copy import deepcopy
from lightyear_calibration.contracts import seal, verify
from tools.ms94_b06_admission import check
from tools.ms94_b06_revision_r5 import SUMMARY

# The correction identity, not its editorial explanation, selects a control.
APPLIES_TO = {
    '637b228ea66f8523c97d27e0fbb0796eaea98e7835a87eeb262931cf2eaf8c53': 'duplicate-trace-key',
    '035b200d41bfb1ee7fa3cf1cd861d523f18f17ba92859723e3f433cc208eb2ca': 'prior-post',
    '2e58bd83ca5682829e4a9e88f4fb3a5a86e3a800fbbff9a60db0777b3a799a6a': 'prior-lock',
    '453600c91ff320507a4ce8fd457129787476760a02c3dad7a21630c16935d3ed': 'wrong-document',
}


def apply_revisions(schedule, revisions, catalogs):
    check({r['revised_sha256'] for r in revisions} == set(APPLIES_TO), 'r6-source-revision-inventory')
    result=deepcopy(schedule); changes=[]
    for slot in result:
        for revision in revisions:
            control=APPLIES_TO[revision['revised_sha256']]
            if slot['source']['sha256'] == revision['original_sha256'] and slot['control'] == control:
                slot['source']['sha256']=revision['revised_sha256']
                changes.append({'slot_id':slot['id'], **revision, 'applies_to_control':control})
        source=slot['source']['sha256']; catalog=catalogs['sources'][source]['catalog']; verify(catalog)
        check(catalog['source_sha256']==source,'r6-catalog-source')
        slot['source'].update(compiled=True, native_qualified_here=False,
                             compilation_record_sha256=catalog['compilation_record_sha256'],
                             class_catalog_sha256=catalog['content_sha256'])
        if slot['control']=='duplicate-trace-key':
            slot['expected'].update(equipment_suspect=True,delivery='empty')
    return result,changes


def revise(draft, summary, catalogs, classpath_audit, private_manifest):
    for value in (draft,catalogs,classpath_audit,private_manifest):verify(value)
    verify({k:v for k,v in summary.items() if k!='signature'})
    check(summary['content_sha256']==SUMMARY,'r6-compilation-summary')
    result=deepcopy(draft);result.pop('content_sha256');result.pop('signature',None)
    result['schedule'],changes=apply_revisions(draft['schedule'],summary['source_revisions'],catalogs)
    check({s['id'] for s in result['schedule']} == set(private_manifest['slots']), 'r6-private-slot-set')
    for slot in result['schedule']:
        check(private_manifest['slots'][slot['id']]['inputs_sha256']['operations.java']==slot['source']['sha256'],
              'r6-private-source-binding')
    result.update(artifact_type='ms94-b06-qualification-assembly-specification/6',
        previous_assembly_sha256=draft['content_sha256'],source_revisions=changes,
        source_revision_applicability=APPLIES_TO,compilation_summary_sha256=SUMMARY,
        private_assembly_sha256=private_manifest['content_sha256'],
        classpath_audit_sha256=classpath_audit['content_sha256'],executable_snapshot_sha256=None,
        status='blocked-before-executable-conversion',
        execution_blockers=['Resolved Tycho/OSGi loaded terminal class identity is unavailable.'],
        qualification_decision_kind='b06-qualification-group',native_pairs=0,model_calls=0,
        measurement_authorized=False,docker_runs_authorized=False)
    return seal(result)
