identification division.
program-id. probe.
data division.
working-storage section.
01 zoned-value pic s9(3) display.
01 raw-value redefines zoned-value pic x(3).
procedure division.
 move "12C" to raw-value
 if zoned-value not = 123 stop run returning 11 end-if
 add 0 to zoned-value
 if raw-value not = "12C" stop run returning 12 end-if
 move "12L" to raw-value
 if zoned-value not = -123 stop run returning 13 end-if
 add 0 to zoned-value
 if raw-value not = "12L" stop run returning 14 end-if
 move "123" to raw-value
 if zoned-value not = 123 stop run returning 15 end-if
 add 0 to zoned-value
 if raw-value not = "12C" stop run returning 16 end-if
 move 0 to zoned-value
 if raw-value not = "00{" stop run returning 17 end-if
 move -5 to zoned-value
 if raw-value not = "00N" stop run returning 18 end-if
 stop run returning 0.
