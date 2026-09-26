# iDempiere native reconciliation

The release-13 experiment now passes **20 migration-pair checkpoints and one
four-pair maintenance checkpoint** on local Oracle 26ai Free and PostgreSQL 15.
That is **24 pairs / 48 native script executions**, with **zero unexplained
final data differences** under explicit, field-specific rules. Oracle has no
remaining invalid objects or compilation errors after native recompilation.

Historical replay now also completes **1,125 regular pairs across 20 release
checkpoints**, with **2,255 native script attempts**, including five recorded
recovery attempts. All checkpoints have zero unexplained data differences on
the explicitly corrected path. This covers all **1,074 original regular pairs**
plus **51 older prerequisites**. The four maintenance pairs above are a separate
release-13 experiment. Repeated pairs are not added as new unique coverage.

This supersedes the unresolved findings in [PR214's original experiment](../idempiere-runtime/README.md)
for this corrected execution path. The original observations remain unchanged.
The [receipt](receipt.json) and [evidence archive](evidence.zip) distinguish raw equality,
logical data admission, successful execution, and broader qualification.

## What was corrected

1. **Registration works.** Calling the native function directly inserted one
   completed/applied registration row on each engine. The probe restored its
   affected tables and verified their previous hashes. Oracle's autonomous
   commit required explicit restoration; rollback alone would not suffice.
2. **Starting data now comes from one source.** A canonical Oracle seed snapshot
   supplied all 185,275 rows in the 911 common base tables. PostgreSQL's 3,807
   foreign keys were checked explicitly after loading, with zero violations.
   Before this correction, 134 common tables differed between official seeds.
3. **Literal input bytes are controlled.** Windows CRLF inside SQL strings had
   produced different stored help/email text in SQL*Plus and psql. The rerun
   dispatched canonical LF source matching the pinned logical SHA256. Business
   text is compared exactly; no whitespace-stripping output rule was added.
4. **Native validity is checked.** The upstream `DBA_RECOMPILE(NULL)` resolved
   the original 14 invalid Oracle objects. Recompilation/readback also follows
   new DDL; successful script exit alone cannot establish validity. The final
   audit also found 2,914 enabled foreign keys still marked unvalidated. Oracle
   natively validated all of them without rewriting data. All **3,826 final
   Oracle foreign keys** are now enabled and validated; no invalid objects or
   compilation errors remain. The completed release-13 containers are stopped,
   with their data preserved.

The nine application-table findings from the earlier run are resolved on this
corrected path. They included unequal starting timestamps, differing newline
handling in literal text, and independently generated tree-row metadata.

## What explicit equivalence means

Raw observations and every differing field value are retained. Rules validate:

- Newly generated UUIDs only in named metadata columns: well formed, nonzero,
  unique, absent from that lane's starting rows.
- Execution timestamps only in named columns and within recorded execution
  windows. Existing-row updates require a separately enumerated policy.
- Registration filenames exactly `oracle/<executed script>` and
  `postgresql/<executed script>`, with the same script name and applied status.
- Two scheduler timestamps only when native timezone types/offsets are observed
  and both values represent the same instant.

Historical policy revisions are retained by hash. They explicitly add existing
`AD_TreeNodeMM.Updated`, then `AD_Field.Updated`, then new `AD_Message_Trl`
metadata, and finally UUID columns on seven named translation tables. The UUID
rules still require a new row, a valid unique value and no reuse from the prior
state; they do not accept changed UUIDs on existing rows. The time rules still
require a recorded native execution window. Each rejected checkpoint remains
available alongside its reviewed successor.

For historical data, native Oracle NUMBER and PostgreSQL NUMERIC values may
also differ only in retained decimal formatting, such as `23.9` versus `23.90`.
The rule requires finite, exactly equal decimal values and observed native
numeric types; it uses no float tolerance. Raw strings remain visible. Boolean
values are never implicitly equated to numeric zero or one.

An Oracle-only historical repair script also re-registers an older migration.
Its description and update timestamp are validated against the actual native
function body and the recorded successful function calls, including the call
committed before the runner failure and the recovery call. The other lane's
untouched audit record must remain unchanged. This admits an explained audit
history difference; it does not manufacture matching registration events.

All other values remain exact. A prior admitted difference can be carried forward
only while both raw values are unchanged and the prior checkpoint is bound to
those starting snapshots. Unknown tables, column sets, row keys or differences
block advancement.

The strict shared-start receipt still says `admitted: false`: two native
scheduler strings differ in fractional-second formatting. The separate logical
[entry checkpoint](evidence/rerun/entry-checkpoint.json) admits the same instants.
Likewise, the first maintenance checkpoint correctly rejected 553 fields under
the narrower migration policy. The [reviewed maintenance checkpoint](evidence/maintenance/processes_post_migration/reviewed-checkpoint.json)
validates explicitly enumerated translation/access-row UUIDs and clocks. It
retains **640 total allowed raw field differences**, including 87 carried from
the migration tranche. Neither failed checkpoint was overwritten.

## Historical replay

The [release-by-release results](history-results.md) derive their counts from
the retained native execution receipts and final admitted checkpoints.

An official release-3.1 seed was located and pinned by archive hashes. Both
engines start from 843 common tables copied from one Oracle snapshot, with
3,402 foreign keys checked. Two prerequisites required explicit correction:

- The old PostgreSQL seed declared `AD_ModelValidator.Updated` as `date`, losing
  time-of-day present in Oracle. The bootstrap changes that column to timestamp
  and restores the exact canonical values.
- Its UUID function requires the native `uuid-ossp` extension. The pinned
  upstream historical installation script specifies this prerequisite.

The current migration inventory begins too late for that seed: 44 archived
`i3.1` pairs and seven `i3.1z` pairs are dependencies. These **51 prerequisite
pairs are outside the original 1,078-pair denominator**. Failed attempts are
retained, including the first missing-column error and the missing-extension
error; no uncertain state was silently reused.

The first complete 44-pair prerequisite attempt revealed two additional
execution-environment issues: SQL*Plus removes trailing spaces within multiline
string literals, and five registrations fell outside host-clock windows.
The retry uses exact Oracle statement dispatch and database-clock observations.
These changes preserve source literals and narrow timing validation rather
than suppressing differences. Historical checkpoints are per release, not proof
of each individual script's isolated effects. Advancement stops at the first
unadmitted release.

### Explicit historical target corrections

The release-5.1 comparison exposed two actual stored-value differences in the
upstream PostgreSQL migration sources. These are repaired in the target database,
not accepted by a comparison exception:

- `201803141439_IDEMPIERE-3655.sql` uses PostgreSQL `TO_DATE` for a literal with
  time-of-day. The target correction restores `2018-03-14 14:27:47` as timestamp
  on `AD_SysConfig` row 200102, matching the Oracle-authored value.
- `201804121657_IDEMPIERE-3685.sql` stores an unqualified ordering expression on
  `AD_Tab` row 107. The target correction retains the Oracle-qualified expression.
  Native queries verified identical ordering on the observed `AD_Field` data,
  with an explicit ID tie-breaker. This is a bounded probe, not application proof.

Release 6.2 exposed one further source-semantic difference:
`201908232051_IDEMPIERE-4034.sql` inserts an empty optional tooltip. Oracle stores
NULL and PostgreSQL stores an empty string. A single guarded target update on
`AD_Message` row 200537 preserves the Oracle result. No empty-string-to-NULL
comparison rule was introduced.

A second optional tooltip, `AD_Message` row 200593 in release 7.1, receives the
same explicit target correction, bringing the total to four targeted field
updates.

All four updates require the exact observed old value and exactly one affected row.
The original rejected checkpoint, correction SQL, hashes and after-state check
are retained. Two newly inserted message translations use the existing UUID and
execution-clock validation pattern, limited to their named metadata columns.
Continued historical checkpoints depend on these explicit target repairs;
they must not be presented as equivalence of the unmodified upstream scripts.

### Runner boundary recovery

A release-7.1 script exposed a native dispatcher bug: a slash-terminated Oracle
`CREATE TYPE` was incorrectly grouped with the following function. The runner
stopped on the native error. Its corrected boundary parser preserves each exact
statement, including quoted newlines and trailing literal spaces. An audit of
all **303 earlier successful Oracle dispatches** found no changed statement
sequence or hash under the correction. The malformed type's creation time,
source text and absence of dependents were verified before targeted cleanup;
only the failed Oracle script was retried. PostgreSQL's successful execution
was retained. The original failure, retry, resulting state and extra native
execution are counted separately.

### Release-7.1 follow-up migration defects

The next 89-pair tranche exposed 1,345 raw field differences. The resolution
retains that checkpoint and applies explicit corrective writes:

- Oracle's Web Store migration uses `LIKE 'W\_%'` without an `ESCAPE` clause.
  PostgreSQL interprets the backslash as an escape by default; Oracle does not.
  The corrected Oracle source specifies the escape character explicitly. Native
  probes identify the same 11 Web Store table names. Guarded corrections restore
  the intended classification on 399 rows, changing only their differing
  EntityType/Updated/UpdatedBy fields and preserving matching later metadata.
- PostgreSQL drops time-of-day in 41 field timestamps through `TO_DATE`. Two
  further field/tab timestamps differ as literal values in the paired sources.
  Explicit target corrections restore those 43 Oracle-source timestamp values.
- Both engines convert DUNS from fixed-width to varying-width text, but PostgreSQL
  drops the old padding. Ten target corrections preserve the exact observed
  source contents. No general trimming or string-normalization rule is used.

That is **452 guarded native row updates**, separately recorded from the
migration script count. Remaining generated account/tree-row clocks are checked
against native execution windows on explicitly named columns. Monetary values,
module classifications, identifiers and static timestamps are not exempted.
The corrected whole-state checkpoint has zero unexplained differences.

The runner also now retains per-engine receipts before returning to the paired
controller, supports the encountered display-only SQL*Plus settings, captures
DBMS_OUTPUT, and preflights every Oracle file before dispatching a release.
All 1,125 planned non-maintenance scripts pass boundary preflight. A PostgreSQL
registration placeholder completed before a prior Oracle preflight rejection;
its timing receipt was not retained. That attempt is preserved as incomplete,
its exact registration/counter side effects were restored, and the pair was
rerun with complete receipts. A later Oracle rejection on an empty delimiter
occurred before any script statement was submitted; it is not counted as a
native script execution. Successful PostgreSQL evidence was retained.

### Release-8.2 constraint migration repair

The Oracle constraint migration `202112051645_IDEMPIERE-5075.sql` assumes all
2,920 named foreign keys already exist. Native execution stopped after 52 DDL
statements because the older starting schema lacks 72 of those constraints.
The native catalog confirms no foreign key on those columns under another name.
The recovery retains the successful DDL prefix, skips only those 72 absent
`DROP CONSTRAINT` statements, and executes every supplied `ADD CONSTRAINT`.
PostgreSQL's already successful placeholder is retained. The failed attempt,
precise source repair, and additional Oracle execution remain separate evidence.
This is an explicitly repaired upgrade path, not an unmodified-script pass.

The same tranche contains 65 field-update timestamps with different fixed
literals in the two source files. Each is checked against the last matching
upstream statement and repaired on PostgreSQL with an exact old-value guard.
One generated `AD_Column.Updated` value is validated within the recorded native
execution window; fixed timestamps and other column metadata remain exact.

### Release-9 witness continuity

A migration expands `AD_Message_Trl`'s primary key to include its client ID.
Previously validated UUID/clock differences are carried to the new key only
when both before catalogs agree on the old key, the new key contains it, and
both raw before/after field values remain unchanged. The witness names its old
key and predecessor checkpoint. Missing catalog evidence or changed values
still block admission. New business-partner tree/account metadata receives the
same narrow UUID and native-clock checks; no business values are exempted.

### Release-10 client timeout recovery

The PostgreSQL client timed out after dispatch of a two-statement script. Native
readback showed its registration and fixed Product-window update had completed,
but no client exit/timing receipt survived. The full state and registration are
retained. Recovery restores only the exact registration row, sequence counter
and last-script pointer, then repeats the idempotent fixed-value update through
a new recorded PostgreSQL execution. Oracle's successful receipt is retained.
The original PostgreSQL attempt is counted separately, with its missing client
receipt stated explicitly. Future attempts persist their native start before
dispatch and retain timeout diagnostics; no timeout triggers automatic retry.

### Release-10 value corrections

Three guarded native writes correct observed source differences: PostgreSQL's
extra trailing space in a field display expression, PostgreSQL's `TO_DATE`
loss of time-of-day, and an extra closing brace in Oracle's DatePicker message.
A retained Java `MessageFormat` probe renders the Oracle source as `Last Week}`
and `Last 2 Weeks}`, versus the intended PostgreSQL `Last Week` / `Last 2 Weeks`.
The Oracle correction removes that demonstrated user-visible defect. There is
no generic whitespace or message-text comparison exemption. Print-layout
`Updated` metadata uses a named execution-window rule; sequence/layout values
remain exact.

### Release-11 redundant index drop

Oracle's selection-table migration drops a primary-key constraint and then
explicitly drops its index. In this historical schema, the first operation
already removed the owned index. Native readback proves the index is absent;
the recovery omits only the redundant drop and runs the remaining source.
Ten completed statements, including registration and committed DDL, are retained
as the original prefix. A composite receipt binds that prefix to the successful
suffix, preserving the original registration's clock window and recording the
additional Oracle attempt separately.

### Release-11 catalog and registration changes

PostgreSQL's upstream migration replaces the DUAL table with a view. The rule
accepts only its exact observed constant-`X` definition, and native queries on
both engines confirm one `X` row. A view with a filter or another value fails.
One paired migration legitimately has different Oracle/PostgreSQL filenames;
its registration names and paths are checked against the respective executed
source files, including applied status. Neither audit record is renamed.
Two scheduler timestamps use the same-instant rule only after native timezone
types and the offset-preserving capture contract are verified. The remaining
SQL-default string differs by one space; native expression probes agree, and
one guarded PostgreSQL update preserves the exact Oracle-source text.

### Release-12 whitespace cleanup and missing dictionary rows

The original Oracle cleanup predicate `LENGTH(TRIM(value))=0` does not match
whitespace-only strings because Oracle turns the trimmed empty string into
NULL. Native probes demonstrate the difference from PostgreSQL. The corrected
Oracle predicate uses `TRIM(value) IS NULL AND value IS NOT NULL`. Before each
write, its exact matched primary keys must equal the retained differing rows;
matching or subsequently changed rows cannot be silently swept into the repair.

The Oracle source also inserts three missing DocumentNo dictionary entries that
the PostgreSQL source omits. With both engines built from the same old Oracle
seed, PostgreSQL needs those inserts too. Native target-catalog checks verify
the corresponding physical columns exist before executing the three exact
source INSERT statements. This corrects the migration path rather than accepting
missing rows or treating all blank text as equivalent.

### Release-13 historical field dictionary repair

The Oracle source restores seven missing field dictionary entries, while its
PostgreSQL counterpart omits them. The canonical older seed makes these entries
missing on PostgreSQL as well. The recovery verifies all seven target table /
column references and absence of the IDs, then executes the exact seven source
INSERT statements. No row-set difference is waived. These are seven additional
native corrective inserts, separately recorded from the paired script count.

## Final historical validity and cleanup

Native validation accepted all **2,914** outstanding Oracle foreign keys, with
no data rewrites. A fresh full capture verifies every table's row multiset is
unchanged by validation and the final logical checkpoint remains admitted.

| Final native check | Oracle 26ai | PostgreSQL 15 |
|---|---:|---:|
| Foreign keys present and validated | 3,794 | 3,822 |
| Unvalidated constraints | 0 | 0 |
| Invalid / unusable indexes | 0 | 0 |
| Invalid objects / compilation errors | 0 / 0 | Not the same catalog model |

Oracle also has no disabled constraints or unusable index partitions. Different
constraint counts are reported explicitly; this experiment does not assert
schema equivalence. These are the upgraded release-3.1 databases, separate from
the fresh release-13 seed experiment's counts above. Both historical containers
are stopped and their data retained. No GCP resources were started.

A final audit matches all **1,125 successful Oracle dispatches** to their exact
statement sequences and hashes. Original failed prefixes and explicit suffix
repairs retain their separate evidence.

## Boundaries and reproducibility

This is a native **logical base-table data** experiment on a public reference
estate. It does not establish full schema, application, historical-upgrade or
platform qualification. Oracle JVM metadata and the PostgreSQL DDL helper are
explicitly scoped; the historical PostgreSQL `dual` helper must contain exactly
one `X`, matching native Oracle DUAL. Native structure is retained but not
asserted structurally equivalent. Oracle 26ai executing an old seed does not
constitute testing on Oracle 11g or 19c.

The static gate remains **780 / 111,293 decided units**. No Oracle catalog
conformance or platform-qualification counters were advanced by these results.

The deterministic `evidence.zip` contains every member named in the receipt.
Extract it into this report directory to inspect the original evidence paths.
The release table links to that archive; each exact checkpoint member is named
in `receipt.json`. Three directly linked checkpoints are also kept outside it.

The receipt hashes the included checkpoints, raw field witnesses, execution
logs, pinned source hashes and controller source. SHA256 seals establish
integrity, not independent attestation. Large SQL/log payloads use deterministic
gzip; the receipt records both compressed-file and original-byte hashes.
Complete all-row snapshots and private
local connection settings remain in ignored `work/` directories; this compact
publication does not pretend to embed a full database backup. Controllers are
research-run scripts, not an unattended production migration tool. Published
controller copies reflect the final implementation; earlier attempts retain
their actual dispatched-source hashes and logs.

All work used local Docker. No GCP resources were started.

## Verification

The affected regression suite ran **133 tests successfully, with two skips**.
One skip is the Windows symlink-privilege test. The other is the optional full
pinned-corpus replay, which was run separately with `IDEMPIERE_SOURCE` set and
passed. Its published static counts and decisions are unchanged.

Evidence tests verify every archived member hash, original bytes of compressed
payloads, release-count arithmetic, checkpoint bindings and native validity
receipts. A private-credential scan of the complete archive passed; all 34
published Python controllers compile. `git diff --check` passed.
