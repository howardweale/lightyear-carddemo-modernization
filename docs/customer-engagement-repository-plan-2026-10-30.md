# Hybrid repository plan - decision draft

Backlog lane - 30 October 2026. No setting, account, access or CI changes.

## Current direction

The existing repository stays public as the LIGHTYEAR reference implementation
and public evidence. A new small private repository is proposed for customer
engagements only. Its name, owner/account, plan and setup window are UNFILLED.

**Option A full transition: deferred until after the seed round.**
The [step-2 inventory](backlog/repo-transition-step2-2026-10-30/README.md) remains
its starting point. Its October measurements are a historical baseline, with
no automatic visibility change after the run.

## Engagement boundary

The private repository holds only pilot agreements, customer-specific
configuration, engagement decisions/specifications and hashes. Anything touching
a real customer estate belongs in that private engagement boundary or the
customer's infrastructure under separate approval, never in this public reference repository.

**Customer data never enters either Git repository**, including history, issues,
PR attachments, Actions logs, caches, artifacts, Releases, packages and LFS.
Engagement data stays in the customer's infrastructure or private infrastructure under
separate approval. Private visibility alone is not permission to store it.

Planned: exclude customer source, database contents, samples, dumps, raw traces,
generated estate artifacts, result payloads, private expected bundles and secrets.
Keep credentials in external secret storage. Use opaque identifiers and reviewed
private-storage references with hashes; names, paths, URLs and predictable-value
hashes also need disclosure review. Keep agreements and their metadata private.
Folders do not isolate customers from one another: use separate repositories or
another reviewed access boundary when engagements require separate access.

## Account prerequisite

Planned: confirm **GitHub Pro for a personally owned private repository**, or
**GitHub Team or higher for an organization-owned private repository**, before
setup. GitHub documents private protected branches on these plans:
[protected-branch availability](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).
The actual account and entitlement remain UNFILLED.

Private hosted-runner compute and storage draw on plan allowances:
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
Planned: Howard selects a spending limit and retention policy before setup.
No purchase or billing change follows from this draft.

## Protection before any content

The [exact public baseline](backlog/repo-transition-step2-2026-10-30/repository-metadata.json#sha256=6d55455b403b79adf715f2917ec1146591fdf26ce5e59675a5a9cca772537fcf)
records the following. Planned: refresh and match the public controls at setup,
including every required context, without relaxing them.

| Control | Recorded public baseline / private setup requirement |
| --- | --- |
| Branch | main. |
| Required checks | documentation-and-lint and required-ci, both required; GitHub Actions app ID 15368 in the baseline. |
| Administrator enforcement | true. |
| Force pushes / branch deletion | both false. |
| Review settings | dismiss_stale_reviews=true; require_code_owner_reviews=false; required_approving_review_count=0. |
| Up-to-date requirement | strict=false in the recorded baseline. |
| Human decision | Howard's separate exact-head decision remains necessary; a platform review count of zero is not merge permission. |

1. Planned: create an empty private repository, and an initial empty commit with
   no files if a branch is necessary. Configure protection and exact required
   contexts, then independently read back every value **before any file content
   is added**. No admin, direct-push or missing-check bypass. If GitHub cannot
   establish this order, stop at the empty repository and bring the precise
   bootstrap constraint back for a reviewed setup decision.
2. Planned: only after readback, add minimal policy and Linux CI scaffolding,
   using public synthetic fixtures through the protected review path. Establish
   both exact check names and expected App identity, with no customer content,
   run-bound code, trust material or copied cross-platform matrix.
3. Planned: before any agreement, customer configuration or hash record, retain
   private repository ID/visibility, plan entitlement, protection readback,
   exact scaffold head, check results and negative controls proving a missing or
   failing required check and prohibited push cannot enter main. A check name in
   settings alone is insufficient. Recheck collaborators, Apps, Actions access,
   log/artifact scope and retention; any mismatch blocks engagement content.
   Keep setup records private, not in this public draft.

## Light CI

Planned: Linux only by default, with short bounded jobs for document/schema
validation, configuration allowlists, links, secret/payload refusal and hash
record format. Preserve stable documentation-and-lint and required-ci contexts;
the latter aggregates applicable checks and refuses missing evidence.
Synthetic inputs only, with no customer connection, data pull or model call.

Planned: add Windows or macOS only for a documented engagement need and reviewed
CI/cost decision. Emit required contexts on every applicable PR, including docs;
a skipped or absent required job is not success. Limit permissions and retention,
keep customer-network runners separate, and restrict logs/artifacts to sanitized
metadata. Use synthetic negative controls plus human disclosure review because
scanning alone cannot guarantee absence of customer data.

## Public repository hygiene

The [static inspection record](backlog/repo-transition-step2-2026-10-30/public-hygiene.json)
binds the exact root README and licence-notice bytes.

- LICENSES/README.md and THIRD_PARTY_NOTICES.md explicitly exclude original
  LIGHTYEAR source from the third-party grants.
- **README gap:** the root README links to third-party licences but does not
  plainly state that no licence is granted to original LIGHTYEAR source.
- No root LICENSE file or original-source grant was found in the scoped root
  file/text inspection. This is a text finding, not a legal opinion.
- An explicit source-available / all-rights-reserved notice and proposed README
  insertion are prepared **outside Git** for counsel. No notice or licence text
  is committed or put into effect by this PR.

Planned: counsel confirms the rights holder, wording, third-party carve-outs and
separately agreed rights before a later reviewed publication change. Until then,
the README clarity check remains OPEN; this draft cannot confirm both texts
already satisfy the requested clarity.

## Howard's decisions

Private repository name and owner/account: UNFILLED

GitHub Pro / Team entitlement, spending and retention: UNFILLED

Post-run setup operator and window: UNFILLED

Engagement access/isolation and data-infrastructure approval: UNFILLED

Protection readback, scaffold checks and refusal controls: UNFILLED

Counsel wording and rights-holder disposition: UNFILLED

Draft only; CI is intentionally skipped with [skip ci].
Planned: full CI before any merge after the 5 November run closes.
No repository creation, customer content, signing, setting or licence change.
