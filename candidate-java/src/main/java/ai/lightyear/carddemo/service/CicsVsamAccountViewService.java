package ai.lightyear.carddemo.service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Modern service seam for the read-only CAVW transaction behavior. */
public class CicsVsamAccountViewService {

    public static final String TRANSACTION_ID = "CAVW";
    public static final String PROGRAM_ID = "COACTVWC";
    public static final String MAPSET = "COACTVW";
    public static final String MAP = "CACTVWA";

    public ViewResult view(
            String accountId,
            KeyedStore<CardXrefView> xrefByAccount,
            KeyedStore<AccountView> accounts,
            KeyedStore<CustomerView> customers) {
        if (accountId == null || !accountId.matches("[0-9]{11}")) {
            return ViewResult.error("INVALID_ACCOUNT", "Account number must contain 11 digits");
        }
        CardXrefView xref = xrefByAccount.read(accountId);
        if (xref == null) {
            return ViewResult.error("NOT_FOUND", "Account not found in cross-reference");
        }
        AccountView account = accounts.read(accountId);
        if (account == null) {
            return ViewResult.error("NOT_FOUND", "Account not found in account master");
        }
        CustomerView customer = customers.read(xref.customerId());
        if (customer == null) {
            return ViewResult.error("NOT_FOUND", "Customer not found in customer master");
        }
        return new ViewResult(
                "NORMAL",
                null,
                new ScreenView(
                        accountId,
                        xref.cardNumber(),
                        xref.customerId(),
                        account.status(),
                        account.currentBalance(),
                        account.creditLimit(),
                        customer.name()),
                List.of());
    }

    public static final class KeyedStore<T> {
        private final String name;
        private final Map<String, T> records;
        private final List<ReadObservation> reads = new ArrayList<>();

        public KeyedStore(String name, Map<String, T> records) {
            this.name = Objects.requireNonNull(name);
            this.records = Map.copyOf(records);
        }

        public T read(String key) {
            reads.add(new ReadObservation("READ", name, key));
            return records.get(key);
        }

        public List<ReadObservation> reads() {
            return List.copyOf(reads);
        }
    }

    public record CardXrefView(String customerId, String cardNumber) { }
    public record AccountView(String status, String currentBalance, String creditLimit) { }
    public record CustomerView(String name) { }
    public record ReadObservation(String operation, String resource, String key) { }
    public record ScreenView(
            String accountId,
            String cardNumber,
            String customerId,
            String accountStatus,
            String currentBalance,
            String creditLimit,
            String customerName) { }
    public record ViewResult(String status, String message, ScreenView view, List<String> mutations) {
        static ViewResult error(String status, String message) {
            return new ViewResult(status, message, null, List.of());
        }
    }
}
