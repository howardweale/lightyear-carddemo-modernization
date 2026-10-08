# Enumerated source normalization proposal — requires Howard's approval

Draft only. The executable sketch is tools/b06_image_artifacts/source_normalization_proposal.py.
It is imported only by offline triage/tests, not capture, producer, replay or
admission. Five tests passed. No Docker or Tower request.

## Exact scope

Only these two exact case-sensitive paths in the following 21 exact symbolic
names are eligible; no `.source` name-pattern allowlist:

- `org.adempiere.base.callout.source`
- `org.adempiere.base.process.source`
- `org.adempiere.base.source`
- `org.adempiere.install.source`
- `org.adempiere.payment.processor.source`
- `org.adempiere.pipo.source`
- `org.adempiere.plugin.utils.source`
- `org.adempiere.replication.source`
- `org.adempiere.report.jasper.source`
- `org.adempiere.server.source`
- `org.adempiere.ui.source`
- `org.adempiere.ui.zk.source`
- `org.apache.ecs.source`
- `org.compiere.db.oracle.provider.source`
- `org.compiere.db.postgresql.provider.source`
- `org.idempiere.hazelcast.service.source`
- `org.idempiere.tablepartition.source`
- `org.idempiere.webservices.resources.source`
- `org.idempiere.webservices.source`
- `org.idempiere.zk.billboard.source`
- `org.idempiere.zk.extra.source`

## Rule B: OSGI-INF/l10n/bundle-src.properties

Require line 1 exactly `#Source Bundle Localization`. Require line 2 to be exactly
`#<English weekday> <English month> <two-digit day> HH:MM:SS UTC YYYY`, validate
the actual calendar/date/weekday, and replace **only that line's comment body**
with `#<generated UTC timestamp>`. Preserve its newline bytes. Every other byte,
including all property keys/values, comments, ordering, whitespace and encoding,
remains exact. Reject other zones, malformed timestamps, moved comments or
unapproved files. Tests include changed resource values and invalid dates.

## Rule C: META-INF/MANIFEST.MF

Retain only the already approved normalizations of Bundle-Version's qualifier,
Built-By, Bnd-LastModified and Build-Timestamp. Add exactly one rule for the main
`Eclipse-SourceBundle` header: unfold its continuation for validation; require
host = this enumerated symbolic name without the final `.source`, version =
the manifest's **full** Bundle-Version, and `roots:="."` with no extra directives.
Retain host and major.minor.micro; remove only the fourth qualifier. Serialize
this one normalized header to one line, preserving its original newline style.
This explicitly canonicalizes folding only for this selected generated header.
Host changes, base-version changes, root changes and extra attributes fail or
remain unequal. No Import-Package, Require-Bundle, other header, named section,
class or resource normalization is allowed. Header presence/case/order remains
bound. Tests cover wrong host/version/roots and unchanged import differences.

## Decision boundary

All 21 observed source bundles have only B/C changes. Their draft comparisons
pass. A new class or other resource difference stops this route; never add a
normalization implicitly. This proposal changes neither current policy nor
historical outcomes. The test bundle's exact non-candidate artifacts still block
rebuild-per-run identity, so the build-once draft is supplied separately.
