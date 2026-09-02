// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class TransferServiceTests {

    @Test
    void facadeForwardsActorTokenAndIdempotencyKeyOnce() {
        RestTemplate client = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(client).build();
        URI endpoint = URI.create("http://account.test/api/v1/transfers");
        server.expect(requestTo(
                "http://account.test/api/v1/transfers?fromAccount=1&toAccount=2&amount=50"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("Idempotency-Key", "command-facade"))
                .andExpect(header("X-CloudBank-Actor", "cust-source"))
                .andExpect(header("X-CloudBank-Internal-Token", "synthetic-token"))
                .andRespond(withSuccess("{\"state\":\"COMPLETED\"}", MediaType.APPLICATION_JSON));
        TransferService service = new TransferService(client, endpoint, "synthetic-token");

        ResponseEntity<String> response = service.transfer(
                1, 2, 50, "command-facade",
                new UsernamePasswordAuthenticationToken("cust-source", "n/a", List.of()));

        assertEquals(HttpStatus.OK, response.getStatusCode());
        server.verify();
    }

    @Test
    void unauthenticatedAndInvalidRequestsStopBeforeAccountCall() {
        TransferService service = new TransferService(
                new RestTemplate(), URI.create("http://account.test/api/v1/transfers"), "token");
        assertEquals(HttpStatus.BAD_REQUEST, service.transfer(1, 2, 0, null, null).getStatusCode());
        assertEquals(HttpStatus.FORBIDDEN, service.transfer(1, 2, 1, null, null).getStatusCode());
    }
}
