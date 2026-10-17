# INTCALC — 30-member APPL-RESULT audit before signing

Twin scope only. Review each sampled mutation and its argument before signing the full class request.
The complete 81-member inventory and exact proof bindings are in audit.json and class-request.json.
This sample is newly packaged; no signature or completed review of this packet is inferred.

## 1. CBACT04C-constant-271-112

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
271:            MOVE 8 TO APPL-RESULT.                                               
272:            OPEN INPUT DISCGRP-FILE                                              
273:            IF  DISCGRP-STATUS = '00'                                            
274:                MOVE 0 TO APPL-RESULT                                            
275:            ELSE                                                                 
276:                MOVE 12 TO APPL-RESULT                                           
277:            END-IF                                                               
278:            IF  APPL-AOK                                                         
```

## 2. CBACT04C-constant-235-81

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 7 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
235:            MOVE 8 TO APPL-RESULT.                                               
236:            OPEN INPUT TCATBAL-FILE                                              
237:            IF  TCATBALF-STATUS = '00'                                           
238:                MOVE 0 TO APPL-RESULT                                            
239:            ELSE                                                                 
240:                MOVE 12 TO APPL-RESULT                                           
241:            END-IF                                                               
242:            IF  APPL-AOK                                                         
```

## 3. CBACT04C-constant-528-294

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 4. CBACT04C-constant-425-225

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 5. CBACT04C-delete-MOVE-523-287

Original:
```cobol
           MOVE 8 TO  APPL-RESULT.                                              
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
523:            MOVE 8 TO  APPL-RESULT.                                              
524:            CLOSE TCATBAL-FILE                                                   
525:            IF  TCATBALF-STATUS = '00'                                           
526:                MOVE 0 TO  APPL-RESULT                                           
527:            ELSE                                                                 
528:                MOVE 12 TO APPL-RESULT                                           
529:            END-IF                                                               
530:            IF  APPL-AOK                                                         
```

## 6. CBACT04C-constant-578-331

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
578:            MOVE 8 TO APPL-RESULT.                                               
579:            CLOSE ACCOUNT-FILE                                                   
580:            IF  ACCTFILE-STATUS  = '00'                                          
581:                MOVE 0 TO APPL-RESULT                                            
582:            ELSE                                                                 
583:                MOVE 12 TO APPL-RESULT                                           
584:            END-IF                                                               
585:            IF  APPL-AOK                                                         
```

## 7. CBACT04C-delete-MOVE-596-347

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
596:            MOVE 8 TO APPL-RESULT.                                               
597:            CLOSE TRANSACT-FILE                                                  
598:            IF  TRANFILE-STATUS  = '00'                                          
599:                MOVE 0 TO APPL-RESULT                                            
600:            ELSE                                                                 
601:                MOVE 12 TO APPL-RESULT                                           
602:            END-IF                                                               
603:            IF  APPL-AOK                                                         
```

## 8. CBACT04C-delete-MOVE-547-310

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Bound source context:
```cobol
542:            MOVE 8 TO APPL-RESULT.                                               
543:            CLOSE XREF-FILE                                                      
544:            IF  XREFFILE-STATUS = '00'                                           
545:                MOVE 0 TO APPL-RESULT                                            
546:            ELSE                                                                 
547:                MOVE 12 TO APPL-RESULT                                           
```

## 9. CBACT04C-constant-542-301

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
542:            MOVE 8 TO APPL-RESULT.                                               
543:            CLOSE XREF-FILE                                                      
544:            IF  XREFFILE-STATUS = '00'                                           
545:                MOVE 0 TO APPL-RESULT                                            
546:            ELSE                                                                 
547:                MOVE 12 TO APPL-RESULT                                           
548:            END-IF                                                               
549:            IF  APPL-AOK                                                         
```

## 10. CBACT04C-constant-290-127

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
290:            MOVE 8 TO APPL-RESULT.                                               
291:            OPEN I-O ACCOUNT-FILE                                                
292:            IF  ACCTFILE-STATUS = '00'                                           
293:                MOVE 0 TO APPL-RESULT                                            
294:            ELSE                                                                 
295:                MOVE 12 TO APPL-RESULT                                           
296:            END-IF                                                               
297:            IF  APPL-AOK                                                         
```

