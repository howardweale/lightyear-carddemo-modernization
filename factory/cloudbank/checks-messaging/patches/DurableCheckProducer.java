// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.testrunner.messaging;

import com.example.testrunner.model.CheckDeposit;
import com.example.testrunner.model.Clearance;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class DurableCheckProducer {

    private final JdbcTemplate jdbc;

    public DurableCheckProducer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** Enqueues a deposit exactly once for the supplied idempotency key. */
    @Transactional
    public boolean deposit(String messageId, CheckDeposit deposit) {
        if (deposit.getAccountId() <= 0 || deposit.getAmount() <= 0) {
            throw new IllegalArgumentException("account and amount must be positive");
        }
        return jdbc.update("""
                INSERT INTO check_messages
                    (message_id, message_type, aggregate_id, account_id, amount)
                VALUES (?, 'DEPOSIT', ?, ?, ?)
                ON CONFLICT (message_id) DO NOTHING
                """, messageId, deposit.getAccountId(), deposit.getAccountId(),
                deposit.getAmount()) == 1;
    }

    /** Enqueues a clearance exactly once for the supplied idempotency key. */
    @Transactional
    public boolean clearance(String messageId, Clearance clearance) {
        if (clearance.getJournalId() <= 0) {
            throw new IllegalArgumentException("journal must be positive");
        }
        return jdbc.update("""
                INSERT INTO check_messages
                    (message_id, message_type, aggregate_id, journal_id)
                VALUES (?, 'CLEARANCE', ?, ?)
                ON CONFLICT (message_id) DO NOTHING
                """, messageId, clearance.getJournalId(), clearance.getJournalId()) == 1;
    }
}
