// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks;

import com.example.common.filter.LoggingFilterConfig;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
@Import(LoggingFilterConfig.class)
public class ChecksApplication {

    /**
     * Starts the durable Checks consumer.
     *
     * @param args application arguments.
     */
    public static void main(String[] args) {
        SpringApplication.run(ChecksApplication.class, args);
    }
}
