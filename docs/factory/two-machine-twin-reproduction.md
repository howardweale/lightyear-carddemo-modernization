# Two-machine twin reproducibility — 2026-10-11

Howard's A9 decision replaces the Multipass-specific requirement with two independent clean machines: one GitHub-hosted runner and one operator Mac or cloud VM. Both must build the exact same commit under the same **linux/amd64 Ubuntu24.04 image digest**, fixed Ubuntu package snapshot and checksum-pinned GnuCOBOL packages. The Mac must explicitly select linux/amd64; an arm64 build is not the comparison.

Pinned base: `ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b` (official Ubuntu24.04 amd64 manifest resolved2026-10-11). `reproducible.Containerfile` fixes transitive package lookup to the2026-10-01 Ubuntu snapshot. Existing compiler-only libfaketime pins embedded compilation timestamps; it does not change the machine clock.

The [dedicated workflow](../../.github/workflows/factory-twin-reproducibility.yml) builds both ASCII and cp037 executables in a clean container and retains per-binary hashes, exact commit, base-image digest, installer hash, machine label and build-receipt seals. It also executes the mixed-key probe. Build container networking is disabled after toolchain installation. This is public GnuCOBOL engineering CI; it does not start Oracle, a B06 application, or a model.

## Operator machine procedure

Howard selected his Mac and will run the command himself. With Git and Docker
already available, check out the exact reviewed SHA and run
`bash tools/legacy_twin/run_reproduction.sh EXACT_COMMIT howard-mac`.
The script refuses a different or modified tracked checkout, pins linux/amd64
and the exact base image, creates a fresh output, and preserves logs. It installs
packages only inside the disposable build image; it makes no host configuration
changes. Return only `work/operator-twin-<commit-prefix>/build/reproduction.json`
to the chat; keep logs and binaries local. The full equivalent commands follow.

Run only on the separately approved operator host and outside any conflicting evidence window. Check out the exact PR head used by the completed GitHub receipt. Use a fresh output directory; the builder refuses existing paths. These are instructions, not evidence that this machine has run:

```sh
# Replace EXACT_COMMIT and MACHINE_LABEL with the reviewed commit and host label.
docker build --platform linux/amd64 -f tools/legacy_twin/reproducible.Containerfile -t twin-repro-toolchain .
mkdir -p work/operator-twin-reproduction
docker run --rm --network none --platform linux/amd64 \
  --mount type=bind,src="$PWD",dst=/source,readonly \
  --mount type=bind,src="$PWD/work/operator-twin-reproduction",dst=/output \
  --env PYTHONPATH=/source/src:/source --env PYTHONDONTWRITEBYTECODE=1 \
  --workdir /source twin-repro-toolchain \
  python3 -B -m tools.legacy_twin.reproducible_build build \
  --output /output/build --machine-id MACHINE_LABEL --host-kind operator-machine \
  --commit EXACT_COMMIT \
  --base-image ubuntu@sha256:f610ab94648195aa356059f5b41d6085c9d4d903c072430cdd1af7bdb646106b
python3 -B -m tools.legacy_twin.reproducible_build compare \
  github-reproduction.json work/operator-twin-reproduction/build/reproduction.json \
  work/two-machine-comparison.json
```

The comparison rejects different commits/images/installers/platforms, same machine labels, two GitHub-only declarations, missing binaries, altered receipts and binary mismatches. Mismatches are saved before refusal. Machine identity is operator-declared, not hardware attestation. Preserve package/build logs and compare every compiled binary, not only the main executable. Matching hashes support reproducibility of this public twin on these two machines; they do not establish z/OS behavior.

**Second operator machine is pending.** No Mac/cloudVM access or receipt was supplied. Two clean directories on one host do not satisfy A9, and no second-machine result is claimed. Any observed hash differences must be recorded in `twin-limits.md` with the differing paths and both receipt seals before further promotion.
