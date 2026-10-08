# PR270/271 review follow-up

Operator review; not independent attestation. Zero model calls, B06 Docker
commands, native pairs or new operator decisions in this increment. r10 remains
failed; Howard reported rejecting r11. No B05, template-r1, work/ms94, J1
business predicate or frozen input was edited.

## Runtime artifacts

Local validation: 63 host/inventory/Tower tests (13 local-evidence skips), and
173 B06 admission tests (one local-evidence skip): **222 passed, 14 skipped**.
The 19 new portable review tests all pass without local JDI data. A dedicated
Windows/Linux CI workflow now runs those tests; remote CI has not run for this
unpublished increment. Test-injected failure messages are expected negative
controls, not native executions.

The broad extraction entry point is withdrawn. Raising its 200,000-class bound
does not solve runtime scope. Its failed output and the earlier bound proposal
remain historical evidence.

The next proposal is one **inventory-only** pinned-image container: paths, sizes,
SHA-256 hashes, class/nested-archive directory counts and per-root progress.
No class bytes are copied. Progress is flushed as each artifact completes; the
terminal inventory is written on failure as well as success. Limits: 900 seconds
work, 600 seconds cleanup reserve, one container, no retries, network none,
no database, target JVM or model. The controller binds the complete argv,
requires exact public bytes and a fresh Tower decision before any Docker call,
and limits cleanup to its verified owned container. A new exact commit,
snapshot and 30-minute UTC window are still needed; no old authority is reused.

The separate scoped extractor takes a byte-bound inventory and saved effective
Equinox/Surefire properties. It parses explicit resolved file URLs and contiguous
classpath entries; ambiguous encodings, indirection and gaps fail closed. It
deduplicates the union, not the whole Maven tree. A configuration alone does not
prove a loaded class: the observer must also match the actual defining loader
and artifact. Unsupported configuration formats require a reviewed reader;
they are not guessed.

Only `lib/modules`, extracted using the bound `jimage` binary, supplies
authoritative JDK class bytes. jmods are not admission inputs. Selected bundles'
nested `lib/*.jar` are opened, with depth, class-count and expanded-byte bounds.
Nested counts, jimage entry counts and expanded-byte limits must be measured
before sealing the scoped plan; the cheap inventory alone does not supply them.
The scoped extractor is an offline-tested library, not yet an authorized
executable group. No new artifact catalogue or native binding is claimed.

## Generated provenance and pool rule

The forwarding body decoder is now separate from admission. Admission additionally
requires the recorded JDK lambda-factory boundary, invokedynamic/bootstrap
linkage, independently byte-bound defining host and loader, generated definition,
method/pool hashes and immediately younger target frame. The invoked target's
owner does not substitute for the defining host. Application name prefixes no
longer bypass jar-entry verification. Direct `defineHiddenClass` provenance is
rejected. Candidate-host lambdas remain candidate-origin.

The native collector has not yet supplied the complete generation record required
by that gate. Missing provenance therefore rejects; a synthetic forwarding stub
does not count as a completed native proof. LambdaForm expression/definition
fixtures cover extra logic, altered host/loader/emitter, missing linkage and
changed hashes in ordinary CI. Their `adapter_body_verified`/native-admission
flags remain false where proof is incomplete.

The approved single-class pool rule is unchanged. A [general rule proposal](pool-proposal-v2.md)
derives stand-in entries from bound hierarchy bytes, and is intentionally not
imported by production admission. Authored 145+14 pool-shape tests exercise the
approved comparator's prefix/count/semantic checks in CI by substituting only a
test identity; the unmodified production identity gate rejects that fixture.
Real-JDI evidence tests remain separate and skip when their captures are absent.

## Next admission steps

1. Review/publish the inventory-only code and bind an exact new window in Tower.
2. Inventory; then measure and approve the resolved runtime extraction separately.
3. Complete collector integration and independent generated-class replay against
   those native artifacts. Review the general pool proposal before enabling it.
4. Freeze and publish one five-path census (J1's three paths, J2 retained, J3
   retained; both engines), then obtain its exact Tower decision.

The Oct 9 end-of-day time box remains **2026-10-10T07:00:00Z**. If JDI provenance
is not fully provable then, stop and present the alternative mechanism. No smoke
or measurement launch is authorized by this document.
