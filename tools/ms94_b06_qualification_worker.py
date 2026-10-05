"""Bounded host worker. Existing signing authority stays in place, outside Docker."""
import argparse
from pathlib import Path
from lightyear_calibration.journey_runtime import CONTROL, JourneySigner
from tools.ms94_b06_admission import check


def existing_signer(authority):
    authority = Path(authority).resolve()
    check((authority/CONTROL/'authority.key.pem').is_file() and
          (authority/CONTROL/'authority.public.pem').is_file(), 'existing-authority-required')
    return JourneySigner(authority)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=('native', 'finalize'), required=True)
    for name in ('root', 'run', 'output', 'authority'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    root, run = Path(args.root).resolve(), Path(args.run).resolve()
    check(Path.cwd().resolve() == root, 'worker-must-run-from-snapshot')
    signer = existing_signer(args.authority)
    if args.stage == 'native':
        from tools.ms94_b06_native import execute_pair
        execute_pair(root, run, signer)
    else:
        from tools.ms94_b06_qualification_driver import finalize
        finalize(root, run, Path(args.output), signer.public, signer)


if __name__ == '__main__': main()
