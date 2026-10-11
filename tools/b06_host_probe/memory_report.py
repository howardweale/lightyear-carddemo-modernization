"""Summarize public host measurements without exporting raw event payloads."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re

from tools.b06_host_probe.native_memory import digest


def linear_fit(samples, minimum_event, at_event=231158):
    rows = [r for r in samples if r['events'] >= minimum_event]
    if len(rows) < 2:
        raise ValueError('insufficient-heap-samples')
    xs = [r['events'] for r in rows]
    ys = [r['heap_used_after_gc'] for r in rows]
    mx, my = sum(xs)/len(xs), sum(ys)/len(ys)
    denominator = sum((x-mx)**2 for x in xs)
    if denominator == 0:
        raise ValueError('heap-sample-events-not-distinct')
    slope = sum((x-mx)*(y-my) for x,y in zip(xs,ys))/denominator
    intercept = my-slope*mx
    return dict(first_event=xs[0], last_event=xs[-1], sample_count=len(rows),
                bytes_per_event=slope, intercept_bytes=intercept,
                at_event=at_event, fitted_bytes=intercept+slope*at_event)


def histogram(text):
    rows = []
    for line in text.splitlines():
        match = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(.+)', line)
        if match:
            rows.append(dict(instances=int(match[1]), shallow_bytes=int(match[2]), class_name=match[3]))
    return sorted(rows, key=lambda r:r['shallow_bytes'], reverse=True)


def distribution(values):
    ordered = sorted(values); n = len(ordered)
    return dict(count=n, min=ordered[0], median=ordered[n//2],
                p90=ordered[int((n-1)*.9)], p99=ordered[int((n-1)*.99)], max=ordered[-1])


def summarize(folder):
    result = json.loads((folder/'result.json').read_text())
    # Bind the report to the actual completed host output, not edited aggregates.
    for name in ('heap.csv', 'observer.stdout', 'observer.stderr', 'peak-histogram.txt'):
        if digest(folder/name) != result['output_sha256'][name]:
            raise ValueError('memory-report-hash-mismatch: '+name)
    with (folder/'heap.csv').open() as stream:
        samples = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]
    if samples != result['heap_samples']:
        raise ValueError('memory-report-sample-mismatch')
    sizes = defaultdict(list); counts = Counter()
    with (folder/'observer.stdout').open('rb') as stream:
        while line := stream.readline(4*1024*1024+1):
            if len(line)>4*1024*1024:
                raise ValueError('host-record-bound')
            event = json.loads(line); counts[event['kind']] += 1
            if event['kind'] != 'generation-entry':
                continue
            record = event['record']
            sizes['entry_bytes'].append(len(line))
            sizes['depth'].append(record['entry_depth'])
            sizes['definition_input_bytes'].append(len(record.get('definition_input_hex',''))//2)
            for name in ('lambda_form_graph', 'class_data_graph'):
                if isinstance(record.get(name), dict):
                    sizes[name+'_nodes'].append(len(record[name].get('nodes',{})))
    stderr = (folder/'observer.stderr').read_text()
    fits = [linear_fit(samples, start) for start in (1000, 50000, 100000, 150000, 200000)]
    gate = result['oom_reproduced'] or any(f['fitted_bytes']>=192*1024**2 for f in fits)
    return dict(schema='b06-host-memory-report/1', host_only=True, model_calls=0,
                qualification_credit=False, measurement_credit=False,
                baseline_gate_met=gate, completed_workload=result['workload_completed'],
                oom_reproduced=result['oom_reproduced'],
                termination=('structural-audit-bound' if 'observer structural audit bound exceeded' in stderr
                             else 'other; inspect local stderr'),
                elapsed_seconds=result['elapsed_seconds'], observer_heap_bytes=192*1024**2,
                event_counts=dict(counts), payload_sizes={k:distribution(v) for k,v in sizes.items()},
                last_sample=samples[-1], peak_after_gc_bytes=result['sample_peak'],
                suppressed_fraction=samples[-1]['suppressed_returns']/counts['generation-entry'],
                ordinary_least_squares_fits=fits,
                histogram_semantics='shallow live class totals; not dominator retained sizes',
                largest_live_classes=histogram((folder/'peak-histogram.txt').read_text())[:10],
                observer_source_sha256=result['observer_source_sha256'],
                compiled_observer_sha256=result['compiled_observer_sha256'],
                local_result_sha256=digest(folder/'result.json'),
                local_output_sha256=result['output_sha256'])


def plot(samples, out):
    # Optional reporting dependency; neither the runner nor tests need matplotlib.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9,4.8), layout='constrained')
    ax.plot([r['events'] for r in samples], [r['heap_used_after_gc']/1024**2 for r in samples],
            color='#126b91', label='Measured after GC (every 1,000 events)')
    ax.axhline(192, color='#9b3434', linestyle='--', label='192 MiB heap limit')
    ax.axvline(231158, color='#555555', linestyle=':', label='r3 failure event count')
    ax.set(xlabel='Emitted host events', ylabel='Heap used (MiB)', ylim=(0,205),
           title='Unchanged observer: host baseline stopped at audit cap, not OOM')
    ax.legend(loc='upper left', fontsize=9); ax.grid(alpha=.18)
    fig.savefig(out, dpi=160); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plot', type=Path)
    args = parser.parse_args()
    report = summarize(args.folder)
    with args.out.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(report,stream,indent=2); stream.write('\n')
    if args.plot:
        if args.plot.exists():
            raise ValueError('memory-plot-already-exists')
        with (args.folder/'heap.csv').open() as stream:
            plot([{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)], args.plot)
