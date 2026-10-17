"""Dated CardDemo evidence with the full unsupported-case denominator."""
from hashlib import sha256
import json
from pathlib import Path
import re


def latest(root):
    paths=sorted(p for p in (Path(root)/'docs/modernization').glob('carddemo-slice-1-*.json')
                 if re.fullmatch(r'carddemo-slice-1-\d{4}-\d{2}-\d{2}\.json',p.name))
    return paths[-1] if paths else None


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
            f"Screen API/browser sessions: {s['api_sessions_compared']}/{s['browser_sessions_compared']}; handler mutation proof and Compose acceptance remain unfinished. "
            f"[Dated receipt and durable archive](../modernization/{Path(value['path']).with_suffix('.md').name}). "
            'Overall incomplete; no signing, activation, Phase 2 or release authority.')
