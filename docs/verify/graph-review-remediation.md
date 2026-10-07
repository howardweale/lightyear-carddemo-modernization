# Verify graph review remediation

Date: 2026-10-06. Operator review; not independent attestation.

Prepared on `codex/verify-graph-review-r1` from main
`691059f737e87a8e31472d470472aa461ec79845` in response to the review of
PR259, PR261 and PR263. This record describes local implementation and checks;
it does not assert publication or live graph activation.

## Implemented

- Public source overlap classification now checks exact value bytes in each
  hash-verified public source file, including unquoted numeric and name values.
  It does not join files or normalize whitespace/case to create an overlap.
  Every source-literal match still requires its exact hash acknowledgment;
  protected matches cannot be waived.
- Tower displays the public CardDemo reference scope, the UTC review expiry,
  and the required acknowledgment tokens. Both the signing path and the UI
  reject an incomplete acknowledgment; protected matches block approval.
  The leak report must bind the exact projection and lane under review.
- A read-only activation checker starts the real MCP toolkit child, checks
  discovery and the judge's projection binding, exercises an approved search,
  and confirms the attempt budget is unchanged. It makes no model calls and
  submits no candidates. Its tests use an explicit public fixture HTTP responder,
  not a substitute claim of Linux judge isolation.
- The A/B draft prespecifies paired cost and token analysis before any model
  session. Failed-session costs remain included; zero verified programs means
  undefined cost per verified program. Cached tokens, missing data and undefined
  bootstrap samples have explicit treatment. Paging remains bundled with graph
  access, not claimed as an independently measured intervention.
- The [Tower user manual](../control-tower-users-manual.md) gives the incoming
  CardDemo file workflow: arrival checks, acceptance, observation, normalization
  proposals and Howard's decisions, verdict selection, Java replay, difference
  disposition and evidence release. Normalization must be decided before the
  first immutable verdict. The legacy viewer and scoped Decision Console are
  distinguished.

## Validation

- Focused graph, Tower, CardDemo intake and integration suite: 83 tests, passing
  with two Java-dependent tests initially skipped because the JAR was absent.
- Offline Maven build: 11 Java tests passed. The two skipped intake tests were
  then run successfully alongside the final graph projection suite: 16 tests
  passed, no skips. These are overlapping checks, not additive unique counts.
- Real MCP stdio activation-check tests passed; desktop and mobile Tower browser
  checks passed, including refusal before acknowledgment and successful signing
  after the exact acknowledgment in a disposable fixture authority.
- JavaScript syntax, Git whitespace checks and the graph protected-path guard
  passed. All seven PowerShell blocks in the Tower manual parsed successfully.

No Docker runs or model calls were made. B05, B06, `work/ms94`, template-r1 and
J1 predicates were not changed. The running B06 Tower was not restarted or
reconfigured. Historical October 4 live-client results remain unchanged.

## Remaining activation gates

Follow the [activation checklist](graph-activation-checklist.md). A real public
INTCALC projection still needs its actual lane-inventory leak scan and Howard's
Verify-scoped Tower decision. The Verify authority path and access to the Mac
Ubuntu VM have not been supplied. No B06 authority is reused for this purpose.

Run fresh graph-off separate-user Linux acceptance and Inspector checks on that
VM, then initialize the approved graph-enabled judge/toolkit and retain the
read-only activation report. Check expiry at the start of the review date in
UTC. Revocation requires a fresh trusted Tower proof/head and replacement of the
old serving task; an archived offline approval is not a live revocation feed.

Until these gates pass, graph activation and Linux isolation remain pending.
No efficiency result, live-client graph result or independent human attestation
is claimed by this implementation.

## Operator handoff

The [Mac command sheet](mac-graph-review-commands.md) runs the fresh isolation and baseline protocol checks. A [separate Verify authority](tower-authority-proposal.md) is proposed after Howard confirmed none exists. It has not been provisioned. The Tower manual is also supplied as a Word document at ../control-tower-users-manual.docx.

The five-page Word manual was rendered using installed Microsoft Word and every page was visually inspected. The packaged LibreOffice renderer was attempted first but LibreOffice is not installed on this Windows host. Rendered QA files remain local and are not publication payloads.

## CI dependency correction

The first PR267 broad Ubuntu run executed 2,482 tests and failed the new MCP protocol test because that baseline job does not install the optional MCP SDK. The test now follows existing optional-SDK skips in baseline jobs. The dedicated Verify workflow installs the verify extra and explicitly imports MCP before tests, so a missing SDK fails that job rather than silently skipping protocol acceptance. The original failed CI log remains available.
