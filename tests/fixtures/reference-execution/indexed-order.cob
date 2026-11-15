identification division.
program-id. probe.
environment division.
input-output section.
file-control.
 select rows assign 'index-probe'
 organization indexed access dynamic record key row-key file status status-code.
data division.
file section.
fd rows.
01 row-data.
 05 row-key pic xx.
 05 row-value pic xx.
working-storage section.
01 status-code pic xx.
procedure division.
 open output rows
 if status-code not = '00' stop run returning 10 end-if
 move '03cc' to row-data write row-data
 if status-code not = '00' stop run returning 11 end-if
 move '01aa' to row-data write row-data
 if status-code not = '00' stop run returning 12 end-if
 move '02bb' to row-data write row-data
 if status-code not = '00' stop run returning 13 end-if
 close rows
 open input rows
 read rows next record
 if status-code not = '00' or row-key not = '01' stop run returning 14 end-if
 read rows next record
 if status-code not = '00' or row-key not = '02' stop run returning 15 end-if
 read rows next record
 if status-code not = '00' or row-key not = '03' stop run returning 16 end-if
 read rows next record
 if status-code not = '10' stop run returning 17 end-if
 close rows
 stop run returning 0.
