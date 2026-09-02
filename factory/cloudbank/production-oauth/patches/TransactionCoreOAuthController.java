// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts.controller;

import com.example.accounts.services.TransactionCoreService;
import com.example.accounts.services.TransactionCoreService.TransferResult;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/transfers")
public class TransactionCoreController {

    private final TransactionCoreService transactions;

    public TransactionCoreController(TransactionCoreService transactions) {
        this.transactions = transactions;
    }

    /**
     * Applies one OAuth-authenticated and idempotent account transfer.
     */
    @PostMapping
    public ResponseEntity<TransferResult> transfer(
            @RequestHeader("Idempotency-Key") String commandId,
            @RequestHeader("X-CloudBank-Actor") String actor,
            @RequestParam("fromAccount") long sourceId,
            @RequestParam("toAccount") long targetId,
            @RequestParam("amount") long amount) {
        try {
            TransferResult result = transactions.transfer(
                    commandId, sourceId, targetId, amount, actor, false);
            if (!result.accepted()) {
                return ResponseEntity.badRequest().body(result);
            }
            return ResponseEntity.ok(result);
        } catch (IllegalArgumentException exception) {
            return new ResponseEntity<>(HttpStatus.NOT_FOUND);
        }
    }
}
