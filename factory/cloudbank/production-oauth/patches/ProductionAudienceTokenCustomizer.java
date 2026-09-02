// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package oracle.obaas.aznserver.securityconfig;

import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.stereotype.Component;

@Component
@Primary
public class ProductionAudienceTokenCustomizer
        implements OAuth2TokenCustomizer<JwtEncodingContext> {

    private static final String ACCOUNT_AUDIENCE = "cloudbank-account";
    private static final String TRANSFER_AUDIENCE = "cloudbank-transfer";

    /**
     * Binds each access token to the service allowed to consume its scopes.
     */
    @Override
    public void customize(JwtEncodingContext context) {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }
        Set<String> scopes = context.getAuthorizedScopes();
        String clientId = context.getRegisteredClient().getClientId();
        if (scopes.contains("cloudbank.internal")) {
            context.getClaims().audience(List.of(ACCOUNT_AUDIENCE));
        } else if (scopes.contains("cloudbank.transfer") || "scope-denied".equals(clientId)) {
            context.getClaims().audience(List.of(TRANSFER_AUDIENCE));
        } else {
            context.getClaims().audience(List.of("cloudbank-read"));
        }
    }
}
