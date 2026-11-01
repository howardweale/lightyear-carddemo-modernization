# Human-admitted public drill dispatch — unexecuted design

This is an isolated source proposal, not an authorization to execute. It depends
on the combined count packet and the earlier human-proof draft. None of these
new dispatch tests has executed. No source is pushed by publishing this review.

The proposed `human-drill-execute` CLI accepts only an existing public Factory
proof and trust file, committed plan/contract, work order, execution policy,
public output/isolation fixture paths, a fresh external CI evidence directory,
and an allowed OCI runtime. It refuses outside GitHub Actions before reading
inputs. It has no provider selection, API credential, signing, private expected
value, machine-issued identity, resume or retry option. It currently exits 1
even after a complete public trace because full production qualification remains
unresolved. A nonzero result must not be suppressed to obtain strict green.

The genuine proof checks bind the source tree, exact signed executable and
workflow bytes, work order, policy, role actions, caps, time window, public
fixtures and current external trust head. Native GitHub run/job checks and the
atomic consumed ref precede execution. A failed or ambiguous consumed attempt
stops; it cannot be reconstructed from a receipt or reused. The fresh evidence
directory is an attempt output directory, never a new Factory Tower root.

The dispatch uses the native controller, ModelAgentSet, AccountedModelProvider
and OCI backend, with a dedicated public stub that makes no model API calls.
Only explicitly committed files under tests/fixtures/p5_public may enter its
workspace. Public expected-output and isolation files stay out of that read
manifest. Graph and private expected-value routes are excluded. The public
isolation values exercise scanner machinery; they do not establish protection
of real private answer keys or a production workload.

Before each stub response, the provider verifies the exact signed output-plan
step, the live controller and budget binding, the fsynced logical reservation,
and fresh human role authorization. It retains exact serialized request and
response files, hashes and sizes, plus ordered start/end records in the native
controller ledger. It preserves the original receipt. An additive provenance
report compares retained files, live observations, budget calls, authorizations,
reservation events and the actual ledger chain. The receipt's earlier ledger
snapshot and its final scan tail are reported separately. Pure retained-record
validation explicitly cannot establish controller origin.

Origin depends on the reviewed controller code running on the GitHub runner.
The report is unsigned and not independent remote attestation. The draft does
not weaken the existing production build-receipt type/signature requirements.
The report and context remain production_qualified=false and
qualifies_for_factory_receipt=false. G0/D01/D07/D08 are not closed by this draft.

## Future operator sequence, after separate source and execution approval

1. Finish the production receipt route and exact public fixtures/workflow; obtain
   exact-source publication approval, CI evidence and exact green-head merge
   approval. Do not sign a changing executable or fixture set.
2. Prepare one exact admission plan and fresh nonce per independently consumed
   drill case. It binds the executable, workflow/job/attempt 1, public inputs,
   work order, roles/actions and caps. Exact invocation hashes currently have no
   wildcard; concrete cases must demonstrate they can bind their actual inputs.
3. Howard reviews and signs each admission in the EXISTING Factory on 8769 as
   campaign-authorizer. The draft needs one human decision per case, not a
   signature for every role call. Four separately admitted cases would need four
   signatures; the final case inventory is not yet fixed. No machine signs.
4. Following the corrected POSTTRAN order, export the proof first, independently
   verify the resulting journal head with the installed journal_head.py and
   verify-decision, and bind that proof/current head. Any later journal append
   requires fresh verification; an old head is never silently reused.
5. Commit only the permitted plan/proof/contract metadata after the reviewed
   executable, supply the external PUBLIC trust configuration, and use the
   separately reviewed CI workflow for one attempt. No local execution. No
   existing Factory installation, data root, journal or key is changed.
6. Retain native receipt, controller ledger, attempt accounting/identity, public
   request/response files, admission record and provenance report. Missing,
   substituted, reordered or unaccounted evidence fails closed. Unaccepted gaps
   continue to fail strict qualification.

Remaining work: full production receipt route without machine signatures;
concrete signed per-case fixtures and workflow dispatch; positive genuine-proof
controller/OCI CI evidence; abrupt-stop retained provenance coverage; standalone
retained-artifact integration; and exact approval of all changed source/binding
bytes. This document neither consumes an attempt nor requests signatures now.
