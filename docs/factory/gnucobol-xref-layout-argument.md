# INTCALC XREF FD scale argument — 2026-10-11

This is a listed equivalence argument for the single mutation
`CBACT04C-receiving-scale-72-6`, scoped to the public twin's pinned host runtime.
It is not z/OS equivalence, operator acceptance, or a release approval.

The exact CBACT04C source hash is
`5084bb8b0c9a0f0199f737487ae1863f12e43cabbdc459a62b6b67bedc683cc4`.
The mutation adds one fractional display digit to the unused FD customer field
at line72, increasing the FD maximum from50 to51 and shifting the account-key
buffer by one byte. It does not change the16-byte primary key, the11-byte
alternate key's value/ordinal, the input database, or the receiving copybook.

The runtime argument is bound to `libcob4t64=3.1.2-5.1ubuntu1`:

- Package SHA-256: `664d91e5d7b6219126e6255d7d1f99a9d232206d027005ecf5719dca3674923f`.
- Installed `libcob.so.4.1.0`: `67070497d8fb7b0ff564b16b84bf906e5c5940492ad4f1c36615c708ec588429`.
- Official original source archive: `597005d71fd7d65b90cbe42bbfecd5a9ec0445388639404662e70d53ddf22574`.
- `libcob/fileio.c`: `a569a8e0a5844f382d4d816d10100c2c34ad013052cd0424abe06ddbcdf7c041`.
- Debian patch archive: `26060e527863db151c1440026744e7cb86c33b99aeb657d0da72258a1312e9a5`; its three patches do not modify `fileio.c`.

The package and source checksums were verified against the [immutable Ubuntu
source record](https://snapshot.ubuntu.com/ubuntu/20240501T000000Z/pool/universe/g/gnucobol3/gnucobol3_3.1.2-5.1ubuntu1.dsc).
The verified runtime binary links Berkeley DB (`libdb-5.3.so`). The campaign
rechecks the installed library hash; this argument is disabled on any mismatch.

For the verified `WITH_DB` implementation:

1. `bdb_findkey`, lines681–714, matches the requested field pointer to the
   current compiled key descriptors and returns its ordinal. Both programs
   request alternate key1 of length11. A shifted field pointer does not change
   that ordinal or length.
2. `bdb_setkey`/`bdb_savekey`, lines739–767, copy the unchanged requested account
   value from that descriptor into the key buffer. `indexed_start_internal`,
   lines3057–3084, searches the existing key1 database and compares the returned
   key to the same requested value, before replacing the FD record buffer.
3. `indexed_read`, lines4233–4245, accepts the stored50-byte record for both
   maxima50 and51 and copies the same50 bytes. The original source's `READ INTO`
   uses the unchanged50-byte XREF receiving copybook; only its16-byte card
   prefix is subsequently consumed. The shifted FD customer/account fields
   are not read after successful delivery or written back.
4. Missing-key diagnostics use the unchanged11-byte requested account value.
   Declared fault seams replace operation status directly and cannot expose
   the unused extra FD byte.

This argument covers the twin's declared fixed50-byte loader inputs, this
read-only XREF access, and declared engineering fault seams. It does not cover
malformed databases, another backend/runtime, different key lengths, an FD
write, or native z/OS behavior. All other FD layout mutations require their own
witness or argument. The compiled campaign still executes this mutant and only
lists the argument after actual survival.
