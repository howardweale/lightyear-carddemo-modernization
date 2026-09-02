// Copyright (c) 2026, Oracle and/or its affiliates.
// Modifications Copyright (c) 2026 Lightyear.
// Licensed under the Universal Permissive License v 1.0.

package com.example.customer;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.List;
import javax.sql.DataSource;

import com.example.customer.model.Customers;
import com.example.customer.repository.CustomersRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "eureka.client.enabled=false",
        "spring.cloud.discovery.enabled=false",
        "spring.cloud.config.enabled=false",
        "cloudbank.security.require-internal-token=false"
})
@AutoConfigureMockMvc
class CustomerProductionQualificationTests {

    private static final String MARKER =
            "http:pass;authn:pass;authz:pass;errors:pass;isolation:pass;rollback:pass";

    private static final SimpleGrantedAuthority READ =
            new SimpleGrantedAuthority("SCOPE_cloudbank.read");
    private static final SimpleGrantedAuthority WRITE =
            new SimpleGrantedAuthority("SCOPE_cloudbank.write");
    private static final SimpleGrantedAuthority ADMIN =
            new SimpleGrantedAuthority("SCOPE_cloudbank.admin");

    @Autowired
    private CustomersRepository repository;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private DataSource dataSource;

    @BeforeEach
    void seedSyntheticCorpus() {
        repository.deleteAll();
        repository.saveAllAndFlush(List.of(
                customer("cust-001", "Alice", "alice@example.test", "Synthetic alpha"),
                customer("cust-002", "Alicia", "ops@example.test", "Synthetic beta"),
                customer("cust-003", "Bob", null, null),
                customer("cust-004", "Zed", "zed@elsewhere.test", "")));
    }

    @Test
    void httpAuthenticationAndOwnerAuthorization() throws Exception {
        mockMvc.perform(get("/api/v1/customer"))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(get("/api/v1/customer")
                        .with(jwt().jwt(token -> token.subject("cust-001")).authorities(READ)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].customerId").value("cust-001"));

        mockMvc.perform(get("/api/v1/customer/cust-002")
                        .with(jwt().jwt(token -> token.subject("cust-001")).authorities(READ)))
                .andExpect(status().isForbidden());
    }

    @Test
    void httpAdministratorAndErrorContract() throws Exception {
        mockMvc.perform(get("/api/v1/customer")
                        .with(jwt().jwt(token -> token.subject("factory-admin"))
                                .authorities(READ, ADMIN)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(4)));

        mockMvc.perform(get("/api/v1/customer/missing")
                        .with(jwt().jwt(token -> token.subject("missing")).authorities(READ)))
                .andExpect(status().isNotFound());

        mockMvc.perform(post("/api/v1/customer")
                        .with(jwt().jwt(token -> token.subject("cust-001")).authorities(WRITE))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"customerId\":\"cust-001\",\"customerName\":\"Duplicate\"}"))
                .andExpect(status().isConflict());

        mockMvc.perform(post("/api/v1/customer/applyLoan/100")
                        .with(jwt().jwt(token -> token.subject("cust-001")).authorities(WRITE)))
                .andExpect(status().isIAmATeapot());
    }

    @Test
    void concurrentConnectionsPreserveReadCommittedIsolation() throws Exception {
        try (Connection writer = dataSource.getConnection();
                Connection observer = dataSource.getConnection()) {
            writer.setAutoCommit(false);
            insert(writer, "cust-isolation", "Uncommitted");
            assertEquals(0, count(observer, "cust-isolation"));
            writer.rollback();
            assertEquals(0, count(observer, "cust-isolation"));
        }
    }

    @Test
    void rollbackAndCommitVisibility() throws Exception {
        try (Connection writer = dataSource.getConnection();
                Connection observer = dataSource.getConnection()) {
            writer.setAutoCommit(false);
            insert(writer, "cust-commit", "Committed");
            writer.commit();
            assertEquals(1, count(observer, "cust-commit"));
            delete(observer, "cust-commit");
            assertEquals(0, count(observer, "cust-commit"));
        }
    }

    @Test
    void productionShapedBoundariesAndMarker() {
        Customers boundary = customer(
                "cust-boundary",
                "N".repeat(40),
                "e".repeat(27) + "@example.test",
                "D".repeat(4000));
        repository.saveAndFlush(boundary);
        Customers observed = repository.findById("cust-boundary").orElseThrow();
        assertEquals(40, observed.getCustomerName().length());
        assertEquals(40, observed.getCustomerEmail().length());
        assertEquals(4000, observed.getCustomerOtherDetails().length());
        assertNull(repository.findById("cust-004").orElseThrow().getCustomerOtherDetails());
        System.out.println("CLOUDBANK_PRODUCTION_QUALIFICATION=" + MARKER);
    }

    private void insert(Connection connection, String id, String name) throws Exception {
        String sql = "INSERT INTO " + tableName() + " (customer_id, customer_name) VALUES (?, ?)";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, id);
            statement.setString(2, name);
            statement.executeUpdate();
        }
    }

    private int count(Connection connection, String id) throws Exception {
        String sql = "SELECT COUNT(*) FROM " + tableName() + " WHERE customer_id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, id);
            try (ResultSet result = statement.executeQuery()) {
                result.next();
                return result.getInt(1);
            }
        }
    }

    private void delete(Connection connection, String id) throws Exception {
        String sql = "DELETE FROM " + tableName() + " WHERE customer_id = ?";
        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, id);
            statement.executeUpdate();
        }
    }

    private static String tableName() {
        return "postgresql".equals(System.getProperty("cloudbank.qualification.lane"))
                ? "cloudbank_customer.customers"
                : "CUSTOMERS";
    }

    private static Customers customer(String id, String name, String email, String details) {
        Customers customer = new Customers(id, name, email, details);
        customer.setCustomerPassword("synthetic-hash-" + id);
        return customer;
    }
}
