# Native datatype mapping review

Common base-table columns: **18,852**. This inventory does not prove datatype behavior.

| Oracle to PostgreSQL mapping | Columns |
|---|---:|
| BLOB -> bytea | 12 |
| BLOB -> oid | 3 |
| CHAR -> character | 3,039 |
| CHAR -> character varying | 1 |
| CLOB -> json | 2 |
| CLOB -> jsonb | 1 |
| CLOB -> text | 29 |
| DATE -> timestamp without time zone | 2,259 |
| NUMBER -> numeric | 9,393 |
| TIMESTAMP(6) WITH TIME ZONE -> timestamp with time zone | 3 |
| VARCHAR2 -> character varying | 3,196 |
| VARCHAR2 -> uuid | 914 |

## Required behavioral checks

| Check | Columns requiring review |
|---|---:|
| actual-column-json-constraints | 3 |
| application-currency-price-and-tax-rounding | 9,393 |
| application-time-normalization | 2,259 |
| binary-byte-round-trip | 15 |
| collation-and-comparison | 6,236 |
| date-range | 2,262 |
| duplicate-json-keys | 3 |
| empty-binary-versus-null | 15 |
| empty-lob-versus-null | 29 |
| empty-string-and-null | 7,150 |
| fixed-versus-varying-text | 1 |
| fixed-width-padding-and-trailing-spaces | 3,040 |
| fractional-second-write-and-readback | 2,262 |
| invalid-json-rejection | 3 |
| invalid-uuid-rejection | 914 |
| json-null-versus-sql-null | 3 |
| json-number-precision | 3 |
| json-text-rendering | 3 |
| large-object-dereference | 3 |
| large-object-ownership-and-lifecycle | 3 |
| large-unicode-round-trip | 29 |
| large-value-capacity | 44 |
| length-boundary | 6,236 |
| multibyte-byte-capacity | 3,035 |
| nonfinite-input-rejection | 9,393 |
| overflow-rejection | 9,393 |
| positive-and-negative-rounding-ties | 9,393 |
| significant-digit-and-exponent-boundaries | 1,023 |
| timezone-offset-and-instant | 3 |
| unicode-round-trip | 6,236 |
| uuid-case-rendering | 914 |
| valid-uuid-round-trip | 914 |

Counts overlap: a column can require several checks. Matching declared
length or precision does not prove identical accepted inputs, rounding,
collation, table constraints or application behavior. Missing metadata is
retained as null. Every native declaration and one-sided column is retained
in the JSON report. Full schema and platform qualification remain false.
