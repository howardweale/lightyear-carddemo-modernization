-- liquibase formatted sql

-- changeset customer:1
CREATE SCHEMA IF NOT EXISTS cloudbank_customer;
DROP TABLE IF EXISTS cloudbank_customer.customers;

-- changeset customer:2
CREATE TABLE cloudbank_customer.customers (
    customer_id VARCHAR(20) COLLATE "C" NOT NULL,
    customer_name VARCHAR(40) COLLATE "C",
    customer_email VARCHAR(40) COLLATE "C",
    date_became_customer TIMESTAMP(0) WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP(0) NOT NULL,
    customer_other_details VARCHAR(4000) COLLATE "C",
    password VARCHAR(40) COLLATE "C",
    role VARCHAR(40) COLLATE "C",
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
);

COMMENT ON TABLE cloudbank_customer.customers IS 'CLOUDBANK CUSTOMERS TABLE';

-- rollback DROP TABLE cloudbank_customer.customers;