## 11. CBACT04C-constant-290-126

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 7 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
290:            MOVE 8 TO APPL-RESULT.                                               
291:            OPEN I-O ACCOUNT-FILE                                                
292:            IF  ACCTFILE-STATUS = '00'                                           
293:                MOVE 0 TO APPL-RESULT                                            
294:            ELSE                                                                 
295:                MOVE 12 TO APPL-RESULT                                           
296:            END-IF                                                               
297:            IF  APPL-AOK                                                         
```

## 12. CBACT04C-delete-MOVE-401-211

Original:
```cobol
               MOVE 0 TO APPL-RESULT                                            
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Bound source context:
```cobol
182:            PERFORM 0000-TCATBALF-OPEN.                                          
186:            PERFORM 0400-TRANFILE-OPEN.                                          
188:            PERFORM UNTIL END-OF-FILE = 'Y'                                      
190:                    PERFORM 1000-TCATBALF-GET-NEXT                               
191:                    IF  END-OF-FILE = 'N'                                        
197:                        ELSE                                                     
203:                        PERFORM 1100-GET-ACCT-DATA                               
205:                        PERFORM 1110-GET-XREF-DATA                               
213:                      PERFORM 1200-GET-INTEREST-RATE                             
215:                        PERFORM 1300-COMPUTE-INTEREST                            
220:                     PERFORM 1050-UPDATE-ACCOUNT                                 
224:            PERFORM 9000-TCATBALF-CLOSE.                                         
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
340:                    MOVE 'Y' TO END-OF-FILE                                      
401:                MOVE 0 TO APPL-RESULT                                            
423:                MOVE 0 TO APPL-RESULT                                            
435:            END-IF                                                               
438:                PERFORM 1200-A-GET-DEFAULT-INT-RATE                              
447:                MOVE 0 TO APPL-RESULT                                            
632:            CALL 'CEE3ABD' USING ABCODE, TIMING.                                 
```

## 13. CBACT04C-delete-MOVE-290-128

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
290:            MOVE 8 TO APPL-RESULT.                                               
291:            OPEN I-O ACCOUNT-FILE                                                
292:            IF  ACCTFILE-STATUS = '00'                                           
293:                MOVE 0 TO APPL-RESULT                                            
294:            ELSE                                                                 
295:                MOVE 12 TO APPL-RESULT                                           
296:            END-IF                                                               
297:            IF  APPL-AOK                                                         
```

## 14. CBACT04C-delete-MOVE-542-302

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
542:            MOVE 8 TO APPL-RESULT.                                               
543:            CLOSE XREF-FILE                                                      
544:            IF  XREFFILE-STATUS = '00'                                           
545:                MOVE 0 TO APPL-RESULT                                            
546:            ELSE                                                                 
547:                MOVE 12 TO APPL-RESULT                                           
548:            END-IF                                                               
549:            IF  APPL-AOK                                                         
```

## 15. CBACT04C-constant-565-323

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 16. CBACT04C-delete-MOVE-258-106

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Bound source context:
```cobol
253:            MOVE 8 TO APPL-RESULT.                                               
254:            OPEN INPUT XREF-FILE                                                 
255:            IF  XREFFILE-STATUS = '00'                                           
256:                MOVE 0 TO APPL-RESULT                                            
257:            ELSE                                                                 
258:                MOVE 12 TO APPL-RESULT                                           
```

## 17. CBACT04C-constant-504-278

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 18. CBACT04C-delete-MOVE-583-340

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Bound source context:
```cobol
578:            MOVE 8 TO APPL-RESULT.                                               
579:            CLOSE ACCOUNT-FILE                                                   
580:            IF  ACCTFILE-STATUS  = '00'                                          
581:                MOVE 0 TO APPL-RESULT                                            
582:            ELSE                                                                 
583:                MOVE 12 TO APPL-RESULT                                           
```

## 19. CBACT04C-constant-360-189

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 13 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 20. CBACT04C-constant-313-149

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 21. CBACT04C-constant-253-97

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
253:            MOVE 8 TO APPL-RESULT.                                               
254:            OPEN INPUT XREF-FILE                                                 
255:            IF  XREFFILE-STATUS = '00'                                           
256:                MOVE 0 TO APPL-RESULT                                            
257:            ELSE                                                                 
258:                MOVE 12 TO APPL-RESULT                                           
259:            END-IF                                                               
260:            IF  APPL-AOK                                                         
```

## 22. CBACT04C-constant-360-188

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 23. CBACT04C-delete-MOVE-528-295

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Bound source context:
```cobol
523:            MOVE 8 TO  APPL-RESULT.                                              
524:            CLOSE TCATBAL-FILE                                                   
525:            IF  TCATBALF-STATUS = '00'                                           
526:                MOVE 0 TO  APPL-RESULT                                           
527:            ELSE                                                                 
528:                MOVE 12 TO APPL-RESULT                                           
```

## 24. CBACT04C-delete-MOVE-295-136

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       CONTINUE
```

