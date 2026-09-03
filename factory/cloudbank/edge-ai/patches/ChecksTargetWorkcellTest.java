// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks;

import com.example.checks.messaging.CheckMessageWorker;
import com.example.checks.messaging.DurableCheckMessage;
import com.example.checks.messaging.DurableCheckQueue;
import com.example.checks.service.AccountService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ChecksTargetWorkcellTest {

    @Mock
    private DurableCheckQueue queue;
    @Mock
    private AccountService accountService;

    @Test
    void emptyQueueDoesNotCallAccount() {
        new CheckMessageWorker(queue, accountService).processOne();
        verify(queue).claim();
        verifyNoInteractions(accountService);
    }

    @Test
    void depositIsDeliveredAndAcknowledged() {
        DurableCheckMessage message = message("deposit-1", "DEPOSIT", 7L, null, 25L, 1);
        when(queue.claim()).thenReturn(message);

        new CheckMessageWorker(queue, accountService).processOne();

        verify(accountService).journal("deposit-1", 7L, 25L);
        verify(queue).acknowledge("deposit-1");
    }

    @Test
    void clearanceIsDeliveredAndAcknowledged() {
        DurableCheckMessage message = message("clear-1", "CLEARANCE", null, 19L, null, 1);
        when(queue.claim()).thenReturn(message);

        new CheckMessageWorker(queue, accountService).processOne();

        verify(accountService).clear("clear-1", 19L);
        verify(queue).acknowledge("clear-1");
    }

    @Test
    void deliveryFailureIsRejectedWithoutAcknowledgement() {
        DurableCheckMessage message = message("deposit-2", "DEPOSIT", 8L, null, 30L, 2);
        when(queue.claim()).thenReturn(message);
        doThrow(new IllegalStateException("controlled failure"))
                .when(accountService).journal("deposit-2", 8L, 30L);

        new CheckMessageWorker(queue, accountService).processOne();

        verify(queue).reject(message, "IllegalStateException");
        verify(queue, never()).acknowledge(message.messageId());
    }

    private static DurableCheckMessage message(String id, String type, Long accountId,
            Long journalId, Long amount, int attempts) {
        long aggregateId = accountId == null ? journalId : accountId;
        return new DurableCheckMessage(id, type, aggregateId, accountId, journalId, amount, attempts);
    }
}
