// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer;

import java.net.URI;
import java.util.List;

import com.example.common.security.CloudBankServiceTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class TransferServiceTests {

    @Test
    void oauthContextStartsWithTheRealServiceTokenProvider() {
        oauthContext().run(context -> {
            assertThat(context).hasNotFailed()
                    .hasSingleBean(CloudBankServiceTokenProvider.class)
                    .hasSingleBean(TransferService.class);
            assertThat(context.getEnvironment().getProperty(
                    "cloudbank.security.service-token.enabled", Boolean.class)).isTrue();
        });
    }

    @Test
    void explicitlyDisabledServiceTokenProviderFailsStartup() {
        oauthContext()
                .withPropertyValues("CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED=false")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class)
                            .hasStackTraceContaining("CloudBankServiceTokenProvider");
                });
    }

    private static WebApplicationContextRunner oauthContext() {
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(TransferApplication.class)
                .withPropertyValues(
                        "spring.profiles.active=cloudbank-oauth",
                        "spring.cloud.config.enabled=false",
                        "spring.cloud.discovery.enabled=false",
                        "eureka.client.enabled=false",
                        "CLOUDBANK_SECURITY_ISSUER_URI=http://127.0.0.1:1",
                        "CLOUDBANK_SECURITY_JWK_SET_URI=http://127.0.0.1:1/oauth2/jwks",
                        "CLOUDBANK_SECURITY_SERVICE_TOKEN_URI=http://127.0.0.1:1/oauth2/token",
                        "CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_ID=cloudbank-transfer-service",
                        "CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_SECRET=ci-synthetic-secret");
    }

    @Test
    void exchangesServiceCredentialsAndKeepsCallerIdentitySeparate() {
        RestTemplate client = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(client).build();
        CloudBankServiceTokenProvider tokenProvider = mock(CloudBankServiceTokenProvider.class);
        when(tokenProvider.getAuthorizationHeader()).thenReturn("Bearer service-jwt");
        server.expect(once(), requestTo(
                "http://account.test/api/v1/transfers?fromAccount=1&toAccount=2&amount=50"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("Authorization", "Bearer service-jwt"))
                .andExpect(header("Idempotency-Key", "command-oauth"))
                .andExpect(header("X-CloudBank-Actor", "cust-source"))
                .andRespond(withSuccess("{\"accepted\":true}", MediaType.APPLICATION_JSON));
        TransferService service = service(client, tokenProvider);

        ResponseEntity<String> response = service.transfer(
                1, 2, 50, "command-oauth",
                new UsernamePasswordAuthenticationToken("cust-source", "n/a", List.of()));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        verify(tokenProvider).getAuthorizationHeader();
        server.verify();
    }

    @Test
    void unauthenticatedAndInvalidRequestsStopBeforeTokenExchange() {
        RestTemplate client = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(client).build();
        CloudBankServiceTokenProvider tokenProvider = mock(CloudBankServiceTokenProvider.class);
        TransferService service = service(client, tokenProvider);

        assertEquals(HttpStatus.BAD_REQUEST,
                service.transfer(1, 2, 0, null, null).getStatusCode());
        assertEquals(HttpStatus.FORBIDDEN,
                service.transfer(1, 2, 1, null, null).getStatusCode());
        verify(tokenProvider, never()).getAuthorizationHeader();
        server.verify();
    }

    private static TransferService service(RestTemplate client,
            CloudBankServiceTokenProvider tokenProvider) {
        return new TransferService(
                client,
                URI.create("http://account.test/api/v1/transfers"),
                tokenProvider);
    }
}
