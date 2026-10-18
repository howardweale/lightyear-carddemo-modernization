"""Dated CardDemo evidence with the full unsupported-case denominator."""
from hashlib import sha256
import json
from pathlib import Path
import re


def latest(root, schema="carddemo-slice-evidence/2"):
    paths=sorted(p for p in (Path(root)/'docs/modernization').glob('carddemo-slice-1-*.json')
                 if re.fullmatch(r'carddemo-slice-1-\d{4}-\d{2}-\d{2}\.json',p.name))
    return next((p for p in reversed(paths) if json.loads(p.read_bytes()).get("schema")==schema), None)


def load(root):
    path=latest(root)
    if path is None:return None
    value=json.loads(path.read_bytes())
    if value.get('schema')!='carddemo-slice-evidence/2':return None
    body={k:v for k,v in value.items() if k!='content_sha256'}
    if sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=value['content_sha256']:
        raise ValueError('carddemo-status-receipt-hash')
    volume=value['volume'];ims=value['migrated_ims']
    if (sum(f['records'] for f in volume['files'])!=volume['records']
        or sum(f['browse']['compared'] for f in volume['files'])!=volume['browse_compared']
        or sum(f['browse']['matched'] for f in volume['files'])!=volume['browse_matched']
        or ims['adapter_cases']+ims['unsupported']!=ims['total']
        or len(value['unsupported_ims'])!=ims['unsupported']
        or not 0<=ims['matched']<=ims['adapter_cases']
        or not value['durable_asset']['download_verified']):
        raise ValueError('carddemo-status-denominator')
    return dict(value,path=path.relative_to(root).as_posix())


def paragraph(value):
    if value is None:return 'Current dated CardDemo data evidence is unavailable; screen and native IMS acceptance remain unproved.'
    v=value['volume'];i=value['migrated_ims'];s=value['screens']
    return (f"{v['records']:,} generated records; {v['browse_matched']}/{v['browse_compared']} volume browse comparisons; "
            f"{v['byte_key_edges']['matched']}/{v['byte_key_edges']['compared']} byte-key edge comparisons. "
            f"Migrated IMS adapter: {i['matched']}/{i['total']} corpus cases matched, {i['unsupported']} unsupported. "
            f"At that data measurement, screen API/browser sessions: {s['api_sessions_compared']}/{s['browser_sessions_compared']}; handler mutation proof and Compose acceptance remain unfinished. "
            f"[Dated receipt and durable archive](../modernization/{Path(value['path']).with_suffix('.md').name}). "
            'Overall incomplete; no signing, activation, Phase 2 or release authority.')


def web_packet_path(path):
    date=Path(path).stem.removeprefix('carddemo-slice-1-')
    return 'docs/factory/carddemo-web-review-evidence-'+date+'.json'


def load_web(root):
    root=Path(root);path=latest(root,'carddemo-slice-receipt/1')
    if path is None:return None
    raw=path.read_bytes();value=json.loads(raw)
    packet=json.loads((root/web_packet_path(path)).read_bytes())
    if packet.get('receipt')!={'path':path.relative_to(root).as_posix(),'sha256':sha256(raw).hexdigest()}:
        raise ValueError('carddemo-web-receipt-hash')
    gates=value['gates'];m=gates['mutation'];counts=m['status_counts'];browser=gates['browser'];api=gates['api-reference']
    required={'COSGN00C','COMEN01C','COACTVWC','COACTUPC','COPAUS0C','COPAUS1C'}
    expected={'api-reference','browser-reference','mutation-reference','browser','mutation','ci-jobs'}
    if (value.get('unsigned') is not True or value.get('acceptance_complete') is not True
        or value.get('status')!='proved-in-ci' or value.get('remaining_evidence_gaps')
        or set(gates)!=expected or any(gate.get('passed') is not True for gate in gates.values())
        or set(value['scope']['programs'])!=required
        or not all(type(n) is int and n>=0 for n in counts.values())
        or m['total']<=0 or sum(counts.values())!=m['total'] or counts.get('KILLED',0)!=m['killed']
        or 10*m['killed']<9*m['total'] or m['threshold']!=90 or m['missing_screen_handlers']
        or abs(m['percent']-100*m['killed']/m['total'])>1e-9
        or browser['interactions']<=0 or browser['interactions']!=browser['required']
        or any(gates[mode]['completed_cases']<=0
               or gates[mode]['completed_cases']!=gates[mode]['planned_cases']
               or gates[mode]['programs_compared']!=6 or gates[mode]['programs_required']!=6
               or gates[mode]['interactions']!=browser['interactions']
               for mode in ('api-reference','browser-reference','mutation-reference'))):
        raise ValueError('carddemo-web-denominator')
    # Compact projection: measurement identities and all raw hashes remain in the linked receipt.
    return dict(schema='carddemo-web-status/1',run_id=value['run_id'],status=value['status'],
                cases=api['completed_cases'],interactions=browser['interactions'],bms_interactions=api['bms_interactions'],
                killed=m['killed'],total=m['total'],percent=m['percent'],status_counts=counts,
                path=path.relative_to(root).as_posix(),unsigned=True,final_head_ci='separate readiness gate')


def web_paragraph(value):
    if value is None:return 'Six-screen proof receipt is not available; no measured acceptance is inferred.'
    c=value['status_counts']
    return (f"CI run {value['run_id']}: {value['cases']}/{value['cases']} cases and "
            f"{value['interactions']}/{value['interactions']} API/browser interactions across six programs "
            f"({value['bms_interactions']} BMS interactions). Strict mutation: {value['killed']}/{value['total']} "
            f"KILLED ({value['percent']:.2f}%); {c.get('SURVIVED',0)} survivors, {c.get('NO_COVERAGE',0)} uncovered "
            f"and {c.get('TIMED_OUT',0)} timeout remain in the denominator. "
            f"[Unsigned receipt and complete retained artifacts](../modernization/{Path(value['path']).with_suffix('.md').name}). "
            'Bounded raw-source reference and disclosed synthetic fixtures; native execution and SQL-error screen equivalence remain unproved. '
            'Final publication-head CI and Howard merge approval are separate. No signing, import, activation, Phase 2 or release authority.')
