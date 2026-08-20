package ai.lightyear.carddemo.service;

import static org.assertj.core.api.Assertions.assertThat;

import ai.lightyear.carddemo.service.CicsVsamAccountViewService.AccountView;
import ai.lightyear.carddemo.service.CicsVsamAccountViewService.CardXrefView;
import ai.lightyear.carddemo.service.CicsVsamAccountViewService.CustomerView;
import ai.lightyear.carddemo.service.CicsVsamAccountViewService.KeyedStore;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CicsVsamAccountViewServiceTest {

    private final CicsVsamAccountViewService service = new CicsVsamAccountViewService();

    @Test
    void resolvesCavwThroughTheAlternateIndexAndTwoPrimaryReads() {
        var xref = new KeyedStore<>(
                "CXACAIX",
                Map.of("00000000001", new CardXrefView("000000001", "4111111111111111")));
        var accounts = new KeyedStore<>(
                "ACCTDAT",
                Map.of("00000000001", new AccountView("Y", "125.25", "5000.00")));
        var customers = new KeyedStore<>(
                "CUSTDAT",
                Map.of("000000001", new CustomerView("JANE CUSTOMER")));

        var result = service.view("00000000001", xref, accounts, customers);

        assertThat(result.status()).isEqualTo("NORMAL");
        assertThat(result.view().customerName()).isEqualTo("JANE CUSTOMER");
        assertThat(result.mutations()).isEmpty();
        assertThat(List.of(
                xref.reads().get(0).resource(),
                accounts.reads().get(0).resource(),
                customers.reads().get(0).resource()))
                .containsExactly("CXACAIX", "ACCTDAT", "CUSTDAT");
    }

    @Test
    void invalidAndMissingAccountsFailClosedWithoutWrites() {
        var emptyXref = new KeyedStore<CardXrefView>("CXACAIX", Map.of());
        var emptyAccounts = new KeyedStore<AccountView>("ACCTDAT", Map.of());
        var emptyCustomers = new KeyedStore<CustomerView>("CUSTDAT", Map.of());

        var invalid = service.view("BAD", emptyXref, emptyAccounts, emptyCustomers);
        var missing = service.view("00000000002", emptyXref, emptyAccounts, emptyCustomers);

        assertThat(invalid.status()).isEqualTo("INVALID_ACCOUNT");
        assertThat(missing.status()).isEqualTo("NOT_FOUND");
        assertThat(invalid.mutations()).isEmpty();
        assertThat(missing.mutations()).isEmpty();
        assertThat(emptyAccounts.reads()).isEmpty();
        assertThat(emptyCustomers.reads()).isEmpty();
    }
}
