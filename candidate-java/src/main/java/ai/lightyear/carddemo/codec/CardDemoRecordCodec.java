package ai.lightyear.carddemo.codec;

import ai.lightyear.carddemo.domain.Records.Account;
import ai.lightyear.carddemo.domain.Records.CardXref;
import ai.lightyear.carddemo.domain.Records.CategoryBalance;
import ai.lightyear.carddemo.domain.Records.Disclosure;
import ai.lightyear.carddemo.domain.Records.Transaction;

public final class CardDemoRecordCodec {

    public static final int CATEGORY_BALANCE_LENGTH = 50;
    public static final int DISCLOSURE_LENGTH = 50;
    public static final int CARD_XREF_LENGTH = 50;
    public static final int ACCOUNT_LENGTH = 300;
    public static final int TRANSACTION_LENGTH = 350;

    private CardDemoRecordCodec() {
    }

    public static CategoryBalance parseCategoryBalance(String raw) {
        String value = padded(raw, CATEGORY_BALANCE_LENGTH);
        return new CategoryBalance(
                value.substring(0, 11),
                value.substring(11, 13),
                value.substring(13, 17),
                ZonedDecimal.decode(value.substring(17, 28), 2),
                value.substring(28, 50));
    }

    public static Disclosure parseDisclosure(String raw) {
        String value = padded(raw, DISCLOSURE_LENGTH);
        return new Disclosure(
                value.substring(0, 10),
                value.substring(10, 12),
                value.substring(12, 16),
                ZonedDecimal.decode(value.substring(16, 22), 2),
                value.substring(22, 50));
    }

    public static CardXref parseCardXref(String raw) {
        String value = padded(raw, CARD_XREF_LENGTH);
        return new CardXref(
                value.substring(0, 16),
                value.substring(16, 25),
                value.substring(25, 36),
                value.substring(36, 50));
    }

    public static Account parseAccount(String raw) {
        String value = padded(raw, ACCOUNT_LENGTH);
        return new Account(
                value.substring(0, 11),
                value.substring(11, 12),
                ZonedDecimal.decode(value.substring(12, 24), 2),
                ZonedDecimal.decode(value.substring(24, 36), 2),
                ZonedDecimal.decode(value.substring(36, 48), 2),
                value.substring(48, 58),
                value.substring(58, 68),
                value.substring(68, 78),
                ZonedDecimal.decode(value.substring(78, 90), 2),
                ZonedDecimal.decode(value.substring(90, 102), 2),
                value.substring(102, 112),
                value.substring(112, 122),
                value.substring(122, 300));
    }

    public static String renderAccount(Account value) {
        return String.join("",
                leftPad(value.accountId(), 11, '0'),
                fit(value.activeStatus(), 1),
                ZonedDecimal.encode(value.currentBalance(), 12, 2),
                ZonedDecimal.encode(value.creditLimit(), 12, 2),
                ZonedDecimal.encode(value.cashCreditLimit(), 12, 2),
                fit(value.openDate(), 10),
                fit(value.expirationDate(), 10),
                fit(value.reissueDate(), 10),
                ZonedDecimal.encode(value.currentCycleCredit(), 12, 2),
                ZonedDecimal.encode(value.currentCycleDebit(), 12, 2),
                fit(value.addressZip(), 10),
                fit(value.groupId(), 10),
                fit(value.filler(), 178));
    }

    public static String renderTransaction(Transaction value) {
        return String.join("",
                fit(value.transactionId(), 16),
                fit(value.typeCode(), 2),
                leftPad(value.categoryCode(), 4, '0'),
                fit(value.source(), 10),
                fit(value.description(), 100),
                ZonedDecimal.encode(value.amount(), 11, 2),
                leftPad(value.merchantId(), 9, '0'),
                fit(value.merchantName(), 50),
                fit(value.merchantCity(), 50),
                fit(value.merchantZip(), 10),
                fit(value.cardNumber(), 16),
                fit(value.originalTimestamp(), 26),
                fit(value.processingTimestamp(), 26),
                fit(value.filler(), 20));
    }

    private static String padded(String value, int length) {
        if (value.length() > length) {
            throw new IllegalArgumentException("Record length " + value.length() + " exceeds " + length);
        }
        return fit(value, length);
    }

    private static String fit(String value, int length) {
        String safe = value == null ? "" : value;
        return safe.length() >= length ? safe.substring(0, length) : safe + " ".repeat(length - safe.length());
    }

    private static String leftPad(String value, int length, char pad) {
        String safe = value == null ? "" : value;
        if (safe.length() > length) {
            return safe.substring(safe.length() - length);
        }
        return String.valueOf(pad).repeat(length - safe.length()) + safe;
    }
}

