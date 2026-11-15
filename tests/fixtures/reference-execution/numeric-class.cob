identification division.
program-id. probe.
data division.
working-storage section.
01 item-value pic s9(3) comp-3.
01 bytes-value redefines item-value pic xx.
procedure division.
 move x'123C' to bytes-value
 if item-value is not numeric stop run returning 11 end-if
 move x'123D' to bytes-value
 if item-value is not numeric stop run returning 12 end-if
 move x'12AC' to bytes-value
 if item-value is numeric stop run returning 13 end-if
 stop run returning 0.
