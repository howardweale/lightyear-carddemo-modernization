"""Download the explicitly indexed public release assets and verify exact bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REPOSITORY = 'howardweale/lightyear-carddemo-modernization'


def verify(manifest, output, *, open_url=urllib.request.urlopen):
    value = json.loads(Path(manifest).read_bytes())
    if value.get('schema') != 'public-evidence-retention/1' or value.get('repository') != REPOSITORY or value.get('scope') != 'public CardDemo only':
        raise ValueError('public-retention-scope')
    rows = []
    for asset in value['assets']:
        expected_url = f"https://github.com/{REPOSITORY}/releases/download/{asset['release']}/{asset['name']}"
        if asset['url'] != expected_url or not asset['release'].startswith('evidence-2026-10-15-'):
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest'); parser.add_argument('output')
    args = parser.parse_args(); verify(args.manifest, args.output)
