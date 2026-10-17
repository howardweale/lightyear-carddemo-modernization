"""Download the explicitly indexed public release assets and verify exact bytes."""
import argparse
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path
import urllib.request

REPOSITORY = 'howardweale/lightyear-carddemo-modernization'


def verify(manifest, output, *, open_url=urllib.request.urlopen):
    value = json.loads(Path(manifest).read_bytes())
    if value.get('schema') != 'public-evidence-retention/1' or value.get('repository') != REPOSITORY or value.get('scope') != 'public CardDemo only':
        raise ValueError('public-retention-scope')
    evidence_date = value['source_evidence_date']
    if date.fromisoformat(evidence_date).isoformat() != evidence_date:
        raise ValueError('public-retention-date')
    rows = []
    for asset in value['assets']:
        expected_url = f"https://github.com/{REPOSITORY}/releases/download/{asset['release']}/{asset['name']}"
        if asset['url'] != expected_url or not re.fullmatch(r'evidence-'+re.escape(evidence_date)+r'-[a-z0-9][a-z0-9-]*', asset['release']):
            raise ValueError('public-retention-url')
        count = 0
        digest = hashlib.sha256()
        with open_url(asset['url'], timeout=120) as response:
            for chunk in iter(lambda: response.read(1024*1024), b''):
                count += len(chunk)
                if count > asset['bytes']: raise ValueError('public-retention-size')
                digest.update(chunk)
        if count != asset['bytes'] or digest.hexdigest() != asset['sha256']:
            raise ValueError('public-retention-content')
        rows.append(dict(url=asset['url'], bytes=count, sha256=digest.hexdigest(), verified=True))
    receipt = dict(schema='public-evidence-retention-verification/1',
                   manifest_sha256=hashlib.sha256(Path(manifest).read_bytes()).hexdigest(), assets=rows)
    Path(output).write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    return receipt


def verify_all(root, output):
    root, output = Path(root), Path(output)
    names = subprocess.check_output(['git', 'ls-files', 'docs/factory/evidence-retention-*.json'], cwd=root, text=True).splitlines()
    if not names: raise ValueError('public-retention-no-committed-manifests')
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        verify(root/name, output/(Path(name).stem+'-verification.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest'); parser.add_argument('output')
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    if args.all: verify_all(args.manifest, args.output)
    else: verify(args.manifest, args.output)
