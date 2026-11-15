identification division.
program-id. probe.
data division.
working-storage section.
01 item-value pic s9(3) comp-3.
01 bytes-value redefines item-value pic xx.
01 target pic s9(3).
procedure division.
 move x'123C' to bytes-value
 move item-value to target
 if target not = 123 stop run returning 11 end-if
 move x'123D' to bytes-value
 move item-value to target
 if target not = -123 stop run returning 12 end-if
 move x'123F' to bytes-value
 move item-value to target
 if target not = 123 stop run returning 13 end-if
 stop run returning 0.
