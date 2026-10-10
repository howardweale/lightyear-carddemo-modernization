Scenario: category-1
  Given public captured inputs {"account": "00000000001", "balance": "0.00", "before_balance": "194.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "9680294154603697", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "194.00", "card": "9680294154603697", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000001", "present": true, "source": "System", "type": "01"}

Scenario: category-2
  Given public captured inputs {"account": "00000000002", "balance": "0.00", "before_balance": "158.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "0923877193247330", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "158.00", "card": "0923877193247330", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000002", "present": true, "source": "System", "type": "01"}

Scenario: category-3
  Given public captured inputs {"account": "00000000003", "balance": "0.00", "before_balance": "147.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "3999169246375885", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "147.00", "card": "3999169246375885", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000003", "present": true, "source": "System", "type": "01"}

Scenario: category-4
  Given public captured inputs {"account": "00000000004", "balance": "0.00", "before_balance": "40.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "2988091353094312", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "40.00", "card": "2988091353094312", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000004", "present": true, "source": "System", "type": "01"}

Scenario: category-5
  Given public captured inputs {"account": "00000000005", "balance": "0.00", "before_balance": "345.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6009619150674526", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "345.00", "card": "6009619150674526", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000005", "present": true, "source": "System", "type": "01"}

Scenario: category-6
  Given public captured inputs {"account": "00000000006", "balance": "0.00", "before_balance": "218.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "2871968252812490", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "218.00", "card": "2871968252812490", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000006", "present": true, "source": "System", "type": "01"}

Scenario: category-7
  Given public captured inputs {"account": "00000000007", "balance": "0.00", "before_balance": "193.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "4859452612877065", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "193.00", "card": "4859452612877065", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000007", "present": true, "source": "System", "type": "01"}

Scenario: category-8
  Given public captured inputs {"account": "00000000008", "balance": "0.00", "before_balance": "605.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "8931369351894783", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "605.00", "card": "8931369351894783", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000008", "present": true, "source": "System", "type": "01"}

Scenario: category-9
  Given public captured inputs {"account": "00000000009", "balance": "0.00", "before_balance": "560.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "9501733721429893", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "560.00", "card": "9501733721429893", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000009", "present": true, "source": "System", "type": "01"}

Scenario: category-10
  Given public captured inputs {"account": "00000000010", "balance": "0.00", "before_balance": "159.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "3260763612337560", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "159.00", "card": "3260763612337560", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000010", "present": true, "source": "System", "type": "01"}

Scenario: category-11
  Given public captured inputs {"account": "00000000011", "balance": "0.00", "before_balance": "212.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7427684863423209", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "212.00", "card": "7427684863423209", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000011", "present": true, "source": "System", "type": "01"}

Scenario: category-12
  Given public captured inputs {"account": "00000000012", "balance": "0.00", "before_balance": "176.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "0982496213629795", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "176.00", "card": "0982496213629795", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000012", "present": true, "source": "System", "type": "01"}

Scenario: category-13
  Given public captured inputs {"account": "00000000013", "balance": "0.00", "before_balance": "41.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "4011500891777367", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "41.00", "card": "4011500891777367", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000013", "present": true, "source": "System", "type": "01"}

Scenario: category-14
  Given public captured inputs {"account": "00000000014", "balance": "0.00", "before_balance": "15.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "8517866958206008", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "15.00", "card": "8517866958206008", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000014", "present": true, "source": "System", "type": "01"}

Scenario: category-15
  Given public captured inputs {"account": "00000000015", "balance": "0.00", "before_balance": "489.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6349250331648509", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "489.00", "card": "6349250331648509", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000015", "present": true, "source": "System", "type": "01"}

Scenario: category-16
  Given public captured inputs {"account": "00000000016", "balance": "0.00", "before_balance": "733.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6727055190616014", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "733.00", "card": "6727055190616014", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000016", "present": true, "source": "System", "type": "01"}

Scenario: category-17
  Given public captured inputs {"account": "00000000017", "balance": "0.00", "before_balance": "33.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "9349107475869214", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "33.00", "card": "9349107475869214", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000017", "present": true, "source": "System", "type": "01"}

Scenario: category-18
  Given public captured inputs {"account": "00000000018", "balance": "0.00", "before_balance": "144.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "5671184478505844", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "144.00", "card": "5671184478505844", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000018", "present": true, "source": "System", "type": "01"}

Scenario: category-19
  Given public captured inputs {"account": "00000000019", "balance": "0.00", "before_balance": "480.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "3940246016141489", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "480.00", "card": "3940246016141489", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000019", "present": true, "source": "System", "type": "01"}

Scenario: category-20
  Given public captured inputs {"account": "00000000020", "balance": "0.00", "before_balance": "369.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "0927987108636232", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "369.00", "card": "0927987108636232", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000020", "present": true, "source": "System", "type": "01"}

Scenario: category-21
  Given public captured inputs {"account": "00000000021", "balance": "0.00", "before_balance": "112.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "5407099850479866", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "112.00", "card": "5407099850479866", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000021", "present": true, "source": "System", "type": "01"}

Scenario: category-22
  Given public captured inputs {"account": "00000000022", "balance": "0.00", "before_balance": "55.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "2940139362300449", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "55.00", "card": "2940139362300449", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000022", "present": true, "source": "System", "type": "01"}

Scenario: category-23
  Given public captured inputs {"account": "00000000023", "balance": "0.00", "before_balance": "104.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "8112545834239735", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "104.00", "card": "8112545834239735", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000023", "present": true, "source": "System", "type": "01"}

Scenario: category-24
  Given public captured inputs {"account": "00000000024", "balance": "0.00", "before_balance": "400.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "2760836797107565", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "400.00", "card": "2760836797107565", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000024", "present": true, "source": "System", "type": "01"}

Scenario: category-25
  Given public captured inputs {"account": "00000000025", "balance": "0.00", "before_balance": "61.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "9056297931664011", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "61.00", "card": "9056297931664011", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000025", "present": true, "source": "System", "type": "01"}

Scenario: category-26
  Given public captured inputs {"account": "00000000026", "balance": "0.00", "before_balance": "46.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "8040580410348680", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "46.00", "card": "8040580410348680", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000026", "present": true, "source": "System", "type": "01"}

Scenario: category-27
  Given public captured inputs {"account": "00000000027", "balance": "0.00", "before_balance": "284.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "0683586198171516", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "284.00", "card": "0683586198171516", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000027", "present": true, "source": "System", "type": "01"}

Scenario: category-28
  Given public captured inputs {"account": "00000000028", "balance": "0.00", "before_balance": "68.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6723000463207764", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "68.00", "card": "6723000463207764", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000028", "present": true, "source": "System", "type": "01"}

Scenario: category-29
  Given public captured inputs {"account": "00000000029", "balance": "0.00", "before_balance": "339.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7251508149188883", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "339.00", "card": "7251508149188883", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000029", "present": true, "source": "System", "type": "01"}

Scenario: category-30
  Given public captured inputs {"account": "00000000030", "balance": "0.00", "before_balance": "2.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6509230362553816", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "2.00", "card": "6509230362553816", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000030", "present": true, "source": "System", "type": "01"}

Scenario: category-31
  Given public captured inputs {"account": "00000000031", "balance": "0.00", "before_balance": "31.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7026637615032277", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "31.00", "card": "7026637615032277", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000031", "present": true, "source": "System", "type": "01"}

Scenario: category-32
  Given public captured inputs {"account": "00000000032", "balance": "0.00", "before_balance": "30.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7094142751055551", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "30.00", "card": "7094142751055551", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000032", "present": true, "source": "System", "type": "01"}

Scenario: category-33
  Given public captured inputs {"account": "00000000033", "balance": "0.00", "before_balance": "410.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6832676047698087", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "410.00", "card": "6832676047698087", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000033", "present": true, "source": "System", "type": "01"}

Scenario: category-34
  Given public captured inputs {"account": "00000000034", "balance": "0.00", "before_balance": "253.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "4385271476627819", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "253.00", "card": "4385271476627819", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000034", "present": true, "source": "System", "type": "01"}

Scenario: category-35
  Given public captured inputs {"account": "00000000035", "balance": "0.00", "before_balance": "166.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "1561409106491600", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "166.00", "card": "1561409106491600", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000035", "present": true, "source": "System", "type": "01"}

Scenario: category-36
  Given public captured inputs {"account": "00000000036", "balance": "0.00", "before_balance": "110.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "4534784102713951", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "110.00", "card": "4534784102713951", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000036", "present": true, "source": "System", "type": "01"}

Scenario: category-37
  Given public captured inputs {"account": "00000000037", "balance": "0.00", "before_balance": "7.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "1142167692878931", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "7.00", "card": "1142167692878931", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000037", "present": true, "source": "System", "type": "01"}

Scenario: category-38
  Given public captured inputs {"account": "00000000038", "balance": "0.00", "before_balance": "612.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7443870988897530", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "612.00", "card": "7443870988897530", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000038", "present": true, "source": "System", "type": "01"}

Scenario: category-39
  Given public captured inputs {"account": "00000000039", "balance": "0.00", "before_balance": "843.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "2745303720002090", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "843.00", "card": "2745303720002090", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000039", "present": true, "source": "System", "type": "01"}

Scenario: category-40
  Given public captured inputs {"account": "00000000040", "balance": "0.00", "before_balance": "43.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "9805583408996588", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "43.00", "card": "9805583408996588", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000040", "present": true, "source": "System", "type": "01"}

Scenario: category-41
  Given public captured inputs {"account": "00000000041", "balance": "0.00", "before_balance": "375.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "3766281984155154", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "375.00", "card": "3766281984155154", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000041", "present": true, "source": "System", "type": "01"}

Scenario: category-42
  Given public captured inputs {"account": "00000000042", "balance": "0.00", "before_balance": "302.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "5975117516616077", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "302.00", "card": "5975117516616077", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000042", "present": true, "source": "System", "type": "01"}

Scenario: category-43
  Given public captured inputs {"account": "00000000043", "balance": "0.00", "before_balance": "610.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7058267261837752", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "610.00", "card": "7058267261837752", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000043", "present": true, "source": "System", "type": "01"}

Scenario: category-44
  Given public captured inputs {"account": "00000000044", "balance": "0.00", "before_balance": "263.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "1014086565224350", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "263.00", "card": "1014086565224350", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000044", "present": true, "source": "System", "type": "01"}

Scenario: category-45
  Given public captured inputs {"account": "00000000045", "balance": "0.00", "before_balance": "186.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "7379335634661142", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "186.00", "card": "7379335634661142", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000045", "present": true, "source": "System", "type": "01"}

Scenario: category-46
  Given public captured inputs {"account": "00000000046", "balance": "0.00", "before_balance": "396.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "5656830544981216", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "396.00", "card": "5656830544981216", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000046", "present": true, "source": "System", "type": "01"}

Scenario: category-47
  Given public captured inputs {"account": "00000000047", "balance": "0.00", "before_balance": "32.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "5787351228879339", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "32.00", "card": "5787351228879339", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000047", "present": true, "source": "System", "type": "01"}

Scenario: category-48
  Given public captured inputs {"account": "00000000048", "balance": "0.00", "before_balance": "226.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "6503535181795992", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "226.00", "card": "6503535181795992", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000048", "present": true, "source": "System", "type": "01"}

Scenario: category-49
  Given public captured inputs {"account": "00000000049", "balance": "0.00", "before_balance": "100.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": true, "card": "8262593602473076", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "100.00", "card": "8262593602473076", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000049", "present": true, "source": "System", "type": "01"}

Scenario: category-50
  Given public captured inputs {"account": "00000000050", "balance": "0.00", "before_balance": "492.00", "before_credit": "0.00", "before_debit": "0.00", "boundary": false, "card": "0500024453765740", "fallback": true, "rate": "15.00", "total": "0.00"}
  When the recorded implementation runs
  Then its recorded output is {"account_present": true, "amount": "0.00", "balance": "492.00", "card": "0500024453765740", "category": "0005", "contract": true, "credit": "0.00", "debit": "0.00", "description": "Int. for a/c 00000000050", "present": true, "source": "System", "type": "01"}