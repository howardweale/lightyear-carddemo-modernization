"""Read only pinned-image JAR entries before the candidate starts. No network."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def verify_entries(spec):
    result = {}
    for name, expected in spec.items():
        path = Path(expected['jar']).resolve(strict=True)
        if not any(path.is_relative_to(Path(p)) for p in ('/application', '/root/.m2')):
            raise ValueError('framework-jar-path')
        member = name.replace('.', '/') + '.class'
        if expected['member'] != member or path.suffix != '.jar':
            raise ValueError('framework-jar-member')
        with zipfile.ZipFile(path) as archive:
            matches = [i for i in archive.infolist() if i.filename == member]
            if len(matches) != 1 or matches[0].file_size > 4 * 1024 * 1024:
                raise ValueError('framework-jar-entry-closure')
            data = archive.read(matches[0])
        if hashlib.sha256(data).hexdigest() != expected['entry_sha256']:
            raise ValueError('framework-jar-entry-changed')
        result[name] = {**expected, 'jar_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


if __name__ == '__main__':
    print(json.dumps(verify_entries(json.load(sys.stdin))), flush=True)

