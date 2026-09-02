// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts;

import com.example.accounts.model.Account;
import com.example.accounts.model.Journal;
import com.example.accounts.repository.AccountRepository;
import com.example.accounts.repository.JournalRepository;
import com.example.accounts.repository.TransferCommandRepository;
import com.example.accounts.services.TransactionCoreService;
import com.example.accounts.services.TransactionCoreService.InjectedTransferFailure;
import com.example.accounts.services.TransactionCoreService.TransferResult;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "eureka.client.enabled=false",
        "spring.cloud.discovery.enabled=false",
        "spring.cloud.config.enabled=false",
        "cloudbank.security.require-internal-token=false",
        "cloudbank.transaction.internal-token=synthetic-ms61-token"
})
class PostgreSqlAccountEquivalenceTests {

    private static final String CONTRACT =
            "account-success:conserved;invalid:no-mutation;funds:no-mutation;"
                    + "failure:restored;transfer-invalid:400;transfer-auth:403;"
                    + "transfer-success:200";

    @Autowired
    private TransactionCoreService transactions;

    @Autowired
    private AccountRepository accounts;

    @Autowired
    private JournalRepository journals;

    @Autowired
    private TransferCommandRepository commands;

    private long sourceId;
    private long targetId;
    private long emptyId;

    @BeforeEach
    void resetSyntheticAccounts() {
        journals.deleteAll();
        commands.deleteAll();
        accounts.deleteAll();
        sourceId = createAccount("Source", "cust-source", 1000);
        targetId = createAccount("Target", "cust-target", 250);
        emptyId = createAccount("Empty", "cust-empty", 5);
    }

    @Test
    void successfulTransferConservesValueAndFinalizesJournals() {
        TransferResult result = transactions.transfer(
                "postgres-success", sourceId, targetId, 125, "cust-source", false);
        assertTrue(result.accepted());
        assertEquals(875, balance(sourceId));
        assertEquals(375, balance(targetId));
        assertEquals(1250, balance(sourceId) + balance(targetId));
        assertEquals(2, journals.count());
        assertEquals(0, journals.findAll().stream().mapToLong(this::signedAmount).sum());
    }

    @Test
    void invalidAmountDoesNotMutateState() {
        assertFalse(transactions.transfer(
                "postgres-invalid", sourceId, targetId, 0, "cust-source", false).accepted());
        assertEquals(1000, balance(sourceId));
        assertEquals(250, balance(targetId));
        assertEquals(0, journals.count());
    }

    @Test
    void insufficientFundsHaveNoEffectiveMutation() {
        assertFalse(transactions.transfer(
                "postgres-funds", emptyId, targetId, 10, "cust-empty", false).accepted());
        assertEquals(5, balance(emptyId));
        assertEquals(0, journals.count());
    }

    @Test
    void atomicRollbackRestoresTheSourceBalance() {
        assertThrows(InjectedTransferFailure.class, () -> transactions.transfer(
                "postgres-failure", sourceId, targetId, 100, "cust-source", true));
        assertEquals(1000, balance(sourceId));
        assertEquals(250, balance(targetId));
        assertEquals(0, journals.count());
        assertFalse(commands.existsById("postgres-failure"));
        System.out.println("CLOUDBANK_EQUIVALENCE_CONTRACT=" + CONTRACT);
    }

    private long createAccount(String name, String customerId, long balance) {
        Account account = new Account(name, "CH", "MS61 synthetic", customerId);
        account.setAccountBalance(balance);
        return accounts.saveAndFlush(account).getAccountId();
    }

    private long balance(long accountId) {
        return accounts.findById(accountId).orElseThrow().getAccountBalance();
    }

    private long signedAmount(Journal journal) {
        return "WITHDRAW".equals(journal.getJournalType())
                ? -journal.getJournalAmount() : journal.getJournalAmount();
    }
}
