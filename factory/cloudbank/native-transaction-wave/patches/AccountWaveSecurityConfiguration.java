// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("cloudbank-wave")
public class AccountWaveSecurityConfiguration {

    /**
     * Restricts the Account HTTP surface used by the bounded native wave.
     */
    @Bean
    public SecurityFilterChain accountWaveSecurityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health", "/error", "/error/**").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/v1/transfers").permitAll()
                        .anyRequest().authenticated());
        return http.build();
    }
}
