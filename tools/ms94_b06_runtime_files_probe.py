"""Read-only pre-candidate hash measurement; input/output through trusted broker."""
import hashlib
import json
import sys
from pathlib import Path


def measure(expected):
    result = {}
    for name, digest in expected.items():
        path = Path(name)
        if not path.is_absolute() or '..' in path.parts or not path.is_file():
            raise ValueError('runtime-file-missing')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest:
            raise ValueError('runtime-file-bytes-differ')
        result[name] = actual
    return result


if __name__ == '__main__':
    print(json.dumps(measure(json.load(sys.stdin)), sort_keys=True))
