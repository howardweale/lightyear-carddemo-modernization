# POSTTRAN: APPL-RESULT class signing packet

96 exact members; 30-member deterministic audit. Twin scope only.

Source SHA-256: `708f3cadc555acab63f11e2f3238f5372ac7180e6b01197bf960d96bf0d2e83f`
Matcher SHA-256: `0ba15b8cec35656269fb3f26c92ce7b3f2075c325e28089c953fab12133a3825`
Class proof: `13aca947966f508c373d9a1269e4729b744549c6e1fbb32f205a6543dd38a242`

The census and full membership are in the companion JSON. Signing is an operator review, not independent attestation. No signature has been applied.

## 1. CBTRN02C-constant-638-377

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 638:            MOVE 8 TO APPL-RESULT.                                               
 639:            CLOSE DALYREJS-FILE                                                  
 640:            IF  DALYREJS-STATUS = '00'                                           
 641:                MOVE 0 TO APPL-RESULT                                            
 642:            ELSE                                                                 
 643:                MOVE 12 TO APPL-RESULT                                           
 644:            END-IF                                                               
 645:            IF  APPL-AOK                                                         
```

## 2. CBTRN02C-constant-242-79

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 3. CBTRN02C-constant-533-297

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 4. CBTRN02C-delete-MOVE-569-326

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

```cobol
 563:            MOVE 8 TO  APPL-RESULT.                                              
 564:            WRITE FD-TRANFILE-REC FROM TRAN-RECORD                               
 565:                                                                                 
 566:            IF  TRANFILE-STATUS = '00'                                           
 567:                MOVE 0 TO  APPL-RESULT                                           
 568:            ELSE                                                                 
 569:                MOVE 12 TO APPL-RESULT                                           
```

## 5. CBTRN02C-constant-292-117

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 292:            MOVE 8 TO APPL-RESULT.                                               
 293:            OPEN OUTPUT DALYREJS-FILE                                            
 294:            IF  DALYREJS-STATUS = '00'                                           
 295:                MOVE 0 TO APPL-RESULT                                            
 296:            ELSE                                                                 
 297:                MOVE 12 TO APPL-RESULT                                           
 298:            END-IF                                                               
 299:            IF  APPL-AOK                                                         
```

## 6. CBTRN02C-constant-260-94

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 7. CBTRN02C-constant-680-414

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 8. CBTRN02C-constant-354-171

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 9. CBTRN02C-delete-MOVE-531-295

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

```cobol
 195:            PERFORM 0000-DALYTRAN-OPEN.                                          
 200:            PERFORM 0500-TCATBALF-OPEN.                                          
 202:            PERFORM UNTIL END-OF-FILE = 'Y'                                      
 204:                    PERFORM 1000-DALYTRAN-GET-NEXT                               
 205:                    IF  END-OF-FILE = 'N'                                        
 208:                      MOVE 0 TO WS-VALIDATION-FAIL-REASON                        
 210:                      PERFORM 1500-VALIDATE-TRAN                                 
 213:                      ELSE                                                       
 216:                      END-IF                                                     
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 362:                ELSE                                                             
 370:        1500-VALIDATE-TRAN.                                                      
 382:            MOVE DALYTRAN-CARD-NUM TO FD-XREF-CARD-NUM                           
 395:            READ ACCOUNT-FILE INTO ACCOUNT-RECORD                                
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 495:            IF WS-CREATE-TRANCAT-REC = 'Y'                                       
 496:               PERFORM 2700-A-CREATE-TCATBAL-REC                                 
 498:               PERFORM 2700-B-UPDATE-TCATBAL-REC                                 
 513:                MOVE 0 TO APPL-RESULT                                            
 531:                MOVE 0 TO APPL-RESULT                                            
 563:            MOVE 8 TO  APPL-RESULT.                                              
 566:            IF  TRANFILE-STATUS = '00'                                           
```

## 10. CBTRN02C-constant-680-415

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 11. CBTRN02C-constant-328-146

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 328:            MOVE 8 TO APPL-RESULT.                                               
 329:            OPEN I-O  TCATBAL-FILE                                               
 330:            IF  TCATBALF-STATUS = '00'                                           
 331:                MOVE 0 TO APPL-RESULT                                            
 332:            ELSE                                                                 
 333:                MOVE 12 TO APPL-RESULT                                           
 334:            END-IF                                                               
 335:            IF  APPL-AOK                                                         
