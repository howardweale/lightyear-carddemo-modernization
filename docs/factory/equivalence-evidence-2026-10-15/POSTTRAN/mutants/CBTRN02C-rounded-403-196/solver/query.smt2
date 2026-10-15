; benchmark generated from python API
(set-info :status unknown)
(declare-fun ACCT-CURR-CYC-CREDIT () Int)
(declare-fun DALYTRAN-AMT () Int)
(declare-fun ACCT-CURR-CYC-DEBIT () Int)
(declare-fun WS-TEMP-BAL () Int)
(assert
 (>= ACCT-CURR-CYC-CREDIT (- 999999999999)))
(assert
 (<= ACCT-CURR-CYC-CREDIT 999999999999))
(assert
 (>= DALYTRAN-AMT (- 99999999999)))
(assert
 (<= DALYTRAN-AMT 99999999999))
(assert
 (>= ACCT-CURR-CYC-DEBIT (- 999999999999)))
(assert
 (<= ACCT-CURR-CYC-DEBIT 999999999999))
(assert
 (>= WS-TEMP-BAL (- 99999999999)))
(assert
 (<= WS-TEMP-BAL 99999999999))
(assert
 (let ((?x11529 (to_real DALYTRAN-AMT)))
(let ((?x6591 (/ ?x11529 100.0)))
(let ((?x6603 (to_real ACCT-CURR-CYC-DEBIT)))
(let ((?x7276 (/ ?x6603 100.0)))
(let ((?x8371 (to_real ACCT-CURR-CYC-CREDIT)))
(let ((?x7531 (/ ?x8371 100.0)))
(let ((?x3880 (* (+ (- ?x7531 ?x7276) ?x6591) 100.0)))
(let (($x2645 (< ?x3880 0.0)))
(let ((?x5010 (ite $x2645 (- ?x3880) ?x3880)))
(let ((?x854 (to_int (+ ?x5010 (/ 1.0 2.0)))))
(let (($x1392 (>= ?x854 100000000000)))
(let ((?x5217 (to_int (+ ?x5010 0.0))))
(let (($x8775 (>= ?x5217 100000000000)))
(let ((?x2974 (mod ?x854 100000000000)))
(let ((?x11243 (ite $x2645 (- ?x2974) ?x2974)))
(let ((?x11127 (mod ?x5217 100000000000)))
(let ((?x3777 (ite $x2645 (- ?x11127) ?x11127)))
(or (and (distinct ?x3777 ?x11243) true) (and (distinct $x8775 $x1392) true))))))))))))))))))))
(check-sat)
