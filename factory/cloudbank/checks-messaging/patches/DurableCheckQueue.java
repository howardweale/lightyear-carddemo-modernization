// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks.messaging;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class DurableCheckQueue {

    private static final int MAX_ATTEMPTS = 3;
    private final JdbcTemplate jdbc;

    public DurableCheckQueue(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** Claims the oldest available message while preserving per-aggregate order. */
    @Transactional
    public DurableCheckMessage claim() {
        List<DurableCheckMessage> rows = jdbc.query("""
                SELECT message_id, message_type, aggregate_id, account_id,
                       journal_id, amount, attempts
                  FROM check_messages candidate
                 WHERE (state = 'READY'
                        OR (state = 'PROCESSING' AND lease_until < CURRENT_TIMESTAMP))
                   AND available_at <= CURRENT_TIMESTAMP
                   AND NOT EXISTS (
                       SELECT 1 FROM check_messages earlier
                        WHERE earlier.aggregate_id = candidate.aggregate_id
                          AND earlier.state IN ('READY', 'PROCESSING')
                          AND (earlier.created_at, earlier.message_id)
                              < (candidate.created_at, candidate.message_id))
                 ORDER BY created_at, message_id
                 FOR UPDATE SKIP LOCKED
                 LIMIT 1
                """, this::map);
        if (rows.isEmpty()) {
            return null;
        }
        DurableCheckMessage message = rows.getFirst();
        jdbc.update("""
                UPDATE check_messages
                   SET state = 'PROCESSING', attempts = attempts + 1,
                       lease_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds'
                 WHERE message_id = ?
                """, message.messageId());
        return new DurableCheckMessage(message.messageId(), message.messageType(),
                message.aggregateId(), message.accountId(), message.journalId(),
                message.amount(), message.attempts() + 1);
    }

    /** Marks a delivered message terminally processed. */
    public void acknowledge(String messageId) {
        jdbc.update("""
                UPDATE check_messages SET state = 'PROCESSED', processed_at = CURRENT_TIMESTAMP,
                    lease_until = NULL, last_error_code = NULL WHERE message_id = ?
                """, messageId);
    }

    /** Schedules bounded redelivery or moves a poison message to the dead-letter state. */
    public void reject(DurableCheckMessage message, String errorCode) {
        if (message.attempts() >= MAX_ATTEMPTS) {
            jdbc.update("""
                    UPDATE check_messages SET state = 'DEAD', lease_until = NULL,
                        last_error_code = ? WHERE message_id = ?
                    """, errorCode, message.messageId());
        } else {
            jdbc.update("""
                    UPDATE check_messages SET state = 'READY', lease_until = NULL,
                        available_at = CURRENT_TIMESTAMP + (? * INTERVAL '1 second'),
                        last_error_code = ? WHERE message_id = ?
                    """, message.attempts(), errorCode, message.messageId());
        }
    }

    private DurableCheckMessage map(ResultSet row, int number) throws SQLException {
        return new DurableCheckMessage(row.getString("message_id"),
                row.getString("message_type"), row.getLong("aggregate_id"),
                nullableLong(row, "account_id"), nullableLong(row, "journal_id"),
                nullableLong(row, "amount"), row.getInt("attempts"));
    }

    private Long nullableLong(ResultSet row, String column) throws SQLException {
        long value = row.getLong(column);
        return row.wasNull() ? null : value;
    }
}
