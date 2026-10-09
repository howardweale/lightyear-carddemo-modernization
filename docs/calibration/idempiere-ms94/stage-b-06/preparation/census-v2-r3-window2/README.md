# Census r3: 10:00 AM–9:00 PM PDT window

October 9, 2026. Operator review, not independent attestation.

This supersedes the original r3 window before any native slot started. The five
slot plans change only `docker_run_window` and their content hashes. All other
113,629 snapshot files, including application inputs, implementation, observer,
class catalogue and expected outcomes, are byte-identical. The same never-started
r3 slot identities are retained; no failed r2 slot is resumed or replaced.

- Window: October 9 10:00–21:00 PDT (17:00 UTC to October 10 04:00 UTC).
- Latest full-budget launch: **10:50:50 PDT / 17:50:50 UTC**.
- Five serial Oracle/PostgreSQL pairs: J1 retained, duplicate-line rejection,
  candidate null dereference/direct closed diagnostic, J2 retained, J3 retained.
- Each pair: 7,190 seconds including finalization/replay/cleanup; candidate timeout
  1,800 seconds. Group reserve: 600 seconds in addition to 35,950 pair seconds.
- No models; no qualification or measurement credit; stop on first unexpected result.

## Exact bindings and validation

Snapshot: `72e28a5ccec6ac4bb61362b6d0c81269be927e4324c2941d299bd3492da9703b`.
Executable plan: `7a9acb7f4c45a5e02526f7ed192ee3e2352a49114702ebaf42655e9439be7998`.
Window amendment: `f83ee36f6d16e7aacca31eed9c0bb803fca9e40118b305e12d47ca09508a0e64`.
Frozen verification: `15996793972c6afd0a551291c2d5784316249f587e3ba9dbb5ec3872ddf17663`.
Implementation commit: `ecfb7cd637b4f47bdf800c44b43a64694f522248`.

The unchanged full freeze validated all five observer manifests again.
All 113,634 frozen file hashes and 767 public implementation files verified;
23 tests passed from frozen imports. Preparation took 3,895.235 seconds,
including 85.687 seconds for the final verifier. Zero Docker commands, native
pairs or model calls. The implementation commit separately passed all 28 CI checks.

The retained built application image is
`sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`.
Other exact image digests are in executable-plan.json. Real clocks and the
October accounting-period guard remain mandatory.

Only hash-only plan/verification records and documentation are public. Private
inputs, class blobs, reference sources, archives, captures and keys stay local.
A fresh Tower decision binding this snapshot, plan, public commit and window is
required. Preparation is not launch authorization. Earlier failures, including
r2's collector failure and incomplete finalization, remain unchanged.