The immediately preceding operation block initializes APPL-RESULT to8, then assigns0 on success or12 on failure. Deleting only the failure assignment retains8 on that branch. Both8 and12 leave the only consumers (numeric0/16 condition names) false; neither is displayed, aliased or externally passed. Successful behavior and all following assignments remain unchanged.

Bound source context:
```cobol
290:            MOVE 8 TO APPL-RESULT.                                               
291:            OPEN I-O ACCOUNT-FILE                                                
292:            IF  ACCTFILE-STATUS = '00'                                           
293:                MOVE 0 TO APPL-RESULT                                            
294:            ELSE                                                                 
295:                MOVE 12 TO APPL-RESULT                                           
```

## 25. CBACT04C-constant-547-308

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 26. CBACT04C-delete-MOVE-578-332

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       CONTINUE.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
578:            MOVE 8 TO APPL-RESULT.                                               
579:            CLOSE ACCOUNT-FILE                                                   
580:            IF  ACCTFILE-STATUS  = '00'                                          
581:                MOVE 0 TO APPL-RESULT                                            
582:            ELSE                                                                 
583:                MOVE 12 TO APPL-RESULT                                           
584:            END-IF                                                               
585:            IF  APPL-AOK                                                         
```

## 27. CBACT04C-delete-MOVE-447-239

Original:
```cobol
               MOVE 0 TO APPL-RESULT                                            
```
Replacement:
```cobol
       CONTINUE
```

Pinned whole-program control-flow invariant: each successful OPEN returns APPL-RESULT0; a failed OPEN terminates through the host CEE3ABD shim. Before each listed non-sentinel operation, the prior successful operation left0. A failed operation sets12 and terminates before another such operation; EOF16 exits the loop before another iteration. INTCALC tariff status23 is explicitly converted to0 before DEFAULT lookup; POSTTRAN validation rejects do not change APPL-RESULT and their reject WRITE returns0. Therefore this single deletion of a success assignment retains0 on its success branch. The unchanged failure branch still sets12 or16. This excludes OPEN/CLOSE/reject-WRITE initializers that first assign8, and assumes the recorded host CEE3ABD terminating shim, not an arbitrary replacement that returns.

Bound source context:
```cobol
182:            PERFORM 0000-TCATBALF-OPEN.                                          
186:            PERFORM 0400-TRANFILE-OPEN.                                          
188:            PERFORM UNTIL END-OF-FILE = 'Y'                                      
190:                    PERFORM 1000-TCATBALF-GET-NEXT                               
191:                    IF  END-OF-FILE = 'N'                                        
197:                        ELSE                                                     
203:                        PERFORM 1100-GET-ACCT-DATA                               
205:                        PERFORM 1110-GET-XREF-DATA                               
213:                      PERFORM 1200-GET-INTEREST-RATE                             
215:                        PERFORM 1300-COMPUTE-INTEREST                            
220:                     PERFORM 1050-UPDATE-ACCOUNT                                 
224:            PERFORM 9000-TCATBALF-CLOSE.                                         
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
340:                    MOVE 'Y' TO END-OF-FILE                                      
423:                MOVE 0 TO APPL-RESULT                                            
435:            END-IF                                                               
438:                PERFORM 1200-A-GET-DEFAULT-INT-RATE                              
447:                MOVE 0 TO APPL-RESULT                                            
632:            CALL 'CEE3ABD' USING ABCODE, TIMING.                                 
```

## 28. CBACT04C-constant-240-89

Original:
```cobol
               MOVE 12 TO APPL-RESULT                                           
```
Replacement:
```cobol
       MOVE 11 TO APPL-RESULT
