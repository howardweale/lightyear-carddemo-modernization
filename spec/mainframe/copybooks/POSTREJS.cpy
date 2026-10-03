      * Derived from CVTRA06Y and CBTRN02C WS-VALIDATION-TRAILER.
       01  REJECT-RECORD.
           05 DALYTRAN-RECORD.                                             
           10  DALYTRAN-ID                             PIC X(16).       
           10  DALYTRAN-TYPE-CD                        PIC X(02).       
           10  DALYTRAN-CAT-CD                         PIC 9(04).       
           10  DALYTRAN-SOURCE                         PIC X(10).       
           10  DALYTRAN-DESC                           PIC X(100).      
           10  DALYTRAN-AMT                            PIC S9(09)V99.   
           10  DALYTRAN-MERCHANT-ID                    PIC 9(09).       
           10  DALYTRAN-MERCHANT-NAME                  PIC X(50).       
           10  DALYTRAN-MERCHANT-CITY                  PIC X(50).       
           10  DALYTRAN-MERCHANT-ZIP                   PIC X(10).       
           10  DALYTRAN-CARD-NUM                       PIC X(16).       
           10  DALYTRAN-ORIG-TS                        PIC X(26).       
           10  DALYTRAN-PROC-TS                        PIC X(26).       
           10  FILLER                                  PIC X(20).       
        05 WS-VALIDATION-TRAILER.
           10 WS-VALIDATION-FAIL-REASON      PIC 9(04).
           10 WS-VALIDATION-FAIL-REASON-DESC PIC X(76).
