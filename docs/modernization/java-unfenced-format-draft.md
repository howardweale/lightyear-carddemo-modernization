# K1 unfenced Java formatting — first batch

Nine unfenced account rule/state classes receive formatting in a separate,
format-only commit. The original 33-file CI patch is larger than the review
limit; the other 24 files remain explicitly deferred in the scope record.
The two adapters with exact source-hash consumers are among the deferred files.
No fenced file or independent oracle changes.

Source artifact: [run 40103847871](https://github.com/howardweale/lightyear-carddemo-modernization/actions/runs/40103847871),
artifact 12564440005. The exact ZIP, patch and all nine before/after hashes were
reviewed. The Java body tokens, literals, comments and import sets are identical;
AccountSsnRule imports are reordered. Spotless 2.43.0 uses Google import order
even with reorderImports=false. Long-string and Javadoc reflow remain disabled.
The scope update binds the formatted parent commit and each exact new source
hash; capture never silently accepts another version.

Required CI runs the synthetic scope/refusal tests, formatter apply/check, and
refuses any remaining formatter change. The existing full proof, whole-storage
parity and per-class mutation gates must pass on the final head before review.
A successful patch producer alone is insufficient. No threshold changes or
new mutation credit are claimed. Local work is static metadata review and lint.

Idiomatic-index change: zero. Paragraph classifications, mutation thresholds
and engine counts are unchanged. Checkstyle, Error Prone and SpotBugs remain
subsequent K1 work; this is not completion of K1. Held fenced formatting remains
in #451. Ten-minute checks remain off. No signing, factory execution, model
calls, Tower access or spending authority. Exact-head approval is still needed.
