// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks.messaging;

import com.example.checks.service.AccountService;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class CheckMessageWorker {

    private final DurableCheckQueue queue;
    private final AccountService accountService;

    public CheckMessageWorker(DurableCheckQueue queue, AccountService accountService) {
        this.queue = queue;
        this.accountService = accountService;
    }

    /** Processes at most one message per scheduling tick. */
    @Scheduled(fixedDelayString = "${cloudbank.checks.poll-delay-ms:100}")
    public void processOne() {
        DurableCheckMessage message = queue.claim();
        if (message == null) {
            return;
        }
        try {
            if ("DEPOSIT".equals(message.messageType())) {
                accountService.journal(message.messageId(), message.accountId(), message.amount());
            } else {
                accountService.clear(message.messageId(), message.journalId());
            }
            queue.acknowledge(message.messageId());
        } catch (RuntimeException exception) {
            queue.reject(message, exception.getClass().getSimpleName());
        }
    }
}
