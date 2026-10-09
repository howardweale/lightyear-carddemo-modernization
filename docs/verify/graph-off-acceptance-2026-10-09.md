# Verify graph activation, stage 1: graph-off acceptance (2026-10-09)

Operator review by Howard Weale; not independent attestation. Zero model calls.

| Item | Value |
| :---- | :---- |
| Revision | `25735d06beeefb97935903082ad046b4774e6bc3` (`main`, includes the tracked activation checker `e3c7e4d0`) |
| VM | `lyverify-graph-off-r2`, Multipass Ubuntu 24.04.5 LTS, arm64 (aarch64), kernel 6.8.0-142-generic, Apple Silicon Mac |
| Setup hash | `faa857d95c9d1d0007ea773f6292b236e92207e2ccf609dd483c4d3fc59fabbf` |
| Platform acceptance | **passed**, started 2026-10-09T18:51:57Z, 37.958 s, exit 0, log `16e222868cf9582a80f470a153d4b36fcca00f0b3bc23b9657b3d1a07e4b25e3`, judge uid 1000, agent uid 65534 |
| Baseline protocol check | **passed** at 2026-10-09T18:52:52Z: 10 tools, budget unchanged, 0 submissions, manifest `4857a8e511becc441762533ac4ec66841a2fab04db5c675ca097b9eaeca2d587`, probe `7d9e67930e0035ef30efca554c3c7c05b912b15b783920f4b52a42e0c656cfd7`, projection and decision proof null |
| Inspector walkthrough | 15 steps completed as specified, reported by the operator: `good.jar` equivalent; `rounding.jar`, `skipped.jar`, `date.jar` divergent; repeat `date.jar` consumed the fifth attempt; sixth submission refused |
| Offline replay | **verified**: 5 attempts, 5 native verdicts replayed, journal head `f2bb76560c674d0e6cf4cc1e9cec13b77f80bb193555f12bbec621c293405026` |
| Model calls | 0 |

## Notes

- An earlier VM, `lyverify-graph-off-review` (revision `92a49774`, platform acceptance passed 2026-10-07), predates the installed activation checker. It is preserved, stopped, and not used for this record.  
- One `submit_candidate` call before step 7 used a literal placeholder (`<UUID 1>`) as `request_id` and was refused without execution.  
- Per-attempt receipt hashes were not copied out individually; the signed journal and the offline replay above are the retained evidence.  
- This record establishes the graph-off baseline only. Stage 2 (Verify Tower authority) remains pending Howard's approval; no projection has been built or approved, and no live model run is authorized.