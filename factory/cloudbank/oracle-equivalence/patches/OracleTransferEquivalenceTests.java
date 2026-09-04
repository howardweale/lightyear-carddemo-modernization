// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer;

import java.net.URI;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class OracleTransferEquivalenceTests {

    private TransferService service;
    private MockRestServiceServer server;

    @BeforeEach
    void createService() {
        AtomicReference<RestTemplate> captured = new AtomicReference<>();
        RestTemplateBuilder builder = new RestTemplateBuilder().customizers(captured::set);
        service = new TransferService(builder);
        service.accountLookupUri = URI.create("http://account/api/v1/accounts");
        service.withdrawUri = URI.create("http://account/withdraw");
        service.depositUri = URI.create("http://account/deposit");
        service.transferConfirmUri = URI.create("http://transfer/confirm");
        server = MockRestServiceServer.bindTo(captured.get()).build();
    }

    @Test
    void invalidAmountReturnsBadRequestBeforeCallingDependencies() {
        assertEquals(HttpStatus.BAD_REQUEST, service.transfer(
                1, 2, 0, "oracle-invalid", authenticated()).getStatusCode());
        server.verify();
    }

    @Test
    void missingAuthenticationIsRejectedBeforeCallingDependencies() {
        assertEquals(HttpStatus.FORBIDDEN, service.transfer(
                1, 2, 10, "oracle-auth", null).getStatusCode());
        server.verify();
    }

    @Test
    void successfulRequestOrchestratesLookupWithdrawDepositAndConfirm() {
        server.expect(once(), requestTo("http://account/api/v1/accounts/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"accountCustomerId\":\"cust-source\"}",
                        MediaType.APPLICATION_JSON));
        server.expect(once(), requestTo("http://account/withdraw?accountId=1&amount=25"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withSuccess("withdraw succeeded", null));
        server.expect(once(), requestTo("http://account/deposit?accountId=2&amount=25"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withSuccess("deposit succeeded", null));
        server.expect(once(), requestTo("http://transfer/confirm"))
                .andExpect(method(HttpMethod.POST))
                .andRespond(withSuccess("confirmed", null));

        assertEquals(HttpStatus.OK, service.transfer(
                1, 2, 25, "oracle-success", authenticated()).getStatusCode());
        server.verify();
    }

    private TestingAuthenticationToken authenticated() {
        return new TestingAuthenticationToken("cust-source", "synthetic");
    }
}
