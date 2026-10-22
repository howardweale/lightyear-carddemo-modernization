# Status freshness correction — 22 October 2026

The status rebuild now reads main and PR #362 metadata and their exact-head
required-ci checks through the GitHub API in CI. It records the observation
time, checks for head/state races, and renders missing, pending and failed
checks explicitly. API failures stop the rebuild before any publication.
The same captured input drives rendering and its freshness check; status
generation with no live input remains a reproducible historical rendering.

The POSTTRAN days-remaining value uses the new observation time when present,
not the 17 October delivery snapshot clock. The original delivery evidence and
clock file remain unchanged. Generated current-status files are still written
only by their existing CI workflow and proposed through a draft status PR.

MS-109's PR360 row and the status renderer's CMS sentence explicitly describe
the 17 October state. This labels the historical observation; it does not
change CMS scope or claim a current PR state. CMS remains parked.

This is an observation at rebuild time, not a continuously updating dashboard.
It adds no polling schedule, signing, activation, model call or release authority.
