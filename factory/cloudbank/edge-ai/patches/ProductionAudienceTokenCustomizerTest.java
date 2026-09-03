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
    void unknownClientFailsToUnassignedAudience() {
        assertAudience("unknown-client", "cloudbank-unassigned");
    }

    private void assertAudience(String clientId, String audience) {
        RegisteredClient client = RegisteredClient.withId(clientId + "-id")
                .clientId(clientId)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .build();
        JwtEncodingContext context = JwtEncodingContext.with(
                        JwsHeader.with(org.springframework.security.oauth2.jose.jws.SignatureAlgorithm.RS256),
                        JwtClaimsSet.builder())
                .registeredClient(client)
                .authorizedScopes(Set.of())
                .tokenType(OAuth2TokenType.ACCESS_TOKEN)
                .build();

        customizer.customize(context);

        assertEquals(List.of(audience), context.getClaims().build().getClaim("aud"));
    }
}
