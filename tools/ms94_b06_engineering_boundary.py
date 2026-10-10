"""Uncredited engineering artifacts must never cross an evidence admission."""
from pathlib import Path

LABEL = dict(run_class='engineering', qualification_credit=False, measurement_credit=False)


def refuse_engineering(value, path=None):
    if path is not None:
        path = Path(path).resolve()
        if 'b06-engineering' in path.parts or any(
                (p/'engineering.json').exists() for p in (path, *path.parents)):
            raise ValueError('engineering-evidence-not-admissible')
    def visit(item):
        if isinstance(item, dict):
            if item.get('run_class') == 'engineering' or str(item.get('artifact_type', '')).startswith('b06-engineering-'):
                raise ValueError('engineering-evidence-not-admissible')
            for v in item.values(): visit(v)
        elif isinstance(item, (list, tuple)):
            for v in item: visit(v)
    visit(value)
