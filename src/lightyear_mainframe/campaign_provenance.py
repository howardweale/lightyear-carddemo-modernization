"""Bind a compiled host campaign to its exact code, inputs and retained results."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from .legacy_twin import ROOT, verify_build, write_json

PREFIXES=('spec/mainframe','src/lightyear_mainframe','src/lightyear_factory/scenario_policy.py',
          'tools/legacy_twin','tools/check_factory_review.py','tools/check_equivalence_followup.py',
          'docs/factory','tests/mainframe/fixtures')
RECORDS=('review-summary.json','mutation-results.json','mutation-inventory.json',
         'generation-inventory.json','fault-results.json','systematic-scenario-selection.json')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def sealed(value):
    return {**value,'content_sha256':digest(value)}


def read_sealed(path):
    value=json.loads(path.read_text());body={k:v for k,v in value.items() if k!='content_sha256'}
    if value.get('content_sha256')!=digest(body):raise ValueError('campaign-seal-mismatch:'+path.name)
    return value


def current_binding():
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    subprocess.run(['git','diff','--quiet','HEAD','--',*PREFIXES],cwd=ROOT,check=True)
    extra=subprocess.check_output(['git','ls-files','--others','--exclude-standard','--',*PREFIXES],cwd=ROOT)
    if extra.strip():raise ValueError('untracked-campaign-inputs')
    paths=subprocess.check_output(['git','ls-files','-z','--',*PREFIXES],cwd=ROOT).decode().split('\0')
    files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths if p}
    if not files:raise ValueError('campaign-input-binding-empty')
    return dict(head=head,files=files)


def begin(campaign,job):
    value=sealed(dict(schema='factory-campaign-start/1',job=job,binding=current_binding(),
        started_at=datetime.now(timezone.utc).isoformat(),run_class='engineering',model_calls=0))
    write_json(Path(campaign)/'campaign-start.json',value)
    return value


def finish(campaign,job):
    campaign=Path(campaign);start=read_sealed(campaign/'campaign-start.json')
    binding=current_binding()
    if start['job']!=job or start['binding']!=binding:raise ValueError('campaign-inputs-or-head-changed-during-run')
    builds={}
    for path in sorted(campaign.rglob('build-receipt.json')):
        verify_build(path.parent)
        builds[path.relative_to(campaign).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    if 'baseline/build-receipt.json' not in builds:raise ValueError('campaign-baseline-build-missing')
    records={name:hashlib.sha256((campaign/name).read_bytes()).hexdigest() for name in RECORDS}
    value=sealed(dict(schema='factory-campaign-manifest/1',job=job,binding=binding,
        campaign_start_sha256=start['content_sha256'],build_receipts=builds,records=records,
        completed_at=datetime.now(timezone.utc).isoformat(),run_class='engineering',model_calls=0))
    write_json(campaign/'campaign-manifest.json',value)
    return value


def validate(campaign,job):
    campaign=Path(campaign).resolve();manifest=read_sealed(campaign/'campaign-manifest.json')
    start=read_sealed(campaign/'campaign-start.json')
    if manifest.get('schema')!='factory-campaign-manifest/1' or manifest['job']!=job:
        raise ValueError('campaign-schema-or-job-mismatch')
    if manifest['binding']!=current_binding():raise ValueError('campaign-stale-head-or-inputs')
    if start['content_sha256']!=manifest['campaign_start_sha256'] or start['binding']!=manifest['binding'] or start['job']!=job:
        raise ValueError('campaign-start-binding-mismatch')
    if set(manifest['records'])!=set(RECORDS) or 'baseline/build-receipt.json' not in manifest['build_receipts']:
        raise ValueError('campaign-record-inventory-incomplete')
    for name,expected in {**manifest['records'],**manifest['build_receipts']}.items():
        path=(campaign/name).resolve()
        if not path.is_relative_to(campaign) or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('campaign-retained-artifact-mismatch:'+name)
    for name in manifest['build_receipts']:verify_build((campaign/name).parent)
    return manifest
