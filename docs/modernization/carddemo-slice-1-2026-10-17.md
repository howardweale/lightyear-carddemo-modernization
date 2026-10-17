# CardDemo slice 1 evidence — 2026-10-17

Authorized by Howard; prepared by Codex. Unsigned; overall **incomplete**. No release, signing, activation or Phase 2 authority.

[CI measurement](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/39044984415) at PR head `1f638ed0f0e9c132bdb99c63cfbf0dc4d8b2d76c`; checkout merge commit `cf43585fc4fb7ae4466f7414eb4ae5028bcccad8`. This is data evidence, not full PR-green or screen acceptance.

| Gate | Result |
| --- | --- |
| Generated VSAM records | 500,000; five files × 100,000; raw and typed round trips passed |
| Volume browse | 372/372 |
| Byte-key edge browse | 58/58 |
| Alternate keys | 20,000 distinct keys each in CARDDATA and CARDXREF |
| Migrated IMS corpus | 27/40 matched; 13 unsupported; 9 returned-segment comparisons; after-state compared for supported cases |
| Screen API / browser sessions | 0 / 0 |
| Screen-handler mutants | Unmeasured; acceptance requires at least 90% caught |
| Compose acceptance / final Factory request | Unfinished / not prepared |

## Durable evidence

[Receipt archive](https://github.com/howardweale/lightyear-carddemo-modernization/releases/download/evidence-2026-10-17-carddemo/carddemo-data-evidence-2026-10-17.zip); downloaded again and SHA-256 verified: `547dbaed40d237d2b820877873001cee293534a305301c2f91fd3de7df9c00ea`. The JSON companion pins each receipt, generator, dataset, mapping plan and corpus hash. Historical records remain unchanged.

## Remaining gaps

- 13 of 40 IMS corpus cases have no migrated adapter implementation; the historical model is a separate baseline.
- Public IMS unload framing and a native CICS/IMS baseline are not established.
- Account-update and pending-authorization services, linked AUTHFRDS action, and complete source semantics remain unfinished.
- Independent screen interpreter, API/Playwright sessions, every field/attribute/cursor/message and database after-state comparison remain unfinished.
- Screen-handler mutation catch rate, Docker Compose acceptance and the final unsigned Factory request remain unfinished.

## Source quirks and scope

- Generic VSAM browse starts at the first key greater than or equal to the prefix and continues to EOF.
- Non-display 00/FF/mixed primary keys are lossless in CARDDATA, CARDXREF and USRSEC.
- Historical GNP-no-parent DJ and PROCOPT-G denial expectations are corrected to GP and AM; not counted as native IMS verification.
- COACTUP account rewrite buffer omits ACCT-ADDR-ZIP present in CVACT01Y; screen proof must compare bytes rather than match field names.
- Menu options 3 through 10 use the explicit not-in-this-slice endpoint; fifteen other BMS maps remain later slices.
- Pending authorization PF5 requires COPAUS2C AUTHFRDS plus IMS detail effects within one interaction transaction.

Required screens: COSGN00, COMEN01, COACTVW, COACTUP, COPAU00 and COPAU01. No customer data, actual Factory signatures or Phase 2 execution were used.
