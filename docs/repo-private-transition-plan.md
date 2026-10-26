# Private source repository and public evidence — draft plan

Howard has decided that the main repository becomes private before the first customer. This document makes no repository, visibility, access, protection, Pages or CI changes. It is a review draft; no merge is authorized before the Friday run.

## Publication boundary

| Keep private | Candidate for a separate public evidence repository |
| --- | --- |
| Application and factory source, deployment recipes, customer adapters and intake | Public claims register with exact scope, limitations and supersession history |
| Customer procedure/twin source, fixtures, business rules, data and derived traces | Receipts generated solely from approved public or authored synthetic fixtures |
| Internal operational discussions and approval context | Explicitly approved public attestations and source-independent proof summaries |
| Run configuration, private infrastructure topology, operational logs | Minimal replay tools and schemas that can verify a public evidence package without private imports |
| Signing material and credentials in their existing external custody, never in either repository | Public verifier keys only when their publication is separately approved |

A hash alone does not make an object safe to publish: filenames, low-entropy values, paths, identifiers and embedded error messages can disclose customer information. Each proposed public package needs an explicit provenance and disclosure review. The public evidence repository must not mirror the private Git history, issues, Actions logs or artifacts. Public proofs retain their original bytes; publication is not permission to redact a signed receipt and call it the same proof.

## Links and automation to audit

| Dependency | Expected consequence of making this repository private | Required preparation |
| --- | --- | --- |
| Public GitHub source, commit, PR and issue links | Readers without repository access cannot use them | Inventory each link in the public claims register; replace it with an approved evidence permalink and preserve the old URI as provenance, not an accessible proof promise |
| Raw source URLs and downloadable public artifacts | Anonymous downloads may fail | Package the minimum approved verification inputs in the evidence repository; record file hashes and immutable release identifiers |
| Pages and public documentation hosting | Availability depends on the account and hosting configuration | Inspect the actual configuration before scheduling a move; prepare an evidence-only site without assuming Pages will remain public |
| Public workflow badges and Actions URLs | Badges/log links may become inaccessible | Publish approved CI outcome receipts bound to exact commits; do not label a copied badge as fresh CI |
| Cross-repository checkout, reusable workflows and API consumers | Existing anonymous operations may need authenticated access | Enumerate callers, permissions and ownership; propose narrowly scoped access through existing secret custody, with no credential values in the plan |
| Required checks, branch rules and trusted-main validation | Changing repository identity or workflow paths can invalidate gate assumptions | Preserve the private repository identity and required checks; separately review any proposed settings change with Howard |
| Source-bound evidence and signatures | Private source references are still hashes but may no longer be independently inspectable | State the resulting verification limitation explicitly; provide approved source snapshots only where disclosure permits |
| External clones, forks, caches and downloads | Earlier public copies remain outside our control | Treat the visibility change as future access control, not retroactive removal of already-public content |

These are consequences to verify against the live configuration, not claims that any particular consumer is already broken. No live settings audit or visibility rehearsal has been performed for this draft.

GitHub's current guidance confirms that public forks remain public after detachment. It also identifies plan-dependent loss of Pages and security features; on GitHub Free a published Pages site is unpublished, and a custom domain requires DNS review. The transition audit must therefore include the actual account plan, code-scanning entitlement and custom-domain configuration. See [GitHub's visibility-change documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility), consulted 26 October 2026.

## Ordered transition

1. Finish the Friday run and preserve its exact source, approvals, checks and evidence. Avoid introducing a repository transition into the frozen execution window. If customer timing conflicts, escalate the schedule; do not change visibility during the run.
2. Inventory all public-facing claims, links, workflows, webhook/API consumers, Pages configuration, collaborator access and outstanding PRs. Record an owner and an expected outcome for every consumer.
3. Define and review a minimal public evidence package using public fixtures only. Include a machine-readable inventory of bytes, sizes and hashes, receipt schemas, verifier versions, scope limitations and superseded records. Customer intake stays private and outside the existing public repository throughout.
4. Obtain Howard's approval for the exact new repository name, visibility, initial contents and access model. Creation/publication is a separate action; this plan does not authorize it.
5. Publish the approved evidence package and validate it from an unauthenticated environment. Exercise broken-link checks and offline proof verification using only the published bytes. Do not use a private checkout to conceal a missing public dependency.
6. Prepare exact changes to public documentation and consumers. Obtain approval for any workflow, protection, authority or settings change. Preserve receipt provenance and distinguish the source repository commit from the evidence repository commit.
7. At an approved maintenance time after the run and before first-customer intake, Howard changes visibility. Immediately check authorized clone/read, CI checkout, required checks, public evidence accessibility and documented reader paths. Stop customer intake on any failed access or integrity check.
8. Record the actual transition time, repository IDs, evidence release IDs and verification results. Retain a rollback plan for documentation and access configuration. Do not automatically make the source public again: that would require a new disclosure decision.

## Completion criteria

The source repository is confirmed private; approved users and CI retain necessary access; required gates still apply; the public claims register contains working evidence links and explicit limitations; a reader without private access can verify each advertised public proof; and no customer data, secret or private operational artifact has entered the public evidence repository. Until these checks are measured, this remains a plan.
