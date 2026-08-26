/* Bounded PL/I include fixture for the MS #20 language-pack contract. */
DCL 1 AUTHORIZATION_RECORD,
      5 CARD_NUMBER       CHAR(16),
      5 TRANSACTION_ID    CHAR(16),
      5 AUTHORIZATION_CD  CHAR(6),
      5 APPROVED_AMOUNT   DECIMAL(12,2),
      5 FRAUD_FLAG        CHAR(1);
