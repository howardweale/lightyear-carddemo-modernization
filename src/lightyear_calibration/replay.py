"""Reproducible paired-source replay; retained results are never overwritten."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json

from lightyear_common.io import normalize_logical_source
from lightyear_data.idempiere_comparison import compare_pair as original_compare, _totals
from .adapters import import_idempiere, gate_identity, sql_records, safe_path, MAX_FILE, MAX_CORPUS
from .contracts import digest, require, seal
from .instrument import build_report, compare_reports
from .reporting import publish, esc
from .sql_gate import compare_pair
from .sql_context import baseline, admit


def _states(result,lane):
    return [(s['category'],tuple(s['outcomes'])) for s in result['segments'][lane]
            for _ in range(s['first_unit'],s['last_unit']+1)]


def replay_idempiere(source,retained,manifest,output, *, context=None, catalogs=None):
    require(not output.exists(),'Output already exists; choose a new evidence directory')
    require(not output.resolve().is_relative_to(source.resolve()),'Keep replay output outside the source corpus')
    before_snapshot=import_idempiere(retained,manifest)
    originals={r['pair_id']:r for r in retained['results']}
    source=source.resolve()
    texts={};inputs=[];size=0
    import hashlib
    # Admit and bind every byte before running any comparison. Source text never
    # enters the published report; input hashes and locators do.
    for pair in sorted(manifest['pairs'],key=lambda p:p['pair_id']):
        cid=pair['pair_id'];texts[cid]={};item={'case_id':cid}
        for lane,side in (('oracle','source'),('postgresql','target')):
            path=safe_path(source,pair[lane]['path'])
            with path.open('rb') as f:raw=f.read(MAX_FILE+1)
            require(len(raw)<=MAX_FILE,'Input file exceeds bound')
            size+=len(raw);require(size<=MAX_CORPUS,'Corpus exceeds bound')
            raw=normalize_logical_source(raw)
            require(hashlib.sha256(raw).hexdigest()==pair[lane]['logical_sha256'],'Pinned source hash mismatch: '+pair[lane]['path'])
            texts[cid][side]=raw.decode('utf-8')
            item[side]={'path':pair[lane]['path'],'sha256':pair[lane]['logical_sha256']}
        inputs.append(item)
    if context is not None:
        admit(context,before_snapshot['corpus_sha256'],inputs)
        if context['evidence']['mode']=='captured-catalog':
            from .native_catalog import context_from_captures
            require(catalogs is not None, 'Captured context requires both raw native catalogs')
            template=baseline({'corpus_sha256':before_snapshot['corpus_sha256'],'provenance':{'inputs':inputs}},texts)
            require(context == context_from_captures(template,catalogs), 'Context differs from native catalog projection')
    require(catalogs is None or context is not None and context['evidence']['mode']=='captured-catalog', 'Catalogs require captured context')
    after_snapshot=deepcopy(before_snapshot)
    after_snapshot.update(gate=gate_identity('oracle-postgresql-sql'),cases=[],records=[])
    after_snapshot['provenance']={'mode':'pinned-source-gate-replay','runtime_invocations':0,'source_authentication':'not-established',
        'source_commit':manifest['source']['commit'],'pairing_manifest_sha256':manifest['content_sha256'],
        'inputs':inputs,'scope':'identical paired current SQL migration files; static declared effects, no native execution'}
    if context is not None:
        after_snapshot['gate']['context_sha256']=digest(context)
        after_snapshot['provenance']['context_evidence']=context['evidence']
    results=[];parser_results=[];control_results=[];transitions=Counter();changed=[];lost=[]
    for item in inputs:
        cid=item['case_id'];args=(cid,texts[cid]['source'],texts[cid]['target'])
        old=original_compare(*args)
        require(old==originals[cid],'Retained gate does not reproduce the baseline: '+cid)
        parsed=compare_pair(*args,prefix_alignment=False);parser_results.append(parsed)
        if context is not None:control_results.append(compare_pair(*args))
        after=compare_pair(*args,context_case=context['cases'][cid] if context is not None else None,
                           context_enabled=context is not None and context['evidence']['mode']!='template');results.append(after)
        for lane in ('oracle','postgresql'):
            b,a=_states(old,lane),_states(after,lane)
            require(len(b)==len(a),'Statement denominator changed')
            for ordinal,(left,right) in enumerate(zip(b,a),1):
                transitions[(left[0],right[0])]+=1
                if left!=right:
                    if right[0]=='parsed-and-compared' or left[0]=='parsed-and-compared':
                        changed.append({'case_id':cid,'lane':lane,'ordinal':ordinal,'before':left[0],'after':right[0],
                                        'before_outcomes':list(left[1]),'after_outcomes':list(right[1])})
                if left[0]=='parsed-and-compared' and right[0]!='parsed-and-compared' or 'divergent' in left[1] and 'divergent' not in right[1]:
                    lost.append({'case_id':cid,'lane':lane,'ordinal':ordinal})
        after_snapshot['cases'].append({'id':cid,'verdict':after['verdict']})
        after_snapshot['records'].extend(sql_records(after,{lane:item[side] for lane,side in (('oracle','source'),('postgresql','target'))}))
    before_report=build_report(before_snapshot)
    after_report=build_report(after_snapshot)
    comparison=compare_reports(before_report,after_report)
    acquisition=baseline(after_snapshot,texts)
    counts={'before':retained['statistics']['coverage_combined'],
            'parser_only':_totals(parser_results)['coverage_combined'],
            'after':_totals(results)['coverage_combined']}
    if context is not None:counts['current_gate_without_context']=_totals(control_results)['coverage_combined']
    measurement=seal({'schema_version':'1.0','artifact_type':'lightyear-calibration-measurement',
        'source_commit':manifest['source']['commit'],'corpus_sha256':before_snapshot['corpus_sha256'],
        'pairing_manifest_sha256':manifest['content_sha256'],'retained_report_sha256':retained['content_sha256'],
        'before_report_sha256':before_report['content_sha256'],'after_report_sha256':after_report['content_sha256'],
        'gate':after_snapshot['gate'],'baseline_reproduced':True,'counts':counts,
        'case_counts':{'before':retained['statistics']['verdicts'],'after':_totals(results)['verdicts'],'total':len(results)},
        'statement_denominator_unchanged':True,'unit_transitions':[{'before':b,'after':a,'units':n} for (b,a),n in sorted(transitions.items())],
        'changed_decisions':changed,'lost_decisions_or_divergences':lost,
        'context_baseline_sha256':digest(acquisition),'context_mode':context['evidence']['mode'] if context is not None else 'acquisition-template-not-runtime-facts',
        'applied_context_sha256':digest(context) if context is not None else None,
        'schema_session_inventory':{'cases':len(acquisition['cases']),
           'table_references':sum(len(lane['tables']) for case in acquisition['cases'].values() for lane in case['lanes'].values()),
           'observed_declarations':sum(len(lane['observed_declarations']) for case in acquisition['cases'].values() for lane in case['lanes'].values()),
           'complete_catalogs':len(catalogs) if catalogs else 0,'verified_sessions':len(catalogs) if catalogs else 0},
        'unresolved_causes':[{'reason':c['reason_code'],'units':c['units']} for c in after_report['causes']],
        'normalization_rules_applied':0,'native_execution':False,'application_equivalence':False,
        **({'context_application_scope':'conditional static comparison on one observed imported baseline; historical entry states not established',
            'native_migration_execution':False,'native_catalog_capture':True,
            'catalog_capture_sha256':{lane:cap['content_sha256'] for lane,cap in catalogs.items()},
            'context_lift_units':counts['after']['parsed-and-compared']-counts['current_gate_without_context']['parsed-and-compared']} if catalogs else {})})
    require(not lost,'Replay lost a prior decision or divergence; publication requires investigation')
    output.mkdir(parents=True)
    publish(before_report,output/'before');publish(after_report,output/'after')
    for name,value in [('measurement.json',measurement),('comparison.json',comparison),('schema-session-baseline.json',acquisition)]:
        (output/name).write_text(json.dumps(value,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    if context is not None:
        (output/'context-used.json').write_text(json.dumps(context,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    write_summary(measurement,output)
    return measurement


def write_summary(m,output):
    c=m['counts'];b=c['before'];a=c['after'];p=c['parser_only']
    native = m.get('native_catalog_capture', False)
    current = c.get('current_gate_without_context', b)
    headline_before = current['parsed-and-compared'] if native else b['parsed-and-compared']
    headline_lift = a['parsed-and-compared'] - headline_before
    lift_label = 'Native context lift' if native else 'Actual lift'
    lines=['# iDempiere calibration: measured before and after','',
        f"Same pinned source, same {m['case_counts']['total']:,} file pairs, same {a['sql_units']:,} in-scope SQL units across Oracle and PostgreSQL.",'',
        '| Count | Before | Parser extensions | Calibrated gate |',
        '|---|---:|---:|---:|']
    for label,key in [('Decided units','parsed-and-compared'),('Parsed but indeterminate','parsed-but-indeterminate'),('Unsupported units','unparsed'),('In-scope units','sql_units'),('Administrative exclusions','administrative_units_excluded')]:
        lines.append(f'| {label} | {b[key]:,} | {p[key]:,} | {a[key]:,} |')
    lines+=['',f"**{lift_label}: {headline_lift:,} additional decided units.** "
        + (f"The unchanged current gate decides {headline_before:,} units without context. The table also retains the older baseline; its four-unit calibration improvement predates this experiment. " if native else '')
        +
        f"Unsupported units fell by {b['unparsed']-a['unparsed']:,}. No prior decision or divergence was lost.",'',
        'Parsing more syntax is not the same as deciding more behavior. The parser-only column isolates that distinction. '
        'The final column also compares an unambiguous positional prefix before the first unknown or mismatched effect, plus an explicitly supplied context if present. It never searches ahead or drops unmatched operations.','',
        f"Complete pairs: {m['case_counts']['after']['equivalent']:,} equivalent, {m['case_counts']['after']['divergent']:,} divergent, {m['case_counts']['after']['indeterminate']:,} indeterminate. This is still insufficient for a customer equivalence claim.",'',
        f"Applied context hash: {m['applied_context_sha256'] or 'none'}. Context mode: {m['context_mode']}. "
        + ('Native metadata observations are bound to this replay; they are not independently attested or historical entry-state proof.' if m.get('native_catalog_capture') else 'Context contracts do not authenticate runtime state.'),'',
        '## Schema and session baseline','',
        'The generated baseline binds every case and input hash, lists required tables and columns, and retains source-located DDL declarations. '+
        ('The acquisition template leaves catalog and session facts unknown. The applied context uses the separately retained native captures. ' if m.get('native_catalog_capture') else 'Catalog completeness, triggers, constraints, row policies, rewrite rules and session settings remain explicitly unknown. ')+
        'A declaration found in a migration is not the catalog at entry to another migration. '
        'Customer catalog/session evidence must fill those facts before the numeric DML comparison can use them.','',
        '| Remaining cause (counts overlap) | Units |','|---|---:|']
    lines += [f"| {v['reason']} | {v['units']:,} |" for v in m['unresolved_causes'][:12]]
    lines +=['','## Evidence','',f"Source commit: `{m['source_commit']}`.",
              f"Measurement hash: `{m['content_sha256']}`.",
              'The retained baseline was reproduced from source before measuring the new gate. No normalization rule was applied, no customer system was invoked, and no application-equivalence claim is made.','',
              'The full replay bundle contains before/after reports, source-bound changes, a schema/session acquisition baseline, and the report comparison. '
              'Compressed report ranges change when causes change; the generic comparison flags that partition change. This replay separately checks the unchanged statement ordinals and records every changed decision.']
    if m.get('native_catalog_capture'):
        lines += ['', '## Native context increment', '',
                  f"The unchanged current gate without context decides {c['current_gate_without_context']['parsed-and-compared']:,} units. "
                  f"The captured context changes that by {m['context_lift_units']:+,} units.", '', m['context_application_scope']+'.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    rows=''.join(f'<tr><td>{esc(label)}</td><td>{b[key]:,}</td><td>{p[key]:,}</td><td>{a[key]:,}</td></tr>' for label,key in
        [('Decided','parsed-and-compared'),('Indeterminate','parsed-but-indeterminate'),('Unsupported','unparsed'),('In scope','sql_units')])
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>iDempiere calibration results</title><style>body{{font:18px/1.6 system-ui;max-width:1050px;margin:50px auto;padding:0 24px;color:#163044}}h1{{font-size:40px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:14px;border-bottom:1px solid #ccd4dc;text-align:left}}.metric{{font-size:32px;color:#245e49}}code{{overflow-wrap:anywhere}}</style>
<h1>{'Does native context raise decidability?' if native else 'Does calibration raise decidability?'}</h1><p class="metric">{headline_before:,} → {a['parsed-and-compared']:,} decided SQL units</p>
<p>Measured on the same {a['sql_units']:,} in-scope units and {m['case_counts']['total']:,} paired migration files.</p>
<table><tr><th>Units</th><th>Before</th><th>Parser extensions</th><th>Calibrated gate</th></tr>{rows}</table>
<h2>What this proves</h2><p>{esc(lift_label)}: {headline_lift:,} additional decisions. {'The four-unit improvement over the older baseline in the table predates the native context experiment.' if native else f'Unsupported syntax fell by {b["unparsed"]-a["unparsed"]:,} units.'} No previous decision or divergence was lost.</p>
<h2>What still blocks useful coverage</h2><p>Context mode: {esc(m['context_mode'])}. Schema, session, trigger and expression obligations remain explicit. {m['case_counts']['after']['indeterminate']:,} complete pairs remain indeterminate.</p>
<p>This is a source comparison, not a customer runtime test or a proof of application equivalence.</p>
<p><a href="report.md">Full explanation and causes</a> · <a href="measurement.json">Measured counts and changed decisions</a></p>
<p><small>Pinned source: <code>{m['source_commit']}</code></small></p></html>'''
    (output/'index.html').write_text(page,encoding='utf-8')
