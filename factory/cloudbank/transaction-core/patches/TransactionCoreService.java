// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts.services;

import java.util.Optional;

import com.example.accounts.model.Account;
import com.example.accounts.model.Journal;
import com.example.accounts.model.TransferCommand;
import com.example.accounts.repository.AccountRepository;
import com.example.accounts.repository.JournalRepository;
import com.example.accounts.repository.TransferCommandRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionCoreService {

    private final AccountRepository accounts;
    private final JournalRepository journals;
    private final TransferCommandRepository commands;

    /**
     * Creates the service with repositories participating in the local transaction.
     */
    public TransactionCoreService(AccountRepository accounts, JournalRepository journals,
            TransferCommandRepository commands) {
        this.accounts = accounts;
        this.journals = journals;
        this.commands = commands;
    }

    /**
     * Moves value atomically and records its durable idempotency and journal evidence.
     */
    @Transactional
    public TransferResult transfer(String commandId, long sourceId, long targetId,
            long amount, String actor, boolean injectFailureAfterDebit) {
        Optional<TransferCommand> replay = commands.findById(commandId);
        if (replay.isPresent()) {
            return result(replay.get(), true);
        }
        if (amount <= 0 || sourceId == targetId) {
            return new TransferResult(commandId, "REJECTED_INVALID", false, false);
        }

        long firstId = Math.min(sourceId, targetId);
        long secondId = Math.max(sourceId, targetId);
        Account first = accounts.findLockedByAccountId(firstId)
                .orElseThrow(() -> new IllegalArgumentException("account not found"));
        Account second = accounts.findLockedByAccountId(secondId)
                .orElseThrow(() -> new IllegalArgumentException("account not found"));
        Account source = sourceId == firstId ? first : second;
        Account target = targetId == firstId ? first : second;

        if (actor == null || !actor.equals(source.getAccountCustomerId())) {
            return new TransferResult(commandId, "REJECTED_AUTHORIZATION", false, false);
        }
        if (source.getAccountBalance() < amount) {
            return new TransferResult(commandId, "REJECTED_FUNDS", false, false);
        }

        TransferCommand command = new TransferCommand(
                commandId, sourceId, targetId, amount, "STARTED", actor);
        commands.save(command);
        source.setAccountBalance(source.getAccountBalance() - amount);
        accounts.save(source);
        journals.save(new Journal("WITHDRAW", sourceId, amount, commandId, "COMPLETED"));
        if (injectFailureAfterDebit) {
            throw new InjectedTransferFailure();
        }
        target.setAccountBalance(target.getAccountBalance() + amount);
        accounts.save(target);
        journals.save(new Journal("DEPOSIT", targetId, amount, commandId, "COMPLETED"));
        command.setState("COMPLETED");
        commands.save(command);
        return result(command, false);
    }

    private static TransferResult result(TransferCommand command, boolean replayed) {
        return new TransferResult(command.getCommandId(), command.getState(), true, replayed);
    }

    public record TransferResult(String commandId, String state, boolean accepted, boolean replayed) {
    }

    public static final class InjectedTransferFailure extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }
}
