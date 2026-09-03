// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.testrunner;

import com.example.testrunner.controller.TestRunnerController;
import com.example.testrunner.messaging.DurableCheckProducer;
import com.example.testrunner.model.CheckDeposit;
import com.example.testrunner.model.Clearance;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TestrunnerTargetWorkcellTest {

    @Mock
    private DurableCheckProducer producer;
    private TestRunnerController controller;

    @BeforeEach
    void setUp() {
        controller = new TestRunnerController(producer);
    }

    @Test
    void newDepositReturnsCreated() {
        CheckDeposit deposit = new CheckDeposit(7, 25);
        when(producer.deposit("deposit-1", deposit)).thenReturn(true);
        assertEquals(HttpStatus.CREATED,
                controller.depositCheck("deposit-1", deposit).getStatusCode());
    }

    @Test
    void duplicateDepositReturnsIdempotentOk() {
        CheckDeposit deposit = new CheckDeposit(7, 25);
        when(producer.deposit("deposit-1", deposit)).thenReturn(false);
        assertEquals(HttpStatus.OK,
                controller.depositCheck("deposit-1", deposit).getStatusCode());
    }

    @Test
    void newClearanceReturnsCreated() {
        Clearance clearance = new Clearance(19);
        when(producer.clearance("clear-1", clearance)).thenReturn(true);
        assertEquals(HttpStatus.CREATED,
                controller.clearCheck("clear-1", clearance).getStatusCode());
    }

    @Test
    void duplicateClearanceReturnsIdempotentOk() {
        Clearance clearance = new Clearance(19);
        when(producer.clearance("clear-1", clearance)).thenReturn(false);
        assertEquals(HttpStatus.OK,
                controller.clearCheck("clear-1", clearance).getStatusCode());
    }
}
