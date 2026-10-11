"""Hash-only conservative quota projection; never rewrites or qualifies evidence."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from lightyear_calibration.contracts import read_json,verify
from lightyear_control_tower.decisions import verify_envelope
from tools.b06_host_probe.compact_diagnostics import encode
from tools.ms94_b06_observer_format import java_json
from tools.ms94_b06_engineering import attempt_limits

DIAGNOSTIC={'observer-audit','breakpoint-lifecycle','watched-class-prepare','observer-heap-telemetry'}

def native_counts(folder,public_key):
    folder=Path(folder);census=read_json(folder/'frame-census.json');failure=read_json(folder/'failure.json')
    for envelope in (census,failure):
        if not verify_envelope(envelope,public_key) or envelope['complete'] is not False:raise ValueError('projection-signature')
    counts=Counter();digest=hashlib.sha256();previous=None;events=0;wire_bytes=0;raw_bytes=0;max_pending=0
    with (folder/'events.jsonl').open('rb') as stream:
        while line:=stream.readline(4*1024*1024+1):
            if len(line)>4*1024*1024:raise ValueError('projection-line-cap')
            digest.update(line);raw_bytes+=len(line);row=json.loads(line);verify(row);event=row['event'];events+=1
            if event['sequence']!=events or row['previous_sha256']!=previous:raise ValueError('projection-chain')
            previous=row['content_sha256'];counts[event['kind']]+=1
            if event['kind']=='observer-audit':
                # Deliberately retain every old audit row and its complete pending
                # list rather than claiming the new coalescing reduction.
                wire_bytes+=len(java_json(encode(event)).encode())
                pending=event.get('detail',{}).get('pending',[])
                if isinstance(pending,list):max_pending=max(max_pending,len(pending))
    for envelope in (census,failure):
        if events!=envelope['event_count'] or previous!=envelope['last_event_sha256']:raise ValueError('projection-tail')
    if digest.hexdigest()!=census['event_file_sha256'] or census['plan_sha256']!=failure['plan_sha256']:raise ValueError('projection-binding')
    return dict(stream_sha256=digest.hexdigest(),census_sha256=census['content_sha256'],failure_sha256=failure['content_sha256'],
        signatures_verified=2,rows=events,counts=dict(counts),generation_entries=counts['generation-entry'],
        raw_bytes=raw_bytes,all_old_audit_rows_compressed_bytes=wire_bytes,observed_max_pending_entries=max_pending)

def project(native,host,target=37000):
    n=native['generation_entries'];h=host['generation_entries']
    if min(n,h)<=0:raise ValueError('projection-empty')
    ordinary=max(sum(v for k,v in native['counts'].items() if k not in DIAGNOSTIC)/n,
                 sum(v for k,v in host['event_counts'].items() if k not in DIAGNOSTIC)/h)
    # Add ALL host metadata to ALL old native audit rows. This double-counts
    # shared audit work but leaves room for new lifecycle/telemetry rows.
    records=native['counts'].get('observer-audit',0)/n+host['diagnostic_records']/h
    metadata=native['all_old_audit_rows_compressed_bytes']/n+host['diagnostic_bytes']/h
    # Preserve old full native payload sizes plus all new metadata and a 2 KiB
    # input witness allowance per entry, with a heap dump and fixed index reserve.
    output=native['raw_bytes']/n+host['diagnostic_bytes']/h+2048
    fixed=1536*1024**2+12*1024**2+1024*1024**2
    pending=max(native['observed_max_pending_entries']/n,host['last_sample']['pending']/h)
    rates=dict(ordinary_records=ordinary,metadata_records=records,metadata_bytes=metadata,output_bytes=output,pending_entries=pending)
    attempts=[]
    for number in (1,2):
        limits=attempt_limits(number)
        stop=dict(ordinary_records=int(limits['evidence_records']/ordinary),metadata_records=int(limits['audit_records']/records),
                  metadata_bytes=int(limits['audit_bytes']/metadata),output_bytes=int((limits['output_bytes']-fixed)/output),
                  pending_entries=int(limits['pending_cap']/pending) if pending else None)
        attempts.append(dict(attempt=number,mode=['strict','diagnostic-unmatched-return'][number-1],limits=limits,
            projected_stopping_points=stop,projected_first_resource=min(v for v in stop.values() if v is not None),
            projected_reaches_target=all(v is None or v>=target for v in stop.values())))
    return dict(schema='b06-oct13-cap-projection/1',target_generation_entries=target,native_prefix=native,
        host_baseline_sha256=hashlib.sha256(json.dumps(host,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        host_source_sha256=host['observer_source_sha256'],host_generation_entries=h,rates_per_generation=rates,
        projected_target=dict(ordinary_records=ordinary*target,metadata_records=records*target,metadata_bytes=metadata*target,
            output_bytes=output*target+fixed,pending_entries=pending*target),fixed_output_reserve_bytes=fixed,attempts=attempts,
        native_payload_tail_bound_proven=False,statistical_upper_confidence_bound=False,
        limitations=['Linear count/byte projections are scenario estimates, not worst-case bounds.',
          'All old native audit rows are retained in the compression estimate; new audit coalescing savings are not assumed.',
          'All host metadata is added as an allowance; this double-counts shared work.',
          'Native time to 37000, future payload tails, retention and first anomaly are not predicted.',
          'Strict mode or diagnostic cap10 can stop before any projected resource limit.',
          'Non-stream baseline/capture/log overhead is unmeasured; 1GiB is a scenario reserve, not a proven bound.',
          'No cap is automatically extended; output8GiB and free60GiB guards remain authoritative.'],
        native_run_authorized=False,qualification_credit=False,measurement_credit=False,model_calls=0)
