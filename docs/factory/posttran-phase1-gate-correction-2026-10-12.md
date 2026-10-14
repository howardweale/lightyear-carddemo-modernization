# POSTTRAN Phase1 gate correction and authorized rerun — October12

Howard requested “fix and rerun 328, 330, 331”. Generation attempt1 and its candidate bytes remain unchanged (SHA256 `1b501ff62f1578064d6867c18ad1a0a412d8d7c6e91bb82c91d52bb538134186`). Original run38295068434 and its failed report remain unchanged.

Source inspection found a harness-contract mismatch: pinned CBTRN02C lines709–711 moves0 to TIMING, moves999 to ABCODE, then calls CEE3ABD. The candidate preserves the full999 in RETURN-CODE and uses process exit231 on Linux (999 modulo256). The legacy twin's explicitly documented CEE3ABD adapter instead returns process12. The prior Phase1 harness passed the candidate's source-code value into the default twin-process check, incorrectly requiring12.

The corrected gate selects the explicit `source-abcode` contract, strictly requiring999 for the duplicate-write abend; the existing `twin-process` contract still strictly requires12. There is no accept-either-code rule. All structural, partial-update, prefix, balance, rejection, process/file agreement and repeatability checks remain. This is a source-bound harness correction, not a candidate repair or a z/OS result. No native/twin comparison was performed. Original failed evidence is retained, not relabelled successful.

[Authorization](posttran-phase1-rerun-authorization-2026-10-12.json) permits compilation ordinal2 only on the first GitHub PR workflow attempt at an exact child of5b23bc28 with pinned candidate/gate/invariant/source bytes. Automatic job retries, later unrelated heads and local execution are refused. No model calls or Phase2 authority. All merges remain held until B06 cleanup is sealed.

The graph-memory UI now waits for both responses before one atomic render and discards superseded loads. The browser test forces overlapping responses and requires one unique checkbox; it does not hide duplicate elements with a first-match selector. Seven focused offline gate tests passed; browser and actual compilation run on GitHub CI.
