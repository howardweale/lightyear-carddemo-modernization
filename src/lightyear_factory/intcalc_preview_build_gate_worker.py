"""Fresh-exec private worker; no provider, credential or model-role interface."""
from pathlib import Path
import sys

if __name__ == '__main__':
    # -I suppresses user-site and environment import paths. Only this reviewed
    # checkout's source root is added, not the request directory or working dir.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lightyear_factory.intcalc_preview_build_gate import worker_main
    from lightyear_factory.intcalc_preview_composition import canonical
    try:
        result = worker_main(sys.argv[1:])
        sys.stdout.buffer.write(canonical(result))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:
        sys.stderr.write('build-gate-worker-refused\n')
        raise SystemExit(2) from None
