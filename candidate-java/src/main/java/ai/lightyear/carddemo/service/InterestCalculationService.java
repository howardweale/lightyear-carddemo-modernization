package ai.lightyear.carddemo.service;

import ai.lightyear.carddemo.domain.Records.Account;
import ai.lightyear.carddemo.domain.Records.CardXref;
import ai.lightyear.carddemo.domain.Records.CategoryBalance;
import ai.lightyear.carddemo.domain.Records.Disclosure;
import ai.lightyear.carddemo.domain.Records.Transaction;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

@Service
public class InterestCalculationService {

    public RunResult calculate(
            List<CategoryBalance> balances,
            List<Disclosure> disclosures,
            List<CardXref> xrefs,
            List<Account> accounts,
            String processingDate,
            String timestamp,
            String finalAccountPolicy) {
        if (processingDate.length() != 10) {
            throw new IllegalArgumentException("processingDate must be exactly 10 characters");
        }
        if (timestamp.length() != 26) {
            throw new IllegalArgumentException("timestamp must be exactly 26 characters");
        }
        if (!List.of("source-faithful", "intended").contains(finalAccountPolicy)) {
            throw new IllegalArgumentException("finalAccountPolicy must be source-faithful or intended");
        }

        Map<String, Account> accountById = accounts.stream().collect(Collectors.toMap(
                Account::accountId,
                value -> value,
                (left, right) -> left,
                LinkedHashMap::new));
        Map<String, CardXref> xrefByAccount = xrefs.stream().collect(Collectors.toMap(CardXref::accountId, value -> value));
        Map<DisclosureKey, Disclosure> disclosureByKey = disclosures.stream().collect(Collectors.toMap(
                value -> new DisclosureKey(value.groupId(), value.typeCode(), value.categoryCode()),
                value -> value));

        String currentAccountId = null;
        Account currentAccount = null;
        CardXref currentXref = null;
        BigDecimal totalInterest = BigDecimal.ZERO.setScale(2);
        List<Transaction> generated = new ArrayList<>();
        int accountUpdates = 0;
        int defaultRatesUsed = 0;
        int zeroRateRows = 0;

        for (CategoryBalance balance : balances) {
            if (!Objects.equals(balance.accountId(), currentAccountId)) {
                if (currentAccount != null) {
                    accountById.put(currentAccount.accountId(), currentAccount.withInterest(totalInterest));
                    accountUpdates++;
                }
                currentAccountId = balance.accountId();
                totalInterest = BigDecimal.ZERO.setScale(2);
                currentAccount = required(accountById.get(currentAccountId), "ACCOUNT NOT FOUND: " + currentAccountId);
                currentXref = required(xrefByAccount.get(currentAccountId), "XREF NOT FOUND: " + currentAccountId);
            }

            DisclosureKey key = new DisclosureKey(
                    currentAccount.groupId(), balance.typeCode(), balance.categoryCode());
            Disclosure disclosure = disclosureByKey.get(key);
            if (disclosure == null) {
                disclosure = disclosureByKey.get(
                        new DisclosureKey("DEFAULT   ", balance.typeCode(), balance.categoryCode()));
                defaultRatesUsed++;
            }
            disclosure = required(
                    disclosure,
                    "DEFAULT DISCLOSURE MISSING: type=" + balance.typeCode() + " category=" + balance.categoryCode());
            if (disclosure.annualRate().signum() == 0) {
                zeroRateRows++;
                continue;
            }

            BigDecimal monthly = balance.balance()
                    .multiply(disclosure.annualRate())
                    .divide(BigDecimal.valueOf(1200), 2, RoundingMode.DOWN);
            totalInterest = totalInterest.add(monthly).setScale(2, RoundingMode.DOWN);
            int suffix = generated.size() + 1;
            generated.add(new Transaction(
                    processingDate + "%06d".formatted(suffix),
                    "01",
                    "0005",
                    "System",
                    "Int. for a/c " + currentAccount.accountId(),
                    monthly,
                    "000000000",
                    "",
                    "",
                    "",
                    currentXref.cardNumber(),
                    timestamp,
                    timestamp,
                    ""));
        }

        // Source-faithful mode intentionally preserves CBACT04C's EOF branch:
        // the final account is not rewritten after the final read sets EOF.
        if ("intended".equals(finalAccountPolicy) && currentAccount != null) {
            accountById.put(currentAccount.accountId(), currentAccount.withInterest(totalInterest));
            accountUpdates++;
        }

        Observations observations = new Observations(
                balances.size(),
                accountUpdates,
                generated.size(),
                defaultRatesUsed,
                zeroRateRows,
                finalAccountPolicy);
        return new RunResult(new ArrayList<>(accountById.values()), generated, observations);
    }

    private static <T> T required(T value, String message) {
        if (value == null) {
            throw new IllegalStateException(message);
        }
        return value;
    }

    private record DisclosureKey(String groupId, String typeCode, String categoryCode) {
    }

    public record Observations(
            int balanceRows,
            int accountUpdates,
            int transactionsCreated,
            int defaultRatesUsed,
            int zeroRateRows,
            String finalAccountPolicy) {
    }

    public record RunResult(
            List<Account> accounts,
            List<Transaction> transactions,
            Observations observations) {
    }
}

