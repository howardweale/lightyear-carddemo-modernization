// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks.service;

import java.net.URI;

import com.example.checks.clients.Journal;
import com.example.common.security.CloudBankServiceTokenProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.RestTemplate;

@Service
public class AccountService {

    private final RestTemplate restTemplate = new RestTemplate();
    private final URI journalUri;
    private final CloudBankServiceTokenProvider tokenProvider;

    public AccountService(@Value("${account.journal.url}") URI journalUri,
            CloudBankServiceTokenProvider tokenProvider) {
        this.journalUri = journalUri;
        this.tokenProvider = tokenProvider;
    }

    /** Delivers one idempotently identified pending check journal. */
    public void journal(String messageId, long accountId, long amount) {
        HttpHeaders headers = headers(messageId);
        Journal command = new Journal(0, "PENDING", accountId, messageId, "COMPLETED", amount);
        try {
            restTemplate.postForEntity(journalUri, new HttpEntity<>(command, headers), String.class);
        } catch (HttpServerErrorException failure) {
            // Account may have committed before an HTTP response was lost. Only
            // suppress the retry when the exact message effect is observable.
            URI accountJournalUri = journalUri.resolve("./" + accountId + "/journal");
            ResponseEntity<Journal[]> response = restTemplate.exchange(accountJournalUri,
                    HttpMethod.GET, new HttpEntity<>(headers), Journal[].class);
            Journal[] rows = response.getBody();
            if (rows == null || !java.util.Arrays.stream(rows).anyMatch(row ->
                    messageId.equals(row.getLraId())
                    && "PENDING".equals(row.getJournalType())
                    && row.getAccountId() == accountId
                    && row.getJournalAmount() == amount)) {
                throw failure;
            }
        }
    }

    /** Delivers one idempotently identified check clearance. */
    public void clear(String messageId, long journalId) {
        HttpHeaders headers = headers(messageId);
        restTemplate.postForEntity(URI.create(journalUri + "/" + journalId + "/clear"),
                new HttpEntity<>("", headers), String.class);
    }

    private HttpHeaders headers(String messageId) {
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.AUTHORIZATION, tokenProvider.getAuthorizationHeader());
        headers.set("Idempotency-Key", messageId);
        headers.set("X-CloudBank-Actor", "checks-service");
        return headers;
    }
}
