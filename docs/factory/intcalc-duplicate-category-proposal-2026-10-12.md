# Proposed scoped decision: INTCALC duplicate-category

**Status: pending Howard approval; not effective.** [Full source-bound proposal](intcalc-duplicate-category-proposal-2026-10-12.json).

Approve classifying only `intcalc-duplicate-category`, under the pinned twin indexed adapter and generator, as an **expected loader refusal outside the mutation-comparison domain**. The duplicate TCATBALF primary key is refused by `load-TCATBALF` with rc66 before CBACT04C starts. Keep this scenario as a loader negative test. Do not give it kill, equivalence, comparison or program-coverage credit, and do not remove mutant sites from adequacy denominators.

This does not apply to duplicate transaction IDs, any valid duplicate program input, any POSTTRAN refusal, other loader errors, or a z/OS-facing claim. No classifier change has been made.

Approval alone is insufficient to make the reclassification effective. Fresh exact-head receipts must bind the generator, loader, duplicate-key input bytes and source hashes, and demonstrate the expected refusal before program start for both control and instrumented baseline. Missing evidence, an unexpected phase/code, source changes or actual execution remain unresolved gaps.

Preserve every original raw receipt and the historical 113 final gap dispositions / 167 records with any gap. After approval and fresh evidence, publish a separately labelled assessment of the remaining valid comparison domain for every mutant. Never blanket-clear 113 gaps. The pending 200/200 comparisons, register dependencies, output diversity and all other threshold conditions remain; this decision grants no threshold/release approval.

All main merges remain held until B06 cleanup is sealed.

## Exact proposal binding

Content SHA-256: `0706ffff6b402568715f3f83174327b166791c6fee88d530016cde77c6f8d882`.

| Bound source | LF SHA-256 |
|---|---|
| `src/lightyear_mainframe/scenario_generation.py` | `13755d905a9e5c02f52cc21f3d66e796ec18352174475f45e4595ff78fa70852` |
| `src/lightyear_mainframe/legacy_twin.py` | `0311ce42e7d2d67f9529edb7c8666ae405ae1463ebf50f32a89a8d2cd2d51eea` |
| `tools/check_generated_scenarios.py` | `cb717fd8bfd02733ea5be7818211b671d7503a93492338f6b1f310a2b6221210` |
| `spec/mainframe/public-source/CBACT04C.cbl` | `5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4` |

Requested approval: **Approve the source-bound INTCALC duplicate-category loader-domain proposal above, conditional on fresh receipts, with historical evidence preserved.**
