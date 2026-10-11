# Indexed key ordering and runtime I/O gaps

The proposed adapter stores key bytes in cp037 in an indexed shadow record.
Before each random READ, START, WRITE and REWRITE, encode every primary and
alternate key; after retrieval, decode only those key fields back into the
program record. Preserve payload bytes, record widths, duplicate flags and
file status. Sequential READ NEXT then follows the backend's unsigned byte
order of cp037 keys rather than ASCII. Program collation alone cannot do this.

The isolated Ubuntu probe compares actual indexed ASCII and cp037 storage with
space, A/Z, a/z and 0/9. It checks READ NEXT order, duplicate status 22, EOF10,
random READ, REWRITE persistence and START positioning. This proves only the
probe's one-byte primary keys. Full composite/alternate keys, range boundaries,
key changes and integration with every legacy I/O statement remain unproven.
**The decimal-only production restriction stays.** No input or frozen twin
adapter has been silently changed.

CBTRN02C's REWRITE failure109 now always appears in new invariant receipts'
unresolved register. Observed109 reject IDs are retained; absence does not mean
unreachable or tested. It is a runtime I/O failure, not a generated business
input condition. The register blocks promotion pending controlled fault
evidence and source-based operator adjudication. Two focused tests passed.

Multipass is not available on this Windows host (`Get-Command multipass`
returned no executable). No VM or machine configuration was changed. The
alternative is an explicitly approved isolated Ubuntu24.04 amd64 host, with
the same pinned compiler packages, clock adapter, source/build paths and
complete runtime-library inventory; run the public CI commands there and
compare all input/output/build hashes with GitHub's artifact. GitHub-hosted
Ubuntu execution alone is not an independent Multipass reproduction. Provisioning
that second host requires Howard's approval; no cloud account was accessed.
