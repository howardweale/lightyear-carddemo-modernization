// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.checks;

import com.example.checks.service.AccountService;
import com.example.common.security.CloudBankServiceTokenProvider;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.NoSuchBeanDefinitionException;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.TaskScheduler;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

class ChecksDeploymentContextTests {

    @Test
    void importedDefaultReproducesMissingServiceTokenProvider() {
        checksContext().run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(NoSuchBeanDefinitionException.class)
                    .hasStackTraceContaining("CloudBankServiceTokenProvider");
        });
    }

    @Test
    void explicitDeploymentOverrideStartsWithRealTokenProvider() {
        checksContext()
                .withPropertyValues("CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED=true")
                .run(context -> {
                    assertThat(context).hasNotFailed()
                            .hasSingleBean(CloudBankServiceTokenProvider.class)
                            .hasSingleBean(AccountService.class);
                    assertThat(context.getEnvironment().getProperty(
                            "cloudbank.security.service-token.enabled", Boolean.class)).isTrue();
                });
    }

    private static WebApplicationContextRunner checksContext() {
        // Exercise the actual application/config import and security auto-configuration.
        // Isolate database I/O and scheduling; token-provider wiring remains real.
        return new WebApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(ChecksApplication.class)
                .withBean(JdbcTemplate.class, () -> mock(JdbcTemplate.class))
                .withBean(TaskScheduler.class, () -> mock(TaskScheduler.class))
                .withPropertyValues(
                        "spring.autoconfigure.exclude="
                                + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration",
                        "spring.cloud.config.enabled=false",
                        "spring.cloud.discovery.enabled=false",
                        "eureka.client.enabled=false",
                        "CLOUDBANK_SECURITY_JWK_SET_URI=http://127.0.0.1:1/oauth2/jwks",
                        "CLOUDBANK_SECURITY_SERVICE_TOKEN_URI=http://127.0.0.1:1/oauth2/token",
                        "CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_ID=cloudbank-checks-service",
                        "CLOUDBANK_SECURITY_SERVICE_TOKEN_CLIENT_SECRET=ci-synthetic-secret");
    }
}
