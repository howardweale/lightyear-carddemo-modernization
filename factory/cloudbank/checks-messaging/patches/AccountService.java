// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks.service;

import java.net.URI;

import com.example.checks.clients.Journal;
import com.example.common.security.CloudBankServiceTokenProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Service;
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
        restTemplate.postForEntity(journalUri,
                new HttpEntity<>(new Journal("PENDING", accountId, amount), headers), String.class);
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
