// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.creditscore;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;

import com.example.creditscore.config.CreditScoreOAuthSecurityConfiguration;
import com.example.creditscore.controller.CreditScoreController;
import com.example.creditscore.service.SyntheticCreditScoreService;
import com.example.qualification.AbstractKubernetesProbeSecurityTest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CreditscoreApplicationTests extends AbstractKubernetesProbeSecurityTest {

    @Override
    protected Class<?> securityConfiguration() {
        return CreditScoreOAuthSecurityConfiguration.class;
    }

    @Override
    protected String businessPath() {
        return "/api/v1/creditscore";
    }

    @Override
    protected HttpMethod businessMethod() {
        return HttpMethod.GET;
    }

    @Override
    protected String requiredScope() {
        return "cloudbank.read";
    }


    private static final String PEPPER = "unit-test-pepper-with-at-least-32-characters";
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-09-03T00:00:00Z"), ZoneOffset.UTC);

    @Test
    void scoreIsStableForSubjectAndUtcDate() {
        SyntheticCreditScoreService service = new SyntheticCreditScoreService(PEPPER, CLOCK);
        assertEquals(service.scoreFor("alice"), service.scoreFor("alice"));
        assertEquals("2026-09-03", service.scoreFor("alice").asOf().toString());
    }

    @Test
    void scoreIsSubjectBoundAndInsideDeclaredRange() {
        SyntheticCreditScoreService service = new SyntheticCreditScoreService(PEPPER, CLOCK);
        int alice = service.scoreFor("alice").score();
        int bob = service.scoreFor("bob").score();
        assertNotEquals(alice, bob);
        assertTrue(alice >= 500 && alice <= 899);
        assertTrue(bob >= 500 && bob <= 899);
    }

    @Test
    void controllerReturnsOnlyScoreDateAndSyntheticProvenance() {
        CreditScoreController controller = new CreditScoreController(
                new SyntheticCreditScoreService(PEPPER, CLOCK));
        Jwt jwt = Jwt.withTokenValue("test").header("alg", "none").subject("alice").build();
        Map<String, String> response = controller.getCreditScore(jwt);
        assertEquals(3, response.size());
        assertEquals("synthetic-v1", response.get("Provider"));
    }

    @Test
    void missingIdentityAndWeakPepperFailClosed() {
        assertThrows(IllegalArgumentException.class,
                () -> new SyntheticCreditScoreService("short", CLOCK));
        SyntheticCreditScoreService service = new SyntheticCreditScoreService(PEPPER, CLOCK);
        assertThrows(IllegalArgumentException.class, () -> service.scoreFor(" "));
    }
}
