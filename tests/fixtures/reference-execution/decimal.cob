identification division.
program-id. probe.
data division.
working-storage section.
01 a pic s9(3)v99.
01 b pic s9(3)v99.
01 high-part pic 9(3).
procedure division.
 compute a = 250.75 * 21 / 1200
 if a not = 4.38 stop run returning 11 end-if
 compute b rounded = 250.75 * 21 / 1200
 if b not = 4.39 stop run returning 12 end-if
 compute a = -250.75 * 21 / 1200
 if a not = -4.38 stop run returning 13 end-if
 compute high-part = 1234
 if high-part not = 234 stop run returning 14 end-if
 stop run returning 0.
