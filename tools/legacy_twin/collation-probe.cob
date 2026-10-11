identification division.
program-id. collatingprobe.
environment division.
configuration section.
object-computer. x86.
input-output section.
file-control.
select source-file assign to 'sort-input.bin' organization sequential.
select sorted-file assign to 'sorted.bin' organization sequential.
select left-file assign to 'left.bin' organization sequential.
select right-file assign to 'right.bin' organization sequential.
select merged-file assign to 'merged.bin' organization sequential.
select work-file assign to 'work.tmp'.
select index-file assign to 'collation.idx' organization indexed
 access dynamic record key index-key file status fs.
data division.
file section.
fd source-file.
01 source-key pic x.
fd sorted-file.
01 sorted-key pic x.
fd left-file.
01 left-key pic x.
fd right-file.
01 right-key pic x.
fd merged-file.
01 merged-key pic x.
sd work-file.
01 work-key pic x.
fd index-file.
01 index-key pic x.
working-storage section.
01 fs pic xx.
01 first-character pic x.
01 second-character pic x.
procedure division.
 if 'a' < 'A' display 'LITERAL=a-before-A'
 else display 'LITERAL=A-before-a' end-if
 accept first-character from environment 'PROBE_LEFT'
 accept second-character from environment 'PROBE_RIGHT'
 if first-character < second-character display 'DATA=a-before-A'
 else display 'DATA=A-before-a' end-if
 open output source-file
 move 'a' to source-key write source-key
 move '0' to source-key write source-key
 move 'A' to source-key write source-key
 close source-file
 sort work-file on ascending key work-key using source-file giving sorted-file
 open output left-file right-file
 move 'A' to left-key write left-key
 move 'a' to right-key write right-key
 close left-file right-file
 merge work-file on ascending key work-key using left-file right-file giving merged-file
 open output index-file
 move 'a' to index-key write index-key
 move '0' to index-key write index-key
 move 'A' to index-key write index-key
 close index-file
 open input index-file
 perform 3 times
   read index-file next record
   if fs not = '00' stop run returning 65 end-if
   display 'INDEX=' index-key
 end-perform
 close index-file
 stop run returning 0.
