# Private source repository transition — decision draft

Backlog lane — 30 October 2026. For Howard's decision after the 5 November run.
This adds to the [earlier transition plan](repo-private-transition-plan.md), which
remains historical. No visibility, access, Pages, workflow or repository setting
changes accompany this draft.

## Current metadata and limits of inspection

The [public repository metadata](https://api.github.com/repos/howardweale/lightyear-carddemo-modernization)
reports repository ID 1329380897, visibility public, default branch main and
has_pages=true on 30 October. The actual Pages URL/domain, account plan, private
security-feature entitlements, collaborator list, tokens, webhooks and anonymous
consumer inventory have not been audited here. No credential or private data was read.

GitHub states that existing public forks stay public and detach after a visibility
change. On GitHub Free, a published Pages site is unpublished on conversion to
private, with custom-domain/DNS implications. Private security features depend on
the relevant plan and licences. These consequences need the actual account and
hosting review; making source private cannot recall old public copies.
Source: [GitHub visibility documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility),
consulted 30 October 2026.

## Options for Howard

| Option | Benefit | Main costs and limits | Decision |
| --- | --- | --- | --- |
| A — existing source repository becomes private; separate minimal public evidence repository/site | Retains the existing source repository ID and internal history while allowing an evidence-only public reader path | Public links/Pages and anonymous consumers need migration; old public copies remain outside control; licensing/disclosure and feature-entitlement reviews required | [UNFILLED] |
| B — new private source repository; original public repository becomes an evidence landing/archive | Clean future source/access boundary | New repository identity and CI/trust references need separate migration; old public history is still public unless separately addressed; more provenance/link work | [UNFILLED] |
| C — defer transition until the evidence/access audit is complete | Avoids a rushed change during run closeout | No customer/private source intake into the public repository; explicit owner and revised decision date needed | [UNFILLED] |

Proposed preference: A, after run closeout and a measured evidence/access rehearsal.
No option is selected by this document. No repository name, account plan or new
visibility is invented. Howard chooses the exact destination, access and timing.

## Proposed source/evidence split

| Keep outside public evidence | Candidate public material, only after disclosure review |
| --- | --- |
| Customer source, procedure/twin code, fixtures, data and derived traces | Results from public or authored synthetic inputs with narrow scope and exclusions |
| Internal source, deployment/adapter details and operational configuration | Minimal public verifier inputs/schemas that work without a private checkout |
| Credentials, private signing/answer material, provider account identifiers | Deliberately published public verifier keys and public-safe receipt fields |
| Investor decks, raise/financial information and commercial partner status | P9 technical proof index and wording rows supported by original public receipts |

A digest is not a disclosure review. Names, paths, low-entropy values and error
strings also need inspection. Do not mirror Git history, issues, Actions logs or
artifacts to the evidence repository.
Planned: preserve signed evidence in place:
a redacted derivative is a different object with an explicit relationship.

## Ordered proposal and acceptance checks

1. Planned: finish the 5 November run/stop closeout and preserve original source,
   proof and evidence bytes before scheduling any transition.
2. Planned: inventory public docs, Pages/custom domain, claim links, raw URLs,
   Release assets, anonymous clients, CI checkout, integrations, collaborators,
   branch rules and security-feature entitlements. Record owners and expected results.
3. Planned: review the exact public evidence inventory, licences and disclosures.
   Keep claims, source/private limitations, provenance and supersession history explicit.
4. Planned: Howard selects A/B/C, repository names/IDs, visibility, account plan,
   access grants, hosting/DNS handling and a maintenance window. No action precedes
   that decision and review of the exact prepared changes.
5. Planned: rehearse the evidence reader path without credentials or private imports,
   and separately verify necessary private CI/reader access. Keep live run authority
   and private material out of the rehearsal.
6. Planned: preserve required checks and protections. Any later workflow, fence,
   trust or integration change belongs to its owner's separate reviewed packet.
7. Planned: Howard performs the separately approved setting/access transition.
   Immediately verify intended private clone/read access, CI checkout/gates and public evidence
   access. A failure stops customer intake and prompts the reviewed recovery plan.
8. Planned: retain actual repository/asset identities, time, outcomes and unresolved
   links. Recovery restores access/docs by review; it never automatically republishes
   private source or recreates keys.

## Decision and sign-off fields

Chosen option and exact repositories: [UNFILLED]

Account plan, Pages/custom-domain and security entitlement findings: [UNFILLED]

Disclosure/licence review and public evidence inventory: [UNFILLED]

Access/protection/integration checks: [UNFILLED]

Maintenance window, operator and recovery plan: [UNFILLED]

Howard's decision reference: [UNFILLED]

Actual transition and post-change evidence: [UNFILLED]
