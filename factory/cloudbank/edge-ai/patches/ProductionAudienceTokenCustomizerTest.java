// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package oracle.obaas.aznserver.securityconfig;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProductionAudienceTokenCustomizerTest {

    private static final String CREDIT_CLIENT = "credit-client";
    private static final String CHAT_CLIENT = "chat-client";
    private final ProductionAudienceTokenCustomizer customizer =
            new ProductionAudienceTokenCustomizer(CREDIT_CLIENT, CHAT_CLIENT);

    @Test
    void creditClientReceivesOnlyCreditScoreAudience() {
        assertAudience(CREDIT_CLIENT, "cloudbank-creditscore");
    }

    @Test
    void chatClientReceivesOnlyChatbotAudience() {
        assertAudience(CHAT_CLIENT, "cloudbank-chatbot");
    }

    @Test
    void scopeDerivedAudiencesRemainLeastPrivileged() {
        assertAudiences(
                "owner-client",
                Set.of("cloudbank.read", "cloudbank.write", "cloudbank.transfer"),
                List.of("cloudbank-account", "cloudbank-transfer"));
        assertAudiences(
                "service-client",
                Set.of("cloudbank.internal", "cloudbank.test"),
                List.of("cloudbank-account"));
        assertAudiences(
                "transfer-client",
                Set.of("cloudbank.transfer"),
                List.of("cloudbank-transfer"));
        assertAudiences("unknown-client", Set.of(), List.of("cloudbank-unassigned"));
    }

    private void assertAudience(String clientId, String audience) {
        assertAudiences(clientId, Set.of(), List.of(audience));
    }

    private void assertAudiences(String clientId, Set<String> scopes, List<String> audiences) {
        RegisteredClient client = RegisteredClient.withId(clientId + "-id")
                .clientId(clientId)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .build();
        JwtEncodingContext context = JwtEncodingContext.with(
                        JwsHeader.with(org.springframework.security.oauth2.jose.jws.SignatureAlgorithm.RS256),
                        JwtClaimsSet.builder())
                .registeredClient(client)
                .authorizedScopes(scopes)
                .tokenType(OAuth2TokenType.ACCESS_TOKEN)
                .build();

        customizer.customize(context);

        assertEquals(audiences, context.getClaims().build().getClaim("aud"));
    }
}
