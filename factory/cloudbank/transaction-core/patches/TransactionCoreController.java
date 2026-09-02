package com.example.accounts.controller;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import com.example.accounts.services.TransactionCoreService;
import com.example.accounts.services.TransactionCoreService.TransferResult;
import org.springframework.beans.factory.annotation.Value;
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
    private final String internalToken;

    public TransactionCoreController(TransactionCoreService transactions,
            @Value("${cloudbank.transaction.internal-token}") String internalToken) {
        this.transactions = transactions;
        this.internalToken = internalToken;
    }

    @PostMapping
    public ResponseEntity<TransferResult> transfer(
            @RequestHeader("Idempotency-Key") String commandId,
            @RequestHeader("X-CloudBank-Actor") String actor,
            @RequestHeader("X-CloudBank-Internal-Token") String suppliedToken,
            @RequestParam("fromAccount") long sourceId,
            @RequestParam("toAccount") long targetId,
            @RequestParam("amount") long amount) {
        if (!tokenMatches(suppliedToken)) {
            return new ResponseEntity<>(HttpStatus.FORBIDDEN);
        }
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

    private boolean tokenMatches(String suppliedToken) {
        if (internalToken.isBlank() || suppliedToken == null) {
            return false;
        }
        return MessageDigest.isEqual(
                internalToken.getBytes(StandardCharsets.UTF_8),
                suppliedToken.getBytes(StandardCharsets.UTF_8));
    }
}
