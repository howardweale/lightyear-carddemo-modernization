// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer;

import java.net.URI;
import java.util.UUID;

import com.example.common.security.CloudBankServiceTokenProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
public class TransferService {

    private final RestTemplate restTemplate;
    private final URI transactionUri;
    private final CloudBankServiceTokenProvider serviceTokenProvider;

    /**
     * Creates the OAuth-authenticated HTTP facade.
     */
    @Autowired
    public TransferService(RestTemplateBuilder builder,
            @Value("${account.transaction.url}") URI transactionUri,
            CloudBankServiceTokenProvider serviceTokenProvider) {
        this(builder.build(), transactionUri, serviceTokenProvider);
    }

    TransferService(RestTemplate restTemplate, URI transactionUri,
            CloudBankServiceTokenProvider serviceTokenProvider) {
        this.restTemplate = restTemplate;
        this.transactionUri = transactionUri;
        this.serviceTokenProvider = serviceTokenProvider;
    }

    /**
     * Reports that the transfer facade is reachable to an authorized reader.
     */
    @GetMapping("/hello")
    public ResponseEntity<String> ping() {
        return ResponseEntity.ok("");
    }

    /**
     * Validates and forwards one OAuth-authenticated transfer request.
     */
    @PostMapping("/transfer")
    public ResponseEntity<String> transfer(
            @RequestParam("fromAccount") long fromAccount,
            @RequestParam("toAccount") long toAccount,
            @RequestParam("amount") long amount,
            @RequestHeader(value = "Idempotency-Key", required = false) String suppliedCommandId,
            Authentication authentication) {
        if (amount <= 0) {
            return ResponseEntity.badRequest().body("transfer failed: amount must be positive");
        }
        if (authentication == null || authentication.getName() == null) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body("transfer failed: account access denied");
        }
        String commandId = suppliedCommandId == null || suppliedCommandId.isBlank()
                ? UUID.randomUUID().toString() : suppliedCommandId;
        URI uri = UriComponentsBuilder.fromUri(transactionUri)
                .queryParam("fromAccount", fromAccount)
                .queryParam("toAccount", toAccount)
                .queryParam("amount", amount)
                .build().toUri();
        HttpHeaders headers = new HttpHeaders();
        headers.set("Idempotency-Key", commandId);
        headers.set("X-CloudBank-Actor", authentication.getName());
        headers.set(HttpHeaders.AUTHORIZATION, serviceTokenProvider.getAuthorizationHeader());
        try {
            return restTemplate.postForEntity(uri, new HttpEntity<>("", headers), String.class);
        } catch (HttpStatusCodeException exception) {
            return ResponseEntity.status(exception.getStatusCode())
                    .body(exception.getResponseBodyAsString());
        }
    }
}
