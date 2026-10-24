# K1 unfenced Java formatting preparation

This draft prepares a CI-only formatting patch for 33 explicitly named
production Java files. No Java file is reformatted by this preparation commit.
The scope excludes the recomputed COPAU/F2 and POSTTRAN union (789
paths and 2 prefixes), SourceEdits, and reserved authorization
Java. The job re-derives both fences from the trusted event base before capture
and after formatting; exact names and frozen inventory prefixes both refuse.
There is no automatic date-based unlock. Held fenced formatting stays in #451.

The formatter versions, input hashes and POM include list are exact. CI captures
all tracked file bytes, rejects out-of-scope changes, inventory or mode changes,
and retains a patch plus before/after hashes. Import reordering, long-string
reflow and Javadoc formatting are disabled. Six synthetic CI tests cover scope,
path and fence refusals, inventories and source bindings. Nothing runs locally
except Howard's separately authorized static lint command.

Before this draft can be ready for merge, review the actual CI patch, preserve
the independent oracle and frozen inputs byte-for-byte, commit formatting in a
separate format-only commit, and rerun all applicable proof suites and gates on
that final head. If inputs change, prepare a separately reviewed scope update
first; never silently accept new bytes. This preparation's capture intentionally
refuses already changed source hashes. Large patches must be split within the
review limit. A green patch producer alone is not final formatting proof.

Idiomatic-index change: zero. Paragraph classifications, mutation thresholds,
engine counts and Java behavior are unchanged. Checkstyle, Error Prone and
SpotBugs are subsequent K1 work; this draft claims no complete findings index.
No signing, factory execution, model calls, Tower access or spending authority.
POSTTRAN and the private answer-key helper retain priority; ten-minute checks
remain off. Exact final-head approval is required.
