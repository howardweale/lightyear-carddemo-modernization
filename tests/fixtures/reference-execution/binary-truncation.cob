identification division.
program-id. probe.
data division.
working-storage section.
01 a pic 9(4) comp.
01 b pic 9(4).
procedure division.
 move 12345 to a
 move a to b
 if b not = 2345 stop run returning 11 end-if
 stop run returning 0.
