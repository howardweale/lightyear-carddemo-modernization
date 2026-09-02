// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

package com.example.customer;

import java.util.List;

import com.example.customer.controller.CustomerController;
import com.example.customer.model.Customers;
import com.example.customer.repository.CustomersRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.Table;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = {
        "eureka.client.enabled=false",
        "spring.cloud.discovery.enabled=false",
        "spring.cloud.config.enabled=false",
        "cloudbank.security.require-internal-token=false"
})
@Transactional
class CustomerApplicationTests {

    private static final String SHARED_MARKER = "rows:4;name:2;email:2;case:0;empty:null;crud:pass;default:pass;auth:pass";

    @Autowired
    private CustomersRepository repository;

    @Autowired
    private EntityManager entityManager;

    @BeforeEach
    void seedSharedSyntheticCorpus() {
        repository.deleteAll();
        repository.saveAllAndFlush(List.of(
                customer("cust-001", "Alice", "alice@example.test", "Synthetic alpha"),
                customer("cust-002", "Alicia", "ops@example.test", "Synthetic beta"),
                customer("cust-003", "Bob", null, null),
                customer("cust-004", "Zed", "zed@elsewhere.test", "")));
        entityManager.clear();
    }

    @Test
    void sharedOracleAndPostgreSqlContract() {
        assertEquals(4, repository.count());
        assertEquals(2, repository.findByCustomerNameIsContaining("Ali").size());
        assertEquals(2, repository.findByCustomerEmailIsContaining("example.test").size());
        assertEquals(0, repository.findByCustomerNameIsContaining("ali").size());

        Customers zed = repository.findById("cust-004").orElseThrow();
        assertNull(zed.getCustomerOtherDetails());
        assertNotNull(zed.getDateBecameCustomer());

        Customers alice = repository.findById("cust-001").orElseThrow();
        alice.setCustomerEmail("changed@example.test");
        repository.saveAndFlush(alice);
        assertEquals("changed@example.test", repository.findById("cust-001").orElseThrow().getCustomerEmail());

        Customers transientCustomer = customer("cust-txn", "Transient", null, null);
        repository.saveAndFlush(transientCustomer);
        assertTrue(repository.existsById("cust-txn"));
        repository.deleteById("cust-txn");
        repository.flush();
        assertFalse(repository.existsById("cust-txn"));

        CustomerController controller = new CustomerController(repository);
        Authentication owner = new UsernamePasswordAuthenticationToken("cust-001", "n/a", List.of());
        Authentication admin = new UsernamePasswordAuthenticationToken(
                "factory-admin", "n/a", List.of(new SimpleGrantedAuthority("SCOPE_cloudbank.admin")));
        assertEquals(1, controller.findAll(owner).size());
        assertEquals(4, controller.findAll(admin).size());
        assertEquals(HttpStatus.FORBIDDEN, controller.getCustomerById("cust-002", owner).getStatusCode());

        System.out.println("CLOUDBANK_SHARED_CONTRACT=" + SHARED_MARKER);
    }

    @Test
    void targetRoleMappingIsExplicit() throws Exception {
        if (!"postgresql".equals(System.getProperty("cloudbank.factory.lane"))) {
            return;
        }
        assertNotNull(Customers.class.getDeclaredField("role"));
        Table table = Customers.class.getAnnotation(Table.class);
        assertEquals("cloudbank_customer", table.schema());
        assertEquals("customers", table.name());
    }

    private static Customers customer(String id, String name, String email, String details) {
        Customers customer = new Customers(id, name, email, details);
        customer.setCustomerPassword("synthetic-hash-" + id);
        return customer;
    }
}
