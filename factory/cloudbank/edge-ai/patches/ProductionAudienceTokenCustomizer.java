// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package oracle.obaas.aznserver.securityconfig;

import java.util.List;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.stereotype.Component;

@Component
@Primary
public class ProductionAudienceTokenCustomizer
        implements OAuth2TokenCustomizer<JwtEncodingContext> {

    private final String creditScoreClientId;
    private final String chatbotClientId;

    public ProductionAudienceTokenCustomizer(
            @Value("${azn.authorization-server.test-client.id}") String creditScoreClientId,
            @Value("${azn.authorization-server.admin-client.id}") String chatbotClientId) {
        this.creditScoreClientId = creditScoreClientId;
        this.chatbotClientId = chatbotClientId;
    }

    @Override
    public void customize(JwtEncodingContext context) {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }
        Set<String> scopes = context.getAuthorizedScopes();
        String clientId = context.getRegisteredClient().getClientId();
        if (creditScoreClientId.equals(clientId)) {
            context.getClaims().audience(List.of("cloudbank-creditscore"));
        } else if (chatbotClientId.equals(clientId)) {
            context.getClaims().audience(List.of("cloudbank-chatbot"));
        } else if (scopes.contains("cloudbank.internal")) {
            context.getClaims().audience(List.of("cloudbank-account"));
        } else if (scopes.contains("cloudbank.transfer")) {
            context.getClaims().audience(List.of("cloudbank-transfer"));
        } else {
            context.getClaims().audience(List.of("cloudbank-unassigned"));
        }
    }
}
