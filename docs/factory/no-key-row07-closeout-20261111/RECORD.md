# P5 row 07 closeout — 11 November 2026, revision 2

## Effect and authority

Effective when this exact record enters main following Howard's exact merge approval: row 07 is CLOSED for the fixed cooperative NO-KEY rehearsal only. Until that merge, repository closure remains pending. This condition is not satisfied by a Release upload or local evidence disposition.

No existing repository row-status authority was found in the pinned main P5 documentation or status-generator inputs. This record is the proposed authoritative repository record for row 07. It does not update generated current-status files or close any other production row. A future reader must establish the main merge and its approval, not assume adoption from these files in a proposal tree.

## Evidence and limits

The evidence is split: S1-S5 come from session2b, scheduled 14:30 PT, packet no-key-session2b-1430-proposal-20261111-r6. S6 comes from session3-s6, scheduled 16:15 PT, packet no-key-s6-only-1615-proposal-20261111-r1. The operator did not press Control-C in session2b S6; its deadline result is retained and superseded for closure by the attended cancellation repeat.

S6 has FAIL / operator-cancelled / REAPED, expected exit 2, six events, cancellation about 2.759 seconds after READY and result before the original deadline. The original journal digest is fc5c63d3b9a7512432cc35b18418b96da593ffdd273ef121cfe41b6a04b5c8ec. All 33 file digests and seven journal chains match the index; chain edges use SHA256(previous raw line + LF), beginning with 64 zeroes. Full comparisons and original timing values are in AUDIT-AND-HISTORY.json.

Limits, verbatim:
- fixed-cooperative-rehearsal-only
- native_proof false
- journals unauthenticated
- hardware_checked false
- live_processes_checked false

This establishes neither hostile descendant containment nor native owner/guardian qualification, production transfer readiness, signer authority or admission. Transfer/re-binding logistics still need hardening. Bound values expire 12 November 11:01:21 PT and are not reusable. No production row or STOP rule changes.

## Four session-specific accepted departures [decision receipt](decision-receipt.json#sha256=d2876cfd7e324bdc02ef78b6f1e0760fe352e4044c5737b14acf99b577d9f6a7)

Howard approved each departure only for its own completed session [decision receipt](decision-receipt.json#sha256=d2876cfd7e324bdc02ef78b6f1e0760fe352e4044c5737b14acf99b577d9f6a7); none is reusable. [decision receipt](decision-receipt.json#sha256=d2876cfd7e324bdc02ef78b6f1e0760fe352e4044c5737b14acf99b577d9f6a7)

| Departure | Session / original observation | Approver | Confirmation time |
|---|---|---|---|
| Section A: existing hash-matched addendum file on USB | session1, 10 November; 2026-11-10T15:36:00-08:00 | Howard | 11 November 2026 17:38 PT |
| Single Control-C to park the incomplete session1 Terminal input | session1, 10 November; 2026-11-10T16:22:00-08:00 | Howard | 11 November 2026 17:38 PT |
| Unchanged r6 script re-pasted after incomplete paste discarded before writes | session2b, 11 November; Windows preparation complete at 13:55 PT; exact first-paste time not recorded | Howard | 11 November 2026 17:38 PT |
| Mac entry attempted before Windows preparation, then repeated in same bash window | session3-s6, 11 November; Exact entry-attempt time not recorded | Howard | 11 November 2026 17:38 PT |

## Complete history

Session1: NOT TESTED; S1-S6 NOT ATTEMPTED. Section A pre-existing exact file departure. Mac was zsh, with incomplete parenthesis input buffered. Stop at 16:06 PT on 10 November; one Control-C at 16:22 returned primary prompt with no execution output, per operator.

11 November 10:45 slot: abandoned before any step, no USB session2 write or Mac command, per operator.

Session2 r5 at 13:00: archive write stalled; PC force-restarted. Original USB session2 folder retained with 67 entries and 245760-byte truncated payload. No removal or reuse.

Operator-only write-test.tar, 32706560 bytes, outside the packet. Reported readback is a diagnostic observation, not native qualification or a general health guarantee.

Session2b r6 at 14:30: first Windows paste left continuation prompt, discarded with Control-C while destination absent, unchanged script re-pasted. Preparation complete at 13:55 PT. Steps reached expected exits; S1-S5 supply closure evidence. S6 lacked operator Control-C and reached the original deadline; retained, not repeated within session2b.

Session3-s6 at 16:15: first Mac entry hash read failed because Windows preparation had not occurred. Operator reported no session path or writes. Preparation followed, then the same bash window entry. Separate attended S6 supplies operator cancellation evidence; no inference of future recovery permission.

## Six observations

1. Folder A is named 1300pt-session2 but its journals are timed 22:43-22:46 UTC (14:43-14:46 PT) and it was produced by packet r6 (Windows folder no-key-session2b). The 1300pt-session2 return folder is the output of the 14:30 PT r6 packet.

2. Folder A executable paths use the Mac directory lightyear-no-key-8fe41d76-session2 (as written in the r6 command sheet).

3. Folder A S6 is FAIL / original-deadline-reached: the operator did not press Ctrl-C. It does not meet the required S6 result and is superseded by folder B; the original file remains retained in folder A and in the hash inventory.

4. S5 and folder A S6: the result event lands about 14 ms after the original deadline and about 4.99 s inside the cleanup deadline, which is the designed behaviour for original-deadline-reached.

5. Mac data volume shows 99% capacity (about 3.0-3.2 GB free) in both r3-paths.txt files.

6. r4-n2, r4-n3 and r4-n4 are byte-identical (same refusal JSON); r4-p1 and r4-n1 are byte-identical. Expected from the command sheet, noted so identical hashes are not mistaken for a copy error.

Status JSON does not carry every limit flag; metadata/result/runtime records supply the other fields. This does not change the stated limits.

## Retention

This record, RETURN-FILE-HASHES.json and AUDIT-AND-HISTORY.json are in-tree evidence. Release copies are secondary. Raw returns are retained by the operator; their file hashes are fixed in-tree. No old session files or evidence are removed.
