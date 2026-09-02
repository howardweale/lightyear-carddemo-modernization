// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.testrunner.controller;

import com.example.testrunner.messaging.DurableCheckProducer;
import com.example.testrunner.model.CheckDeposit;
import com.example.testrunner.model.Clearance;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/testrunner")
public class TestRunnerController {

    private final DurableCheckProducer producer;

    public TestRunnerController(DurableCheckProducer producer) {
        this.producer = producer;
    }

    /** Enqueues a check deposit using the caller's required idempotency key. */
    @PostMapping("/deposit")
    public ResponseEntity<CheckDeposit> depositCheck(
            @RequestHeader("Idempotency-Key") String messageId,
            @RequestBody CheckDeposit deposit) {
        boolean created = producer.deposit(messageId, deposit);
        return new ResponseEntity<>(deposit, created ? HttpStatus.CREATED : HttpStatus.OK);
    }

    /** Enqueues a clearance using the caller's required idempotency key. */
    @PostMapping("/clear")
    public ResponseEntity<Clearance> clearCheck(
            @RequestHeader("Idempotency-Key") String messageId,
            @RequestBody Clearance clearance) {
        boolean created = producer.clearance(messageId, clearance);
        return new ResponseEntity<>(clearance, created ? HttpStatus.CREATED : HttpStatus.OK);
    }
}
