// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/

package com.example.customer.model;

import java.util.Date;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.Generated;
import org.hibernate.annotations.GenerationTime;

@SuppressWarnings("deprecation")
@Entity
@Table(name = "customers", schema = "cloudbank_customer")
@Data
@NoArgsConstructor
public class Customers {

    @Id
    @Column(name = "customer_id")
    private String customerId;

    @Column(name = "customer_name")
    private String customerName;

    @Column(name = "customer_email")
    private String customerEmail;

    @Generated(GenerationTime.INSERT)
    @Column(name = "date_became_customer", updatable = false, insertable = false)
    private Date dateBecameCustomer;

    @Column(name = "customer_other_details")
    private String customerOtherDetails;

    @Column(name = "password")
    @JsonIgnore
    private String customerPassword;

    @Column(name = "role")
    private String role;

    /**
     * Creates a Customers object.
     * @param customerId The Customer ID
     * @param customerName The Customer Name
     * @param customerEmail The Customer Email
     * @param customerOtherDetails Other details about the customer
     */
    public Customers(String customerId, String customerName, String customerEmail, String customerOtherDetails) {
        this.customerId = customerId;
        this.customerName = customerName;
        this.customerEmail = customerEmail;
        this.customerOtherDetails = customerOtherDetails;
    }

    @PrePersist
    @PreUpdate
    private void normalizeOracleEmptyStrings() {
        customerId = emptyToNull(customerId);
        customerName = emptyToNull(customerName);
        customerEmail = emptyToNull(customerEmail);
        customerOtherDetails = emptyToNull(customerOtherDetails);
        customerPassword = emptyToNull(customerPassword);
        role = emptyToNull(role);
    }

    private static String emptyToNull(String value) {
        return value != null && value.isEmpty() ? null : value;
    }
}
