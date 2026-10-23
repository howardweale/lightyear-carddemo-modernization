# K1: initial text hygiene

This first increment replaces four broken range separators in the header
comment of AccountUpdateService with ASCII hyphens. Executable Java is byte
identical. The two live paragraph manifests update only that source hash;
their classifications, spans and all other bindings remain unchanged.

Required lint scans tracked service Java for invalid UTF-8, replacement
characters and known mojibake sequences. Four synthetic CI tests cover valid
Unicode, malformed bytes, line locations and the actual tracked inventory.
The guard reads fenced files but changes none of them. No local tests run.

Idiomatic-index change: engine counts unchanged; one affected source file and
four mojibake occurrences removed. This is not the Checkstyle, Error Prone or
SpotBugs findings index. Formatter selection, a formatting-only commit on
unfenced files, and the static-analysis baseline remain subsequent K1 work.
Fenced formatting is a separate draft held through post-run verification and
after 31 October. Fresh proof CI and Howard's exact-head approval are required.
