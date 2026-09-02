// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts;

import com.example.accounts.model.Account;
import com.example.accounts.model.Journal;
import com.example.accounts.repository.AccountRepository;
import com.example.accounts.repository.JournalRepository;
import com.example.accounts.services.DepositService;
import com.example.accounts.services.WithdrawService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "eureka.client.enabled=false",
        "spring.cloud.discovery.enabled=false",
        "spring.cloud.config.enabled=false",
        "spring.microtx.lra.propagation-active=false"
})
@Transactional
class OracleAccountEquivalenceTests {

    private static final String CONTRACT =
            "account-success:conserved;invalid:no-mutation;funds:no-mutation;"
                    + "failure:restored;transfer-invalid:400;transfer-auth:403;"
                    + "transfer-success:200";

    @Autowired
    private AccountRepository accounts;

    @Autowired
    private JournalRepository journals;

    private final WithdrawService withdraw = new WithdrawService();
    private final DepositService deposit = new DepositService();
    private long sourceId;
    private long targetId;
    private long emptyId;

    @BeforeEach
    void resetSyntheticAccounts() {
        journals.deleteAll();
        accounts.deleteAll();
        sourceId = createAccount("Source", "cust-source", 1000);
        targetId = createAccount("Target", "cust-target", 250);
        emptyId = createAccount("Empty", "cust-empty", 5);
    }

    @Test
    void successfulTransferConservesValueAndFinalizesJournals() throws Exception {
        String lra = "oracle-success";
        assertTrue(withdraw.withdraw(lra, sourceId, 125).getBody().contains("succeeded"));
        assertTrue(deposit.deposit(lra, targetId, 125).getBody().contains("succeeded"));
        deposit.completeWork(lra);
        withdraw.completeWork(lra);

        assertEquals(875, balance(sourceId));
        assertEquals(375, balance(targetId));
        assertEquals(1250, balance(sourceId) + balance(targetId));
        assertEquals(2, journals.count());
        assertEquals(0, journals.findAll().stream().mapToLong(this::signedAmount).sum());
    }

    @Test
    void invalidAmountDoesNotMutateState() {
        assertEquals(HttpStatus.BAD_REQUEST, withdraw.withdraw(
                "oracle-invalid", sourceId, 0).getStatusCode());
        assertEquals(1000, balance(sourceId));
        assertEquals(250, balance(targetId));
        assertEquals(0, journals.count());
    }

    @Test
    void insufficientFundsHaveNoEffectiveMutation() {
        assertTrue(withdraw.withdraw(
                "oracle-funds", emptyId, 10).getBody().contains("failed"));
        assertEquals(5, balance(emptyId));
        assertEquals(0, journals.findAll().stream().mapToLong(Journal::getJournalAmount).sum());
    }

    @Test
    void compensationRestoresTheSourceBalance() throws Exception {
        String lra = "oracle-compensate";
        assertTrue(withdraw.withdraw(lra, sourceId, 100).getBody().contains("succeeded"));
        assertEquals(900, balance(sourceId));
        withdraw.compensateWork(lra);
        assertEquals(1000, balance(sourceId));
        assertEquals("Compensated", journals.findJournalByLraIdAndJournalType(
                lra, WithdrawService.WITHDRAW).getLraState());
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
        return WithdrawService.WITHDRAW.equals(journal.getJournalType())
                ? -journal.getJournalAmount() : journal.getJournalAmount();
    }
}
