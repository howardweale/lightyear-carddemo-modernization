"""Derive a narrow posting cause from replayed JDI + SQL, never trace assertions.

The derivation is prospective until its native controls pass. A PO.lock flag is
not a database row lock. Prior posting without a support failure earns no fault.
"""
from lightyear_calibration.b06_posting_probe import TABLES
from tools.ms94_b06_posting_replay import SUPPORT
from tools.ms94_b06_admission import check


def derive(replayed, lock_sql_binding):
    check(replayed['collection_complete'] is True, 'cause-incomplete-observer')
    from tools.ms94_b06_lock_sql import render
    observations, exceptions, readbacks = (replayed[k] for k in ('observations', 'exceptions', 'readbacks'))
    # Even a caught JDBC/VM error defeats causal exclusion. SQL row count and
    # SELECT 1 alone do not prove absence of a genuine equipment fault.
    if any(any(name.startswith(('java.sql.', 'org.postgresql.', 'oracle.jdbc.')) or
                   name in ('java.lang.VirtualMachineError', 'java.lang.LinkageError')
                   for name in e['exception_ancestry']) for e in exceptions):
        return {'cause': 'non-candidate-fault', 'equipment_suspect': True}

    def row(event):
        capture = readbacks.get(event['sequence'])
        check(capture is not None, 'cause-missing-native-readback')
        rows = capture['results']['document']['rows']
        check(len(rows) == 1 and rows[0]['record_id'] == event['document'][1], 'cause-document-ambiguous')
        return rows[0]

    failures = [o for o in observations if o['entry']['frames'][0]['class'] == 'org.compiere.util.DB'
                and o['exit']['return_value'] == 0]
    for failed in failures:
        entry, exit = failed['entry'], failed['exit']
        key, thread = entry['document'], entry['thread']
        table = TABLES[key[0]]
        # Exact SQL and arguments produced by the bound Doc.post bytecode.
        expected = render(lock_sql_binding, table, key[1])
        check(entry.get('sql', '').lower() == expected.lower(), 'cause-lock-sql-template-differs')
        if (entry.get('force') is not False or entry.get('repost') is not False or
                failed['origin'] != 'support'):
            continue
        state = row(entry)
        if not (state['processing'] == 'Y' and state['processed'] == 'Y' and
                state['isactive'] == 'Y' and state['posted'] in ('N', 'd')):
            continue
        support_failures = [e for e in exceptions if e['thread'] == thread and e['sequence'] > exit['sequence']
                            and any(f['class'] == SUPPORT for f in e['frames']) and e['unwound_calls']
                            and (e.get('catch_location') is None or
                                 not e['catch_location']['class'].startswith('org.idempiere.test.'))]
        for failure in support_failures:
            # Locate the actual unwound support entry, not a caught earlier error.
            support = next((readbacks[n] for n in failure['unwound_calls']
                            if n in readbacks and readbacks[n]['document'] == key and n < entry['sequence']
                            and replayed['entries'][n]['frames'][0]['class'] == SUPPORT
                            and replayed['entries'][n]['thread'] == thread), None)
            if support is None:
                continue
            support_seq = support['event_sequence']
            for prior in observations:
                a, b = prior['entry'], prior['exit']
                if not (prior['origin'] == 'candidate' and a['document'] == key and a['thread'] == thread and
                        a['frames'][0]['class'] == 'org.compiere.model.PO' and a['frames'][0]['method'] == 'lock' and
                        b['return_value'] is True and b['sequence'] < support_seq):
                    continue
                old, new = row(a), row(b)
                support_rows = support['results']['document']['rows']
                if (old['processing'] not in (None, 'N') or new['processing'] != 'Y' or
                        len(support_rows) != 1 or support_rows[0]['processing'] != 'Y'):
                    continue
                # Reject intervening document operations; attribution is deliberately narrow.
                if any(o is not prior and b['sequence'] < o['entry']['sequence'] < support_seq and
                       o['entry']['document'] == key for o in observations):
                    continue
                return {'cause': 'candidate-prior-processing-flag', 'equipment_suspect': False,
                        'document_key': key, 'posting_step': 'JourneySupport.postOnce',
                        'sequences': [a['sequence'], b['sequence'], support_seq, entry['sequence'],
                                      exit['sequence'], failure['sequence']],
                        'capture_sha256': [readbacks[n]['content_sha256'] for n in
                                           (a['sequence'], b['sequence'], support_seq, entry['sequence'], exit['sequence'])]}
    if exceptions:
        return {'cause': 'unattributed-failure', 'equipment_suspect': True}
    return {'cause': 'no-posting-failure', 'equipment_suspect': False}


def replay_cause(root, run, lane, public_key):
    """Production entry: full entry, signatures, bound bytecode and SQL replay first."""
    from tools.ms94_b06_posting_replay import replay
    result = replay(root, run, lane, public_key)
    from lightyear_calibration.contracts import read_json
    from pathlib import Path
    execution = read_json(Path(run) / 'cases/operations/1/execution' / lane / 'execution.json')
    from tools.ms94_b06_admission import bound_file
    from tools.ms94_b06_lock_sql import bind
    plan = read_json(Path(run) / 'plan.json')
    spec = plan['posting_observer']['lock_sql']
    check(plan['posting_observer']['target_class_files_sha256'].get(spec['class_file']) == spec['class_sha256'],
          'cause-lock-class-not-in-catalog')
    binding = bind(bound_file(root, spec['class_file'], spec['class_sha256']).read_bytes(), spec)
    cause = derive(result, binding)
    if cause['cause'] == 'candidate-prior-processing-flag':
        check(execution['exit_code'] != 0, 'cause-not-a-terminal-execution-failure')
    return {**cause, 'lock_sql_binding_sha256': binding['content_sha256'], 'entry_sha256': result['entry_sha256'],
            'collector_receipt_sha256': result['receipt_sha256'],
            'observer_replayed': True, 'attribution_qualified': False,
            'diagnostics': []}  # Native control qualification remains a launch prerequisite.
