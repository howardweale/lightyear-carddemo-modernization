package com.example.transfer;

import java.net.URI;
import java.util.Map;

import com.example.common.security.CloudBankServiceTokenProvider;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

/** Runs the copied production TransferService with a local synthetic upstream. */
@SpringBootApplication
@RestController
public class FramingApplication {
    private final RestTemplate client;

    public FramingApplication(RestTemplateBuilder builder) {
        this.client = builder.build();
    }

    @Value("${account.transaction.url}")
    private URI upstream;

    public static void main(String[] args) {
        SpringApplication.run(FramingApplication.class, args);
    }

    @Bean
    CloudBankServiceTokenProvider tokens() {
        return new CloudBankServiceTokenProvider();
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.csrf(c -> c.disable())
                .authorizeHttpRequests(a -> a.anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults()).build();
    }

    @Bean
    InMemoryUserDetailsManager users() {
        return new InMemoryUserDetailsManager(User.withUsername("test-owner")
                .password("{noop}synthetic-password").roles("USER").build());
    }

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    @PostMapping("/upstream")
    public ResponseEntity<Map<String, Object>> upstream(
            @RequestParam(value = "amount", defaultValue = "1") long amount,
            HttpServletResponse response) {
        // Jackson streams this JSON through Tomcat using chunked framing.
        response.setHeader("Connection", "X-Upstream-Hop");
        response.setHeader("X-Upstream-Hop", "upstream-only");
        response.setHeader("Set-Cookie", "upstream-only=value");
        return ResponseEntity.status(amount == 13 ? 409 : 200).body(
                Map.of("accepted", amount != 13, "message", "Transfer café"));
    }

    @PostMapping("/legacy-transfer")
    public ResponseEntity<String> legacy() {
        // Negative control: the former response passthrough, with the same
        // Spring client and server as the actual production controller.
        return client.postForEntity(upstream, "", String.class);
    }
}
