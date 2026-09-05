// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.qualification;

import java.time.Instant;
import java.util.Map;

import jakarta.servlet.Filter;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.core.env.MapPropertySource;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockServletContext;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Exercises the real security filter chain; token decoding and business handlers are test doubles. */
public abstract class AbstractKubernetesProbeSecurityTest {
    private AnnotationConfigWebApplicationContext context;
    private MockMvc mvc;


    protected abstract Class<?> securityConfiguration();

    protected abstract String businessPath();

    protected abstract HttpMethod businessMethod();

    protected abstract String requiredScope();

    @BeforeEach
    void configureProbeSecurityContext() {
        context = new AnnotationConfigWebApplicationContext();
        context.setServletContext(new MockServletContext());
        context.getEnvironment().setActiveProfiles("cloudbank-oauth");
        context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("probe-test", Map.of(
                "spring.security.oauth2.resourceserver.jwt.issuer-uri", "https://issuer.example.test",
                "spring.security.oauth2.resourceserver.jwt.jwk-set-uri", "https://issuer.example.test/jwks")));
        context.register(TestWebConfiguration.class, securityConfiguration());
        context.refresh();
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(context.getBean("springSecurityFilterChain", Filter.class)).build();
    }

    @AfterEach
    void closeProbeSecurityContext() {
        if (context != null) {
            context.close();
        }
    }

    @Test
    void kubernetesHealthProbesAllowAnonymousRequests() throws Exception {
        for (String path : new String[] {"/actuator/health", "/actuator/health/liveness",
                "/actuator/health/readiness"}) {
            mvc.perform(get(path)).andExpect(status().isOk());
        }
    }

    @Test
    void businessEndpointStillRequiresAuthentication() throws Exception {
        mvc.perform(businessRequest()).andExpect(status().isUnauthorized());
    }

    @Test
    void businessEndpointStillRequiresItsScope() throws Exception {
        mvc.perform(businessRequest().header("Authorization", "Bearer unrelated.scope"))
                .andExpect(status().isForbidden());
        mvc.perform(businessRequest().header("Authorization", "Bearer " + requiredScope()))
                .andExpect(status().isOk());
    }

    @Test
    void otherActuatorPathsRemainProtected() throws Exception {
        for (String path : new String[] {"/actuator/env", "/actuator/health/private-detail"}) {
            mvc.perform(get(path)).andExpect(status().isUnauthorized());
        }
    }

    private MockHttpServletRequestBuilder businessRequest() {
        return request(businessMethod(), businessPath());
    }

    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    static class TestWebConfiguration {
        @Bean
        @Primary
        JwtDecoder testJwtDecoder() {
            // These tests isolate authorization rules; native OAuth gates verify real JWTs.
            return token -> Jwt.withTokenValue(token).header("alg", "test")
                    .subject("synthetic-probe-caller").claim("scope", token)
                    .issuedAt(Instant.now()).expiresAt(Instant.now().plusSeconds(60)).build();
        }

        @Bean
        ProbeController probeController() {
            return new ProbeController();
        }
    }

    @RestController
    static class ProbeController {
        @RequestMapping({"/actuator/health", "/actuator/health/liveness", "/actuator/health/readiness",
                "/actuator/env", "/actuator/health/private-detail", "/api/v1/transfers",
                "/transfer", "/api/v1/creditscore", "/chat"})
        String response() {
            return "ok";
        }
    }
}
