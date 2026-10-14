# Evidence gaps and targeted timestamp repair — October 12

On exact head `2dd787642e66176f78dbf749ec2659e82672cd3e`, run `38198096890`, INTCALC's 113 final evidence-gap dispositions are formerly argued equivalents affected by an incomplete fresh comparison: the baseline loader rejects the deliberately duplicate indexed TCATBALF key in `intcalc-duplicate-category` with rc=66, before program execution. There are 167 mutant records with any gap, including mutants killed by another completed comparison; 113 is the final-disposition count, not a compiler-failure count or 113 refuted arguments. Separate compiler/class/individual proof labels therefore overlap those gaps and do not clear them. POSTTRAN's **1** is an incomplete targeted argument (`CBTRN02C-receiving-scale-173-20`), whereas its **9** are fresh execution-refusal dispositions formerly miscredited as kills (including dump-TCATBALF refusals); they are different sets and phases. The corrected fresh raw POSTTRAN count remains 360/483; INTCALC remains 308/421. Refusals are excluded from authenticated kills, and incomplete comparisons continue to block threshold approval.

## Three incomplete targeted runs

| Program | Mutant | Valid/scheduled | Refused pairs |
|---|---|---:|---:|
| INTCALC | CBACT04C-receiving-scale-164-26 | 2/200 | 198 |
| INTCALC | CBACT04C-receiving-scale-173-34 | 2/200 | 198 |
| POSTTRAN | CBTRN02C-receiving-scale-173-20 | 2/200 | 198 |

The timestamp profile generated fractional seconds `(index % 100)`, while `legacy_twin.runtime_clock` deliberately admits only `.000000`. Only indices 0 and 100 met that contract. Both sides refused the other cases before execution. The branch repair varies day/hour/minute while retaining whole-second precision; it does not broaden the runtime contract, alter the mutant, reinterpret a refusal, or resume old evidence. Offline tests check clock admission for all 400 generated cases across both programs and preserve rejection of fractional input. Only fresh GitHub compiled results can confirm the three completed comparison sets.

The INTCALC duplicate-category baseline gap is separately explained, not silently removed or declared equivalent. A repeated primary key is outside the indexed adapter's admitted input domain. The old raw campaign and the nine POSTTRAN refusal corrections remain unchanged. Any future domain exclusion requires an explicit scoped decision and fresh receipts.
