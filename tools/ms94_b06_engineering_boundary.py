"""Uncredited engineering artifacts must never cross an evidence admission."""
from pathlib import Path
import hashlib
from tools.ms94_b06_engineering_key import ENGINEERING_KEY_SHA256

LABEL = dict(run_class='engineering', qualification_credit=False, measurement_credit=False)


def refuse_engineering_key(public):
    if not isinstance(public, bytes) or not public:
        raise ValueError('evidence-public-key-required')
    if hashlib.sha256(public).hexdigest() == ENGINEERING_KEY_SHA256:
        raise ValueError("engineering-signing-key-not-admissible")


def refuse_engineering(value, path=None):
    if path is not None:
        path = Path(path).resolve()
        if 'b06-engineering' in path.parts or any(
                (p/'engineering.json').exists() for p in (path, *path.parents)):
            raise ValueError('engineering-evidence-not-admissible')
    def visit(item):
        if isinstance(item, dict):
            if isinstance(item.get('signature'), dict) and item['signature'].get('key_id') == ENGINEERING_KEY_SHA256:
                raise ValueError('engineering-signing-key-not-admissible')
            if item.get('run_class') == 'engineering' or str(item.get('artifact_type', '')).startswith('b06-engineering-'):
                raise ValueError('engineering-evidence-not-admissible')
            for v in item.values(): visit(v)
        elif isinstance(item, (list, tuple)):
            for v in item: visit(v)
    visit(value)
