identification division.
program-id. probe.
data division.
working-storage section.
01 zoned-value pic s9(3) display.
01 raw-value redefines zoned-value pic x(3).
01 zero-item pic s9(3) value 0.
01 one-item pic s9(3) value 1.
procedure division.
 move "12C" to raw-value
 add zero-item to zoned-value
 display raw-value
 move "12L" to raw-value
 add zero-item to zoned-value
 display raw-value
 move "123" to raw-value
 add zero-item to zoned-value
 display raw-value
 move "123" to raw-value
 add one-item to zoned-value
 display raw-value
 move 0 to zoned-value
 display raw-value
 move -5 to zoned-value
 display raw-value
 stop run returning 0.
