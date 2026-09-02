// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.provisioning.UserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@Profile("cloudbank-wave")
public class TransferWaveSecurityConfiguration {

    /**
     * Requires authenticated callers at the live Transfer HTTP boundary.
     */
    @Bean
    public SecurityFilterChain transferWaveSecurityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health", "/error", "/error/**").permitAll()
                        .requestMatchers(HttpMethod.POST, "/transfer").authenticated()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    /**
     * Creates synthetic users whose password remains in the operator process environment.
     */
    @Bean
    public UserDetailsManager transferWaveUsers(
            @Value("${cloudbank.wave.user-password}") String password) {
        UserDetails source = user("cust-source", password);
        UserDetails target = user("cust-target", password);
        UserDetails empty = user("cust-empty", password);
        UserDetails attacker = user("cust-attacker", password);
        return new InMemoryUserDetailsManager(source, target, empty, attacker);
    }

    private static UserDetails user(String name, String password) {
        return User.withUsername(name)
                .password("{noop}" + password)
                .authorities("SCOPE_cloudbank.transfer")
                .build();
    }
}
