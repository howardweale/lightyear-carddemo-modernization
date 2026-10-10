identification division.
program-id. platformprobe.
environment division.
input-output section.
file-control.
select packed-file assign to 'packed.bin' organization sequential.
select indexed-file assign to 'probe.idx' organization indexed
 access dynamic record key item-key file status fs.
data division.
file section.
fd packed-file.
01 packed-record.
 05 positive-number pic s9(5)v99 comp-3.
 05 negative-number pic s9(5)v99 comp-3.
fd indexed-file.
01 item-record.
 05 item-key pic x(2).
 05 item-value pic x(4).
working-storage section.
01 fs pic xx.
01 rounded-number pic s9(3)v99.
01 truncated-number pic s9(3)v99.
01 edited-number pic +999.99.
01 narrow-number pic 99.
01 signed-display pic s9(5)v99.
01 signed-bytes redefines signed-display pic x(7).
01 current-stamp pic x(21).
01 calendar-date pic 9(8).
procedure division.
 open output packed-file
 move 123.45 to positive-number
 move -123.45 to negative-number
 write packed-record
 close packed-file
 move -123.45 to signed-display
 display 'SIGNED-DISPLAY=' signed-display
 display 'SIGNED-STORAGE=' signed-bytes
 compute rounded-number rounded = -1.235
 move rounded-number to edited-number
 display 'ROUNDED=' edited-number
 compute truncated-number = -1.235
 move truncated-number to edited-number
 display 'TRUNCATED=' edited-number
 move 123 to narrow-number
 display 'SIZE-TRUNCATION=' narrow-number
 if 'a' < 'A' display 'COLLATION=a-before-A'
 else display 'COLLATION=A-before-a' end-if
 move function date-of-integer(function integer-of-date(20240229))
 to calendar-date
 display 'LEAP-DATE=' calendar-date
 move function current-date to current-stamp
 display 'CLOCK=' current-stamp(1:16)
 open input indexed-file
 display 'MISSING-FILE=' fs
 open output indexed-file
 if fs not = '00' stop run returning 65 end-if
 move '01' to item-key
 move 'data' to item-value
 write item-record
 if fs not = '00' stop run returning 65 end-if
 write item-record
 display 'DUPLICATE-KEY=' fs
 close indexed-file
 open input indexed-file
 if fs not = '00' stop run returning 65 end-if
 move '99' to item-key
 read indexed-file key item-key
 display 'MISSING-KEY=' fs
 move '01' to item-key
 read indexed-file key item-key
 if fs not = '00' stop run returning 65 end-if
 read indexed-file next record
 display 'EOF=' fs
 close indexed-file
 stop run returning 0.
