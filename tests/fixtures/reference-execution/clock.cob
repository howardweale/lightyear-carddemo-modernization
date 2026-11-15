identification division.
program-id. probe.
data division.
working-storage section.
01 now-value pic x(21).
01 fraction pic x(6).
procedure division.
 move function current-date to now-value
 if now-value(1:16) not = '2026111412345678' stop run returning 11 end-if
 move now-value(15:2) to fraction(1:2)
 move '0000' to fraction(3:4)
 if fraction not = '780000' stop run returning 12 end-if
 stop run returning 0.
