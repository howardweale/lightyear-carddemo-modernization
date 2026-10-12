"""Prospective report skeleton: absence of native evidence never identifies cause."""
from lightyear_calibration.contracts import seal
from tools.ms94_b06_oct13_authorization import validate_request,CAUSE_CRITERIA

def template(request):
    validate_request(request)
    return seal(dict(artifact_type='b06-oct13-report-template/1',request_sha256=request['content_sha256'],
        implementation_commit=request['implementation_commit'],observer_source_sha256=request['observer_source_sha256'],
        qualification_credit=False,measurement_credit=False,model_calls=0,
        attempts=[dict(number=i,mode=mode,status='not-run',consumed=False,owner=None,
            generation_entries=None,first_unmatched_return_sequence=None,unmatched_returns=None,
            ordinary_records=None,metadata_records=None,metadata_bytes=None,output_bytes=None,
            peak_heap_bytes=None,guard_receipt_sha256=None,heap_dump_sha256=None,cleanup_verified=None,
            lifecycle_or_class_prepare_at_first_unmatched=[],application_phase_operations=[],
            input_witness_classification_counts={},signed_terminal_sha256=None,archive_sha256=None)
            for i,mode in enumerate(request['attempt_modes'],1)],
        cause_identified_criteria=CAUSE_CRITERIA,cause_identified=False,
        criterion_a={'supported':False,'attempt':None,'first_unmatched_sequence':None,'record_sequence':None,
                     'record_sha256':None,'explanation_kind':None,'explanation':None},
        criterion_b={'supported':False,'same_operation':None,'attempt1_phase_record_sha256':None,
                     'attempt2_phase_record_sha256':None,'attempt1_generation_entries':None,'attempt2_generation_entries':None},
        adjudication='No native evidence yet; no cause identified.',
        next_action='After two consumed attempts, stop observer repair. If neither preregistered criterion is supported, Howard selects an alternative.',
        native_run_authorized=False))
