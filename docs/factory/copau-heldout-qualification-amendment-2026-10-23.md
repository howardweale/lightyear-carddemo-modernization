# COPAU private-key qualification amendment — 23 October 2026

Howard's 23 October decision supersedes the qualification and operator sequence
in [the earlier helper proposal](copau-heldout-helper-2026-10-23.md). That dated
proposal remains historical. No private key has been generated or qualified by
this amendment. CI uses published synthetic inputs only.

## Four mandatory criteria

1. **Freshness.** After the public/run-surface snapshot, Howard chooses a new
   private random 256-bit seed and enters it only at the hidden operator prompt.
   Private provenance records the seed, input fields, producer/version hashes,
   generation time and selected outputs. Seed dependence is tested in synthetic
   CI. Privacy/randomness is an explicit operator attestation, not inferred from
   length. With a secret high-entropy seed and the stated derivation assumptions,
   public code/data alone cannot feasibly reconstruct these held-out outputs.
2. **Exposure.** Scan every file and path in the exact 403-file worker workspace
   bound by manifest SHA-256
   `bb11b3644a6070d7176767d82826d451e0b5055a6ce3e5eda0495c45591b0771`,
   the approved graph projection and every controller prompt and context template
   the run can expose. All four surfaces require reviewed hash-bound closure and
   zero matches, missing files and errors. A directory listing alone is not proof
   that all queryable graphs, dynamic includes or templates are represented.
3. **Collisions.** Scan current main's exact Git tree, the workspace and projection
   against the unchanged scanner's raw and normalized 40-character windows and
   decoding rules. Bind main to fresh public GitHub metadata before and after
   generation/scanning. Reject the bundle if any fragment collides; no automatic
   fragment substitution, new seed or retry. Report collision counts only.
4. **Selection.** Private business identifiers feed the frozen independent
   reference and unchanged authorization/fraud session. Select 40-character
   windows from its existing computed `pautdtl1.source_sha256` after-state fields.
   The original codec computes these fields and the existing judge's database
   comparison checks them. They are not a new hash appended solely for scanning.
   No merchant names, common messages, labels or padding are selected. The private
   transaction-ID domain is 36^15; a digest's length is not an entropy measurement.

The original draft's merchant-in-COMMAREA assumption is withdrawn. The source
does not guarantee such a return. The revised synthetic test must establish the
actual record-digest output and private-seed dependence before helper approval.
These fragments detect selected expected-state exposure, not all short-field
leaks, nor correctness of an entire implementation or malicious intent. A correct
implementation may reproduce them when legitimately given the held-out inputs;
the factory workers must not receive those inputs or outputs during construction.

## Historical disclosure, not qualification

Historical CI artifact/Release payloads and prior repository history are marked
**“not inspected; not relevant to freshly generated values”**. Metadata collection
lists known expired artifact IDs, unavailable catalogs and the inability to
enumerate deleted artifacts/assets/history. It downloads no historical payloads.
Missing historical material and metadata errors do not block qualification.
That exception never excuses missing run-visible content or baseline scan errors.

## Operator sequence after helper review and green CI

Use a clean approved checkout, the reviewed Python environment and #430's private
store, outside every exposed root. No signing key is read or created by this helper.

1. Prepare exact worker, graph, prompt and context snapshots. The graph/prompt/
   context boundary JSON uses schema `copau-run-visible-boundary/1` and `surfaces`
   keys `graph`, `prompts`, `contexts`; each entry contains positive `records` and
   `inventory_sha256` over the canonical file rows. Bind the actual F2 projection
   and template inputs through independent review. Do not inspect private answers
   to construct the public index.
2. Run `tools/copau_public_corpus_index.py` with `--worker`, `--manifest`,
   `--repository`, `--graph`, `--prompts`, `--contexts`, `--run-boundary`, `--out`.
   The repository must contain current main's exact public Git object. The index
   initially remains unreviewed. Review closure against the run's allowed inputs,
   bind the approval reference and full index digest; setting flags alone is not
   review evidence. Keep all historical disclosure entries.
3. From the approved checkout run `python -B -m tools.copau_answer_key` with
   `--reviewed-commit`, `--corpus-index`, `--reviewed-corpus-sha256` and all
   `--exposed-root` paths. Indexed roots are also excluded from private storage.
   Enter a fresh private seed and the exact hidden attestation phrase. Never put
   the seed in arguments, environment variables, chat, Git or CI.
4. Preserve any refusal output for private review. The helper never overwrites
   existing files. Scan-only success is not qualification: seed attestation and
   actual computed-output selection must also pass. Changed main requires a new
   reviewed baseline. Changed graph/templates/workspace likewise invalidate the
   binding; keep these exact hashes through the factory run.
5. Publish only the redacted qualification report (hashes/counts and historical
   public IDs) and the three-field bundle attestation: digest, size, count. Never
   publish the bundle, private provenance, seed, values or matching locations.
   The bundle remains in #430 format. F2 policy, WorkOrder, plan and request are
   bound later; `request_ready` remains false until all concrete fields pass CI.

Helper review target remains Sunday 25 October. POSTTRAN original-commit/key-only
review remains Monday 26 October 12:00 Pacific. Go/no-go is Wednesday 28 October
18:00 Pacific: if any of the four criteria is unmet, move the run, approximately
to 6 November. Do not weaken criteria to preserve the date. First COPAU run only;
8-hour cap, 30 October 08:00–20:00 Pacific window and USD 10 cap unchanged.
No signing, model calls, Tower writes or proof exports are authorized.
