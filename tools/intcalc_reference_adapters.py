"""Exact public adapter definitions retained from legacy_twin at 390230d5."""
FILES = {
    "INTCALC": {"ACCTFILE": (300, 11), "TCATBALF": (50, 17),
                "DISCGRP": (50, 16), "XREFFILE": (50, 16), "TRANSACT": (350, 0)},
    "POSTTRAN": {"ACCTFILE": (300, 11), "TCATBALF": (50, 17),
                 "XREFFILE": (50, 16), "TRANFILE": (350, 16),
                 "DALYTRAN": (350, 0), "DALYREJS": (430, 0)},
}


def indexed_adapter(job, dd):
    length, key = FILES[job][dd]
    if not key:
        raise ValueError("sequential files do not need indexed adaptation")
    alternate = job == "INTCALC" and dd == "XREFFILE"
    tail = ("05 filler pic x(9).\n05 alt-key pic x(11).\n05 filler pic x(14)." if alternate
            else f"05 filler pic x({length-key}).")
    alt_clause = "alternate record key is alt-key" if alternate else ""
    return f"""identification division.
program-id. adapter.
environment division.
input-output section.
file-control.
select flat-file assign to dynamic flat-path
 organization sequential file status flat-status.
select index-file assign to dynamic index-path
 organization indexed access dynamic record key primary-key
 {alt_clause} file status index-status.
data division.
file section.
fd flat-file.
01 flat-record pic x({length}).
fd index-file.
01 index-record.
05 primary-key pic x({key}).
{tail}
working-storage section.
01 flat-path pic x(1024).
01 index-path pic x(1024).
01 operation pic x(8).
01 flat-status pic xx.
01 index-status pic xx.
01 finished pic 9 value 0.
procedure division.
 accept operation from argument-value
 accept flat-path from argument-value
 accept index-path from argument-value
 evaluate operation
 when 'load'
   open input flat-file
   perform check-flat
   open output index-file
   perform check-index
   perform until finished = 1
     read flat-file
     evaluate flat-status
     when '10' move 1 to finished
     when '00'
       move flat-record to index-record
       write index-record
       perform check-index
     when other perform check-flat
     end-evaluate
   end-perform
 when 'dump'
   open input index-file
   perform check-index
   open output flat-file
   perform check-flat
   perform until finished = 1
     read index-file next record
     evaluate index-status
     when '10' move 1 to finished
     when '00'
       move index-record to flat-record
       write flat-record
       perform check-flat
     when other perform check-index
     end-evaluate
   end-perform
 when other stop run returning 64
 end-evaluate
 close flat-file
 perform check-flat
 close index-file
 perform check-index
 stop run returning 0.
check-flat.
 if flat-status not = '00'
   display 'FLAT-STATUS=' flat-status upon syserr
   stop run returning 65
 end-if.
check-index.
 if index-status not = '00'
   display 'INDEX-STATUS=' index-status upon syserr
   stop run returning 66
 end-if.
"""


ABEND = """identification division.
program-id. CEE3ABD.
data division.
linkage section.
01 abcode pic s9(9) binary.
01 timing pic s9(9) binary.
procedure division using abcode timing.
 stop run returning 12.
"""


def wrapper(job):
    if job == "POSTTRAN":
        return """identification division.
program-id. twinmain.
procedure division.
 call 'CBTRN02C'
 stop run returning return-code.
"""
    return """identification division.
program-id. twinmain.
data division.
working-storage section.
01 external-parms.
 05 parm-length pic s9(04) comp value 10.
 05 parm-date pic x(10).
procedure division.
 accept parm-date from environment 'TWIN_PROCESSING_DATE'
 call 'CBACT04C' using external-parms
 stop run returning return-code.
"""
