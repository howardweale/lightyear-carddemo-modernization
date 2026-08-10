package ai.lightyear.carddemo.domain;

import java.math.BigDecimal;

public final class Records {

    private Records() {
    }

    public record CategoryBalance(
            String accountId,
            String typeCode,
            String categoryCode,
            BigDecimal balance,
            String filler) {
    }

    public record Disclosure(
            String groupId,
            String typeCode,
            String categoryCode,
            BigDecimal annualRate,
            String filler) {
    }

    public record CardXref(
            String cardNumber,
            String customerId,
            String accountId,
            String filler) {
    }

    public record Account(
            String accountId,
            String activeStatus,
            BigDecimal currentBalance,
            BigDecimal creditLimit,
            BigDecimal cashCreditLimit,
            String openDate,
            String expirationDate,
            String reissueDate,
            BigDecimal currentCycleCredit,
            BigDecimal currentCycleDebit,
            String addressZip,
            String groupId,
            String filler) {

        public Account withInterest(BigDecimal interest) {
            return new Account(
                    accountId,
                    activeStatus,
                    currentBalance.add(interest).setScale(2, java.math.RoundingMode.DOWN),
                    creditLimit,
                    cashCreditLimit,
                    openDate,
                    expirationDate,
                    reissueDate,
                    BigDecimal.ZERO.setScale(2),
                    BigDecimal.ZERO.setScale(2),
                    addressZip,
                    groupId,
                    filler);
        }
    }

    public record Transaction(
            String transactionId,
            String typeCode,
            String categoryCode,
            String source,
            String description,
            BigDecimal amount,
            String merchantId,
            String merchantName,
            String merchantCity,
            String merchantZip,
            String cardNumber,
            String originalTimestamp,
            String processingTimestamp,
            String filler) {
    }
}

