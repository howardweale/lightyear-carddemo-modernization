// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks.messaging;

/** One normalized durable Checks message. */
public record DurableCheckMessage(
        String messageId,
        String messageType,
        long aggregateId,
        Long accountId,
        Long journalId,
        Long amount,
        int attempts) {
}
