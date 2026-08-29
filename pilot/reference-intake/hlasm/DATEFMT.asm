DATEFMT  CSECT
         USING DATEFMT,15
START    L     2,0(1)
         LTR   2,2
         BZ    EMPTY
         LA    15,0
         B     RETURN
EMPTY    LA    15,8
RETURN   BR    14
DATEDS   DSECT
DATEIN   DS    CL8
         END   DATEFMT
