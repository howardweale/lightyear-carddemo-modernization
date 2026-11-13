"""CI-only actual-volume observation; synthetic placement, never Mac qualification."""
import json
import os
from pathlib import Path
import sys
import uuid

from lightyear_factory import intcalc_preview_ledger_volume as v


def main():
    result = None
    lease = None
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise v.VolumeRefused('ci-only-probe')
        v.native()
        root = Path(os.environ['RUNNER_TEMP']).resolve(strict=True) / ('c2-volume-ci-' + uuid.uuid4().hex)
        root.mkdir(mode=0o700)
        paths = {kind: root / kind for kind in ('use', 'run')}
        identities, fsids = {}, []
        for kind, path in paths.items():
            path.mkdir(mode=0o700)
            _, fd, identities[kind] = v.open_parent(path)
            try:
                fsids.append(tuple(v.filesystem(fd)['fsid']))
            finally:
                os.close(fd)
        if fsids[0] != fsids[1]:
            raise v.VolumeRefused('ci-volume-mismatch')
        placement = v.AttendedPlacement(v.c.digest(b'SYNTHETIC-CI-NOT-HOWARD-APPROVAL'),
            identities['use'], identities['run'], fsids[0], True)
        lease = v.qualify(paths['use'], paths['run'], probe_id=v.c.digest(uuid.uuid4().bytes), placement=placement)
        result = lease.receipt()
        result['evidence_scope'] = 'CI runner only; not the operator Mac or a human placement approval'
        return_code = 0
    except v.VolumeRefused as error:
        result = error.public_record()
        return_code = 2
    except Exception:
        result = {'status': 'REFUSED', 'reason': 'unexpected-ci-probe-fault', 'qualified': False}
        return_code = 2
    finally:
        if lease is not None:
            lease.close()
    # Only fixed-schema public fields; no local paths, device IDs or raw errors.
    Path('ledger-volume-ci-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return return_code


if __name__ == '__main__':
    raise SystemExit(main())