```

## 12. CBTRN02C-delete-MOVE-348-165

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

```cobol
 195:            PERFORM 0000-DALYTRAN-OPEN.                                          
 200:            PERFORM 0500-TCATBALF-OPEN.                                          
 202:            PERFORM UNTIL END-OF-FILE = 'Y'                                      
 204:                    PERFORM 1000-DALYTRAN-GET-NEXT                               
 205:                    IF  END-OF-FILE = 'N'                                        
 208:                      MOVE 0 TO WS-VALIDATION-FAIL-REASON                        
 210:                      PERFORM 1500-VALIDATE-TRAN                                 
 213:                      ELSE                                                       
 216:                      END-IF                                                     
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 362:                ELSE                                                             
 370:        1500-VALIDATE-TRAN.                                                      
 382:            MOVE DALYTRAN-CARD-NUM TO FD-XREF-CARD-NUM                           
 395:            READ ACCOUNT-FILE INTO ACCOUNT-RECORD                                
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 495:            IF WS-CREATE-TRANCAT-REC = 'Y'                                       
 496:               PERFORM 2700-A-CREATE-TCATBAL-REC                                 
 498:               PERFORM 2700-B-UPDATE-TCATBAL-REC                                 
 513:                MOVE 0 TO APPL-RESULT                                            
 531:                MOVE 0 TO APPL-RESULT                                            
 563:            MOVE 8 TO  APPL-RESULT.                                              
 566:            IF  TRANFILE-STATUS = '00'                                           
```

## 13. CBTRN02C-constant-310-132

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 310:            MOVE 8 TO APPL-RESULT.                                               
 311:            OPEN I-O  ACCOUNT-FILE                                               
 312:            IF  ACCTFILE-STATUS = '00'                                           
 313:                MOVE 0 TO APPL-RESULT                                            
 314:            ELSE                                                                 
 315:                MOVE 12 TO APPL-RESULT                                           
 316:            END-IF                                                               
 317:            IF  APPL-AOK                                                         
```

## 14. CBTRN02C-constant-569-325

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 15. CBTRN02C-constant-638-376

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 638:            MOVE 8 TO APPL-RESULT.                                               
 639:            CLOSE DALYREJS-FILE                                                  
 640:            IF  DALYREJS-STATUS = '00'                                           
 641:                MOVE 0 TO APPL-RESULT                                            
 642:            ELSE                                                                 
 643:                MOVE 12 TO APPL-RESULT                                           
 644:            END-IF                                                               
 645:            IF  APPL-AOK                                                         
```

## 16. CBTRN02C-constant-569-324

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 17. CBTRN02C-constant-450-235

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 450:            MOVE 8 TO APPL-RESULT                                                
 451:            WRITE FD-REJS-RECORD FROM REJECT-RECORD                              
 452:            IF DALYREJS-STATUS = '00'                                            
 453:                MOVE 0 TO  APPL-RESULT                                           
 454:            ELSE                                                                 
 455:                MOVE 12 TO APPL-RESULT                                           
 456:            END-IF                                                               
 457:            IF  APPL-AOK                                                         
```

## 18. CBTRN02C-delete-MOVE-656-393

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 656:            MOVE 8 TO APPL-RESULT.                                               
 657:            CLOSE ACCOUNT-FILE                                                   
 658:            IF  ACCTFILE-STATUS  = '00'                                          
 659:                MOVE 0 TO APPL-RESULT                                            
 660:            ELSE                                                                 
 661:                MOVE 12 TO APPL-RESULT                                           
 662:            END-IF                                                               
 663:            IF  APPL-AOK                                                         
```

## 19. CBTRN02C-delete-MOVE-292-118

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 292:            MOVE 8 TO APPL-RESULT.                                               
 293:            OPEN OUTPUT DALYREJS-FILE                                            
 294:            IF  DALYREJS-STATUS = '00'                                           
 295:                MOVE 0 TO APPL-RESULT                                            
 296:            ELSE                                                                 
 297:                MOVE 12 TO APPL-RESULT                                           
 298:            END-IF                                                               
 299:            IF  APPL-AOK                                                         
```

## 20. CBTRN02C-constant-333-154

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 21. CBTRN02C-constant-675-407

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 675:            MOVE 8 TO APPL-RESULT.                                               
 676:            CLOSE TCATBAL-FILE                                                   
 677:            IF  TCATBALF-STATUS  = '00'                                          
 678:                MOVE 0 TO APPL-RESULT                                            
 679:            ELSE                                                                 
 680:                MOVE 12 TO APPL-RESULT                                           
 681:            END-IF                                                               
 682:            IF  APPL-AOK                                                         
```

## 22. CBTRN02C-delete-MOVE-601-348

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 601:            MOVE 8 TO  APPL-RESULT.                                              
 602:            CLOSE TRANSACT-FILE                                                  
 603:            IF  TRANFILE-STATUS = '00'                                           
 604:                MOVE 0 TO  APPL-RESULT                                           
 605:            ELSE                                                                 
 606:                MOVE 12 TO APPL-RESULT                                           
 607:            END-IF                                                               
 608:            IF  APPL-AOK                                                         
```

## 23. CBTRN02C-delete-MOVE-643-386

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

```cobol
 638:            MOVE 8 TO APPL-RESULT.                                               
 639:            CLOSE DALYREJS-FILE                                                  
 640:            IF  DALYREJS-STATUS = '00'                                           
 641:                MOVE 0 TO APPL-RESULT                                            
 642:            ELSE                                                                 
 643:                MOVE 12 TO APPL-RESULT                                           
```

