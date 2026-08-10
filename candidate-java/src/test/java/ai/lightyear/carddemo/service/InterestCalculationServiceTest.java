package ai.lightyear.carddemo.service;

import static org.assertj.core.api.Assertions.assertThat;

import ai.lightyear.carddemo.domain.Records.Account;
import ai.lightyear.carddemo.domain.Records.CardXref;
import ai.lightyear.carddemo.domain.Records.CategoryBalance;
import ai.lightyear.carddemo.domain.Records.Disclosure;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class InterestCalculationServiceTest {

    private InterestCalculationService service;
    private List<Account> accounts;
    private List<CardXref> xrefs;
    private List<CategoryBalance> balances;
    private List<Disclosure> disclosures;

    @BeforeEach
    void setUp() {
        service = new InterestCalculationService();
        accounts = List.of(
                account("00000000001", "STANDARD  ", "1000.00", "25.00", "75.00"),
                account("00000000002", "SPECIAL   ", "2000.00", "10.00", "50.00"));
        xrefs = List.of(
                new CardXref("4111111111111111", "000000001", "00000000001", ""),
                new CardXref("4222222222222222", "000000002", "00000000002", ""));
        balances = List.of(
                new CategoryBalance("00000000001", "01", "0001", new BigDecimal("1200.00"), ""),
                new CategoryBalance("00000000001", "01", "0002", new BigDecimal("600.00"), ""),
                new CategoryBalance("00000000002", "01", "0001", new BigDecimal("1200.00"), ""));
        disclosures = List.of(
                new Disclosure("STANDARD  ", "01", "0001", new BigDecimal("12.00"), ""),
                new Disclosure("STANDARD  ", "01", "0002", new BigDecimal("24.00"), ""),
                new Disclosure("DEFAULT   ", "01", "0001", new BigDecimal("6.00"), ""));
    }

    @Test
    void matchesInterestAndDefaultRateRules() {
        var result = service.calculate(
                balances,
                disclosures,
                xrefs,
                accounts,
                "2022071800",
                "2022-07-18-00.00.00.000000",
                "source-faithful");

        assertThat(result.accounts().get(0).currentBalance()).isEqualByComparingTo("1024.00");
        assertThat(result.accounts().get(0).currentCycleCredit()).isEqualByComparingTo("0.00");
        assertThat(result.accounts().get(0).currentCycleDebit()).isEqualByComparingTo("0.00");
        assertThat(result.accounts().get(1).currentBalance()).isEqualByComparingTo("2000.00");
        assertThat(result.transactions()).extracting(value -> value.amount().toPlainString())
                .containsExactly("12.00", "12.00", "6.00");
        assertThat(result.observations().defaultRatesUsed()).isEqualTo(1);
    }

    @Test
    void intendedPolicyUpdatesFinalAccount() {
        var result = service.calculate(
                balances,
                disclosures,
                xrefs,
                accounts,
                "2022071800",
                "2022-07-18-00.00.00.000000",
                "intended");
        assertThat(result.accounts().get(1).currentBalance()).isEqualByComparingTo("2006.00");
    }

    @Test
    void zeroRateEmitsNoTransaction() {
        var zeroRate = List.of(new Disclosure("STANDARD  ", "01", "0001", BigDecimal.ZERO, ""));
        var result = service.calculate(
                List.of(balances.get(0)),
                zeroRate,
                List.of(xrefs.get(0)),
                List.of(accounts.get(0)),
                "2022071800",
                "2022-07-18-00.00.00.000000",
                "source-faithful");
        assertThat(result.transactions()).isEmpty();
        assertThat(result.observations().zeroRateRows()).isEqualTo(1);
    }

    private static Account account(
            String id,
            String group,
            String balance,
            String cycleCredit,
            String cycleDebit) {
        return new Account(
                id,
                "Y",
                new BigDecimal(balance),
                new BigDecimal("5000.00"),
                new BigDecimal("1000.00"),
                "2020-01-01",
                "2030-01-01",
                "2030-01-01",
                new BigDecimal(cycleCredit),
                new BigDecimal(cycleDebit),
                "3000      ",
                group,
                "");
    }
}

