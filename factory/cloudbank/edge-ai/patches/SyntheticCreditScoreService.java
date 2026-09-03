// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.creditscore.service;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.LocalDate;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class SyntheticCreditScoreService {

    private static final int MINIMUM_SCORE = 500;
    private static final int SCORE_RANGE = 400;

    private final byte[] pepper;
    private final Clock clock;

    @Autowired
    public SyntheticCreditScoreService(
            @Value("${creditscore.synthetic.pepper}") String pepper) {
        this(pepper, Clock.systemUTC());
    }

    public SyntheticCreditScoreService(String pepper, Clock clock) {
        if (pepper == null || pepper.length() < 32) {
            throw new IllegalArgumentException("creditscore synthetic pepper must contain at least 32 characters");
        }
        this.pepper = pepper.getBytes(StandardCharsets.UTF_8);
        this.clock = clock;
    }

    public CreditScoreSnapshot scoreFor(String subject) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("authenticated subject is required");
        }
        LocalDate asOf = LocalDate.now(clock);
        byte[] digest = hmac(subject + "\n" + asOf);
        int value = ByteBuffer.wrap(digest).getInt() & Integer.MAX_VALUE;
        return new CreditScoreSnapshot(MINIMUM_SCORE + value % SCORE_RANGE, asOf, "synthetic-v1");
    }

    private byte[] hmac(String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(pepper, "HmacSHA256"));
            return mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", exception);
        }
    }

    public record CreditScoreSnapshot(int score, LocalDate asOf, String provider) {
    }
}