## 24. CBTRN02C-constant-643-385

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 25. CBTRN02C-constant-297-124

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 26. CBTRN02C-delete-MOVE-450-237

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 450:            MOVE 8 TO APPL-RESULT                                                
 451:            WRITE FD-REJS-RECORD FROM REJECT-RECORD                              
 452:            IF DALYREJS-STATUS = '00'                                            
 453:                MOVE 0 TO  APPL-RESULT                                           
 454:            ELSE                                                                 
 455:                MOVE 12 TO APPL-RESULT                                           
 456:            END-IF                                                               
 457:            IF  APPL-AOK                                                         
```

## 27. CBTRN02C-constant-297-125

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 28. CBTRN02C-constant-606-355

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

```cobol
 142:        01  APPL-RESULT             PIC S9(9)   COMP.                            
 143:            88  APPL-AOK            VALUE 0.                                     
 144:            88  APPL-EOF            VALUE 16.                                    
 237:            MOVE 8 TO APPL-RESULT.                                               
 240:                MOVE 0 TO APPL-RESULT                                            
 242:                MOVE 12 TO APPL-RESULT                                           
 255:            MOVE 8 TO APPL-RESULT.                                               
 258:                MOVE 0 TO APPL-RESULT                                            
 260:                MOVE 12 TO APPL-RESULT                                           
 274:            MOVE 8 TO APPL-RESULT.                                               
 277:                MOVE 0 TO APPL-RESULT                                            
 279:                MOVE 12 TO APPL-RESULT                                           
 292:            MOVE 8 TO APPL-RESULT.                                               
 295:                MOVE 0 TO APPL-RESULT                                            
 297:                MOVE 12 TO APPL-RESULT                                           
 310:            MOVE 8 TO APPL-RESULT.                                               
 313:                MOVE 0 TO APPL-RESULT                                            
 315:                MOVE 12 TO APPL-RESULT                                           
 328:            MOVE 8 TO APPL-RESULT.                                               
 331:                MOVE 0 TO APPL-RESULT                                            
 333:                MOVE 12 TO APPL-RESULT                                           
 348:                MOVE 0 TO APPL-RESULT                                            
 352:                    MOVE 16 TO APPL-RESULT                                       
 354:                    MOVE 12 TO APPL-RESULT                                       
 450:            MOVE 8 TO APPL-RESULT                                                
 453:                MOVE 0 TO  APPL-RESULT                                           
 455:                MOVE 12 TO APPL-RESULT                                           
 482:                MOVE 0 TO APPL-RESULT                                            
 484:                MOVE 12 TO APPL-RESULT                                           
 513:                MOVE 0 TO APPL-RESULT                                            
 515:                MOVE 12 TO APPL-RESULT                                           
 531:                MOVE 0 TO APPL-RESULT                                            
 533:                MOVE 12 TO APPL-RESULT                                           
 563:            MOVE 8 TO  APPL-RESULT.                                              
 567:                MOVE 0 TO  APPL-RESULT                                           
 569:                MOVE 12 TO APPL-RESULT                                           
 583:            MOVE 8 TO  APPL-RESULT.                                              
 586:                MOVE 0 TO APPL-RESULT                                            
 588:                MOVE 12 TO APPL-RESULT                                           
 601:            MOVE 8 TO  APPL-RESULT.                                              
 604:                MOVE 0 TO  APPL-RESULT                                           
 606:                MOVE 12 TO APPL-RESULT                                           
 620:            MOVE 8 TO APPL-RESULT.                                               
 623:                MOVE 0 TO APPL-RESULT                                            
 625:                MOVE 12 TO APPL-RESULT                                           
 638:            MOVE 8 TO APPL-RESULT.                                               
 641:                MOVE 0 TO APPL-RESULT                                            
 643:                MOVE 12 TO APPL-RESULT                                           
 656:            MOVE 8 TO APPL-RESULT.                                               
 659:                MOVE 0 TO APPL-RESULT                                            
 661:                MOVE 12 TO APPL-RESULT                                           
 675:            MOVE 8 TO APPL-RESULT.                                               
 678:                MOVE 0 TO APPL-RESULT                                            
 680:                MOVE 12 TO APPL-RESULT                                           
```

## 29. CBTRN02C-constant-450-236

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 450:            MOVE 8 TO APPL-RESULT                                                
 451:            WRITE FD-REJS-RECORD FROM REJECT-RECORD                              
 452:            IF DALYREJS-STATUS = '00'                                            
 453:                MOVE 0 TO  APPL-RESULT                                           
 454:            ELSE                                                                 
 455:                MOVE 12 TO APPL-RESULT                                           
 456:            END-IF                                                               
 457:            IF  APPL-AOK                                                         
```

## 30. CBTRN02C-constant-583-331

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

```cobol
 583:            MOVE 8 TO  APPL-RESULT.                                              
 584:            CLOSE DALYTRAN-FILE                                                  
 585:            IF  DALYTRAN-STATUS = '00'                                           
 586:                MOVE 0 TO APPL-RESULT                                            
 587:            ELSE                                                                 
 588:                MOVE 12 TO APPL-RESULT                                           
 589:            END-IF                                                               
 590:            IF  APPL-AOK                                                         
```

