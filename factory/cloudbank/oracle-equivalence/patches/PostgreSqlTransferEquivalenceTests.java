// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class PostgreSqlTransferEquivalenceTests {

    private TransferService service;
    private MockRestServiceServer server;

    @BeforeEach
    void createService() {
        RestTemplate restTemplate = new RestTemplate();
        server = MockRestServiceServer.bindTo(restTemplate).build();
        service = new TransferService(
                restTemplate, URI.create("http://account/api/v1/transfers"), "internal-ms61");
    }

    @Test
    void invalidAmountReturnsBadRequestBeforeCallingDependencies() {
        assertEquals(HttpStatus.BAD_REQUEST, service.transfer(
                1, 2, 0, "postgres-invalid", authenticated()).getStatusCode());
        server.verify();
    }

    @Test
    void missingAuthenticationIsRejectedBeforeCallingDependencies() {
        assertEquals(HttpStatus.FORBIDDEN, service.transfer(
                1, 2, 10, "postgres-auth", null).getStatusCode());
        server.verify();
    }

    @Test
    void successfulRequestForwardsActorCommandAndInternalToken() {
        server.expect(once(), requestTo(
                "http://account/api/v1/transfers?fromAccount=1&toAccount=2&amount=25"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("Idempotency-Key", "postgres-success"))
                .andExpect(header("X-CloudBank-Actor", "cust-source"))
                .andExpect(header("X-CloudBank-Internal-Token", "internal-ms61"))
                .andRespond(withSuccess("{\"accepted\":true}", null));

        assertEquals(HttpStatus.OK, service.transfer(
                1, 2, 25, "postgres-success", authenticated()).getStatusCode());
        server.verify();
    }

    private TestingAuthenticationToken authenticated() {
        return new TestingAuthenticationToken("cust-source", "synthetic");
    }
}
