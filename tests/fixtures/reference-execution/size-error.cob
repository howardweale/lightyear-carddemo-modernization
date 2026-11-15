identification division.
program-id. probe.
data division.
working-storage section.
01 a pic 9(3) value 777.
01 caught pic 9 value 0.
procedure division.
 compute a = 1234 on size error move 1 to caught end-compute
 if caught not = 1 or a not = 777 stop run returning 11 end-if
 stop run returning 0.