```

Only APPL-AOK (value0) and APPL-EOF (value16) consume APPL-RESULT; no raw display, alias or external parameter reads it. Substituting11 or13 for12 preserves both condition values as false, and every later assignment is unchanged. Thus the failure branch, displays and RC remain identical for all file statuses.

Bound source context:
```cobol
133:        01  APPL-RESULT             PIC S9(9)   COMP.                            
134:            88  APPL-AOK            VALUE 0.                                     
135:            88  APPL-EOF            VALUE 16.                                    
235:            MOVE 8 TO APPL-RESULT.                                               
238:                MOVE 0 TO APPL-RESULT                                            
240:                MOVE 12 TO APPL-RESULT                                           
253:            MOVE 8 TO APPL-RESULT.                                               
256:                MOVE 0 TO APPL-RESULT                                            
258:                MOVE 12 TO APPL-RESULT                                           
271:            MOVE 8 TO APPL-RESULT.                                               
274:                MOVE 0 TO APPL-RESULT                                            
276:                MOVE 12 TO APPL-RESULT                                           
290:            MOVE 8 TO APPL-RESULT.                                               
293:                MOVE 0 TO APPL-RESULT                                            
295:                MOVE 12 TO APPL-RESULT                                           
308:            MOVE 8 TO APPL-RESULT.                                               
311:                MOVE 0 TO APPL-RESULT                                            
313:                MOVE 12 TO APPL-RESULT                                           
328:                MOVE 0 TO APPL-RESULT                                            
331:                    MOVE 16 TO APPL-RESULT                                       
333:                    MOVE 12 TO APPL-RESULT                                       
358:                MOVE 0 TO APPL-RESULT                                            
360:                MOVE 12 TO APPL-RESULT                                           
379:                MOVE 0 TO APPL-RESULT                                            
381:                MOVE 12 TO APPL-RESULT                                           
401:                MOVE 0 TO APPL-RESULT                                            
403:                MOVE 12 TO APPL-RESULT                                           
423:                MOVE 0 TO APPL-RESULT                                            
425:                MOVE 12 TO APPL-RESULT                                           
447:                MOVE 0 TO APPL-RESULT                                            
449:                MOVE 12 TO APPL-RESULT                                           
502:                MOVE 0 TO APPL-RESULT                                            
504:                MOVE 12 TO APPL-RESULT                                           
523:            MOVE 8 TO  APPL-RESULT.                                              
526:                MOVE 0 TO  APPL-RESULT                                           
528:                MOVE 12 TO APPL-RESULT                                           
542:            MOVE 8 TO APPL-RESULT.                                               
545:                MOVE 0 TO APPL-RESULT                                            
547:                MOVE 12 TO APPL-RESULT                                           
560:            MOVE 8 TO APPL-RESULT.                                               
563:                MOVE 0 TO APPL-RESULT                                            
565:                MOVE 12 TO APPL-RESULT                                           
578:            MOVE 8 TO APPL-RESULT.                                               
581:                MOVE 0 TO APPL-RESULT                                            
583:                MOVE 12 TO APPL-RESULT                                           
596:            MOVE 8 TO APPL-RESULT.                                               
599:                MOVE 0 TO APPL-RESULT                                            
601:                MOVE 12 TO APPL-RESULT                                           
```

## 29. CBACT04C-constant-308-141

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 7 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
308:            MOVE 8 TO APPL-RESULT.                                               
309:            OPEN OUTPUT TRANSACT-FILE                                            
310:            IF  TRANFILE-STATUS = '00'                                           
311:                MOVE 0 TO APPL-RESULT                                            
312:            ELSE                                                                 
313:                MOVE 12 TO APPL-RESULT                                           
314:            END-IF                                                               
315:            IF  APPL-AOK                                                         
```

## 30. CBACT04C-constant-596-346

Original:
```cobol
           MOVE 8 TO APPL-RESULT.                                               
```
Replacement:
```cobol
       MOVE 9 TO APPL-RESULT.
```

The changed/deleted value8 sentinel has no consumer before a total FILE STATUS IF/ELSE overwrites APPL-RESULT with0 or12. The following APPL-AOK reads only that overwrite. The operation does not read this working-storage item. Therefore this initializer cannot affect program outputs/RC/displays on either operation outcome.

Bound source context:
```cobol
596:            MOVE 8 TO APPL-RESULT.                                               
597:            CLOSE TRANSACT-FILE                                                  
598:            IF  TRANFILE-STATUS  = '00'                                          
599:                MOVE 0 TO APPL-RESULT                                            
600:            ELSE                                                                 
601:                MOVE 12 TO APPL-RESULT                                           
602:            END-IF                                                               
603:            IF  APPL-AOK                                                         
```

