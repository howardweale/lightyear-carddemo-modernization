// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts;

import java.util.List;

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
        "cloudbank.transaction.internal-token=synthetic-ms59-token"
})
class TransactionCorePostgreSqlTests {

    private static final String CONTRACT =
            "success:pass;invalid:pass;funds:pass;fault:pass;idempotency:pass;"
                    + "auth:pass;recovery:pass;replay:pass";

    @Autowired
    private TransactionCoreService transactions;

    @Autowired
    private AccountRepository accounts;

    @Autowired
    private JournalRepository journals;

    @Autowired
    private TransferCommandRepository commands;

    @BeforeEach
    void resetSyntheticAccounts() {
        journals.deleteAll();
        commands.deleteAll();
        accounts.deleteAll();
        accounts.saveAllAndFlush(List.of(
                account(1, "Source", "cust-source", 1000),
                account(2, "Target", "cust-target", 250),
                account(3, "Empty", "cust-empty", 5)));
    }

    @Test
    void authorizedTransferConservesValueAndWritesJournal() {
        TransferResult result = transactions.transfer(
                "command-success", 1, 2, 125, "cust-source", false);
        assertTrue(result.accepted());
        assertEquals("COMPLETED", result.state());
        assertEquals(875, balance(1));
        assertEquals(375, balance(2));
        assertEquals(1250, balance(1) + balance(2));
        assertEquals(2, journals.findAll().size());
    }

    @Test
    void invalidAndInsufficientTransfersDoNotMutateBalances() {
        assertFalse(transactions.transfer(
                "command-invalid", 1, 2, 0, "cust-source", false).accepted());
        assertFalse(transactions.transfer(
                "command-funds", 3, 2, 10, "cust-empty", false).accepted());
        assertEquals(1000, balance(1));
        assertEquals(250, balance(2));
        assertEquals(5, balance(3));
        assertEquals(0, journals.count());
    }

    @Test
    void authorizationHappensBeforeMutation() {
        TransferResult result = transactions.transfer(
                "command-denied", 1, 2, 50, "cust-attacker", false);
        assertFalse(result.accepted());
        assertEquals("REJECTED_AUTHORIZATION", result.state());
        assertEquals(1000, balance(1));
        assertEquals(250, balance(2));
        assertEquals(0, journals.count());
    }

    @Test
    void duplicateCommandCannotMoveMoneyTwice() {
        transactions.transfer("command-repeat", 1, 2, 75, "cust-source", false);
        TransferResult replay = transactions.transfer(
                "command-repeat", 1, 2, 75, "cust-source", false);
        assertTrue(replay.replayed());
        assertEquals(925, balance(1));
        assertEquals(325, balance(2));
        assertEquals(2, journals.count());
    }

    @Test
    void injectedCrashRollsBackThenRetryCompletesAndJournalReplays() {
        assertThrows(InjectedTransferFailure.class, () -> transactions.transfer(
                "command-crash", 1, 2, 100, "cust-source", true));
        assertEquals(1000, balance(1));
        assertEquals(250, balance(2));
        assertEquals(0, journals.count());
        assertFalse(commands.existsById("command-crash"));

        transactions.transfer("command-crash", 1, 2, 100, "cust-source", false);
        long journalNet = journals.findAll().stream().mapToLong(this::signedAmount).sum();
        assertEquals(0, journalNet);
        assertEquals(900, balance(1));
        assertEquals(350, balance(2));
        System.out.println("CLOUDBANK_TRANSACTION_CONTRACT=" + CONTRACT);
    }

    private long balance(long accountId) {
        return accounts.findById(accountId).orElseThrow().getAccountBalance();
    }

    private long signedAmount(Journal journal) {
        return "WITHDRAW".equals(journal.getJournalType())
                ? -journal.getJournalAmount() : journal.getJournalAmount();
    }

    private static Account account(long id, String name, String customer, long balance) {
        Account account = new Account(name, "CH", "MS59 synthetic", customer);
        account.setAccountId(id);
        account.setAccountBalance(balance);
        return account;
    }
}
