// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.creditscore.controller;

import java.util.LinkedHashMap;
import java.util.Map;

import com.example.creditscore.service.SyntheticCreditScoreService;
import com.example.creditscore.service.SyntheticCreditScoreService.CreditScoreSnapshot;
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class CreditScoreController {

    private final SyntheticCreditScoreService service;

    public CreditScoreController(SyntheticCreditScoreService service) {
        this.service = service;
    }

    /**
     * Returns the synthetic credit score for the authenticated token subject.
     *
     * @param jwt the authenticated resource-server token
     * @return the legacy-compatible credit-score response
     */
    @GetMapping("/creditscore")
    @Operation(summary = "Get an authenticated synthetic credit score")
    public Map<String, String> getCreditScore(@AuthenticationPrincipal Jwt jwt) {
        CreditScoreSnapshot snapshot = service.scoreFor(jwt == null ? null : jwt.getSubject());
        Map<String, String> result = new LinkedHashMap<>();
        result.put("Credit Score", String.valueOf(snapshot.score()));
        result.put("Date", snapshot.asOf().toString());
        result.put("Provider", snapshot.provider());
        return result;
    }
}
