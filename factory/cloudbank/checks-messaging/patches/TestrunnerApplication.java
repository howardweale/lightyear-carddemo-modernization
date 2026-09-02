// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.testrunner;

import com.example.common.filter.LoggingFilterConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(LoggingFilterConfig.class)
public class TestrunnerApplication {

    /**
     * Starts the durable check-message producer.
     *
     * @param args application arguments.
     */
    public static void main(String[] args) {
        SpringApplication.run(TestrunnerApplication.class, args);
    }
}
