# Option A â€” repository transition step-2 inventory

Backlog lane â€” draft snapshot, 30 October 2026. No settings change.

Operator direction: keep the existing source repository and make it private,
with a minimal separate public evidence repository or site. Timing is the week
after the 5 November run closes, before any mLogica pilot data reaches this
infrastructure. Names, account plan and exact maintenance window remain Howard's
decision. If closeout is on 5 November, the planning week is 9â€“13 November;
a delayed closeout requires a fresh date decision, not an automatic switch.

[Run-sheet proposal](../../factory/thursday-run-sheet-2026-11-05.md) Â·
[Earlier option analysis](../../repo-private-transition-2026-10-30.md)

## Measured metadata inventory

[Exact metadata snapshot](repository-metadata.json#sha256=df4f9c3bc732d123081250402642d0438e889c408f23a46de945d4764b1df37a).

| Area | Read-only snapshot | Required transition preparation |
| --- | --- | --- |
| Repository | ID 1329380897, public, default branch main | Keep the same repository ID and history under Option A; preserve source/proof provenance. |
| Pages | Public workflow-based site at https://howardweale.github.io/lightyear-carddemo-modernization/ ; HTTPS enforcement true; no custom domain in the API response | Howard selects the evidence-site destination and account plan; confirm anonymous reader access before switching. |
| Public document links | 670 unique repository-facing URLs, 1,689 occurrences in 410 tracked Markdown/HTML documents | Classify each destination as public-evidence replacement, private-reader link or intentionally historical/inaccessible reference. |
| Published Releases | 262 published Releases, 1,731 assets, 8,295,754,269 declared bytes; all asset digest fields present | Review the minimal public subset and rights; retain original bytes/IDs/digests; do not mirror every asset by default. |
| CI source | 73 workflow files, each with an exact source-byte hash | Preserve required checks and private checkout/access; source/workflow changes remain in their owner's separate packet. |
| CI external actions | 26 distinct action references in the source inventory | Check private-repository availability and permissions without broadening tokens or changing source pins here. |
| Actions policy | Actions enabled, allowed_actions=all, sha_pinning_required=false | Record the baseline; no hardening or relaxation is performed by this inventory. |
| Branch protection | Admin enforcement true; required contexts documentation-and-lint and required-ci; force pushes and deletion false | Preserve the actual settings and Howard's separate exact-head policy during the switch. |
| Review settings | dismiss_stale_reviews=true, code-owner review false, required review count 0 | Record the platform configuration separately from Howard's human approval requirement; do not infer permission to merge. |
| Collaborators | One direct collaborator in the API response, role admin; names omitted from this public draft | Howard confirms intended access and any App/team/organization paths not represented by this count. |
| Repository webhooks | Zero in the repository-hooks response; no hook URL or secret appears in this inventory | Do not infer that there are no GitHub Apps, OAuth grants or external integrations. |
| Environments | github-pages, branch-policy protection type | Check exact Pages deployment/access consequences under the chosen private plan. |

Sources: read-only GitHub repository, Pages, collaborator-role, hooks, environments,
Actions-permission, branch-protection, ruleset and paginated Release metadata;
the recorded workflow bytes and public documents. No release payload, private
source, secret value, deployment key or provider account value was inspected.

## Reviewable data files

- [repository-metadata.json](repository-metadata.json): projected metadata,
  source-byte bindings, inventory digests, measured scope and open questions.
- [public-reader-links.csv](public-reader-links.csv): exact URL, category,
  occurrence count and source path/line locations; one row per unique URL.
- [releases.jsonl](releases.jsonl): one published Release per record with every
  asset's ID, name, size, digest and public download URL. Draft Releases excluded.
- [external-actions.csv](external-actions.csv): each external action reference
  and its source occurrence count. It is not an installed-App inventory.

JSON payload links, binary documents, non-document source and external consumer
configurations are outside the link crawl. Existing forks/caches and copies held
by others are outside a repository visibility change. An asset digest field
does not mean this inventory downloaded or independently rehashed its payload.

## Open inventory items â€” owner and decision

| Item | Owner / next check | Current finding |
| --- | --- | --- |
| Evidence repository/site names and hosting | Howard | [UNFILLED] |
| Account plan, private Pages and security-feature entitlement | Howard | [UNFILLED] |
| Installed GitHub Apps/OAuth and indirect organization/team access | Howard, metadata-only review | Not enumerated by repository webhooks/direct collaborators. |
| Deploy keys, credential grants and integration endpoints | Howard privately | Values and private configurations are outside this public inventory. |
| Anonymous external API/raw/clone consumers | Howard and integration owners | Public source links are indexed; external registrations still need owner confirmation. |
| Exact public evidence subset and licences | Howard/disclosure review | [UNFILLED] |
| Actual post-change clone, CI and public-reader checks | Separate maintenance review | [UNFILLED] |
| Exact maintenance window and recovery actions | Howard after run closeout | [UNFILLED] |

Planned: no mLogica/customer data intake, transfer or fixture creation precedes
the completed private boundary and separate intake decision. No source/private
material is copied to the proposed public evidence destination.

## Quick-switch checklist for the later decision

1. Planned: close out the run and retain its original evidence before any change.
2. Planned: Howard selects names, plan and window using this inventory and resolves
   the App/access, external-consumer and hosting gaps above.
3. Planned: review the exact minimal public package and reader-link replacements.
   Test it without private credentials or imports in the separately reviewed route.
4. Planned: approve the exact settings/access change and recovery plan separately.
   Preserve required checks and all source/run authority boundaries.
5. Planned: Howard performs the change, then verifies intended private access,
   CI checkout/gates and anonymous public evidence access. Stop intake on failure.
6. Planned: record actual settings, identities, time, outcomes and open links.
   Recovery must never automatically make private source public again.

CI is intentionally skipped for this documentation draft under Howard's
backlog-lane instruction. Full CI remains mandatory before any later merge after
the run. The manual milestone workflow is not used because it also deploys Pages.
