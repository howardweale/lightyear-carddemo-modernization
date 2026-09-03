// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.chatbot.config;

import java.net.URI;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ChatbotEndpointPolicy {

    /**
     * Validates that the configured model endpoint is allowlisted and transport-safe.
     *
     * @param baseUrl the configured model endpoint
     * @param allowedHosts the comma-separated model-host allowlist
     */
    public ChatbotEndpointPolicy(
            @Value("${spring.ai.ollama.base-url}") String baseUrl,
            @Value("${chatbot.security.allowed-model-hosts}") String allowedHosts) {
        URI endpoint = URI.create(baseUrl);
        String host = endpoint.getHost();
        Set<String> allowed = Arrays.stream(allowedHosts.split(","))
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .collect(Collectors.toUnmodifiableSet());
        if (host == null || !allowed.contains(host)) {
            throw new IllegalArgumentException("chat model endpoint host is not allowlisted");
        }
        boolean loopback = "localhost".equals(host) || "127.0.0.1".equals(host) || "::1".equals(host);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                && !(loopback && "http".equalsIgnoreCase(endpoint.getScheme()))) {
            throw new IllegalArgumentException("chat model endpoint must use HTTPS except on loopback");
        }
        if (endpoint.getUserInfo() != null || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("chat model endpoint must not embed credentials or parameters");
        }
    }
}
