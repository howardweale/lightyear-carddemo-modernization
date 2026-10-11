"""Validate every new host input witness and preserve the unchanged r6 decision."""
from collections import Counter
import json
from pathlib import Path
from tools.b06_host_probe.bounded_report import summarize
from tools.b06_host_probe.alternatives_partition import classify
from tools.ms94_b06_generation_inputs import validate


def witness_counts(path):
    counts=Counter();total=0;size=0;maximum=0
    with Path(path).open('rb') as stream:
        for line in stream:
            if len(line)>4*1024*1024:raise ValueError('host-event-size')
            event=json.loads(line)
            if event.get('kind')!='generation-entry':continue
            event=event.get('record',{})
            validate(event)
            if 'class_input_witness' not in event:raise ValueError('missing-input-witness')
            label,_=classify(event);counts[label]+=1;total+=1
            n=len(json.dumps(event['class_input_witness'],sort_keys=True,separators=(',',':')).encode())
            size+=n;maximum=max(maximum,n)
    if total==0:raise ValueError('empty-host-generation-stream')
    return dict(policy='generation-inputs-v1',validated_generation_entries=total,counts=dict(counts),missing=0,
        max_json_bytes=maximum,mean_json_bytes=size/total,caller_stack_used_as_input=False,
        unresolved_bytecode_is_not_application_class_identity=True)


def report(folder):
    folder=Path(folder);result=summarize(folder);witnesses=witness_counts(folder/'observer.stdout')
    if witnesses['validated_generation_entries']!=result['generation_entries']:raise ValueError('witness-count-mismatch')
    manifest=json.loads((folder/'manifest.json').read_text())
    expected=dict(threads=3,iterations_per_thread=1400,distinct_stack_fixture_classes=3000,stack_fixture_depth=100,
        observer_heap_mib=192,suppression_eligible_return_interval=200,
        harness_sha256='3c44b166ef53b717a03b574c633b9ba7fdd648c57893c8dd6dd29d6e92890eff',
        fixture_sha256='cd3d85aa005fa1a4ac0c9826409d00f9287a21b7c6baaf5b2447df4ae4472b76',
        generated_fixture_sha256='fb59d9e56e587d5b1c7312f5324545e86da1cf56a602b4242ce8ce25a54cb6b9')
    if any(manifest.get(k)!=v for k,v in expected.items()):raise ValueError('r6-workload-changed')
    result.update(input_witnesses=witnesses,workload=expected,
        baseline_observer_source_sha256='02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b',
        comparison=dict(same_target_fixture=True,same_generated_stack_fixture=True,same_harness=True,
            same_threads_iterations_heap_suppression=True,native_performance_claim=False))
    return result
