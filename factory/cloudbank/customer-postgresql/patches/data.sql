-- liquibase formatted sql

-- changeset customer:3 runAlways:true
TRUNCATE TABLE cloudbank_customer.customers;

INSERT INTO cloudbank_customer.customers
    (customer_id, customer_name, customer_email, date_became_customer, customer_other_details, password, role)
VALUES
    ('cust-001', 'Alice', 'alice@example.test', TIMESTAMP '2026-09-01 10:15:30', 'Synthetic alpha', 'synthetic-hash-a', 'USER_ROLE'),
    ('cust-002', 'Alicia', 'ops@example.test', TIMESTAMP '2026-09-01 10:16:30', 'Synthetic beta', 'synthetic-hash-b', 'USER_ROLE'),
    ('cust-003', 'Bob', NULL, TIMESTAMP '2026-09-01 10:17:30', NULL, NULL, NULL);

INSERT INTO cloudbank_customer.customers
    (customer_id, customer_name, customer_email, customer_other_details, password, role)
VALUES
    ('cust-004', 'Zed', 'zed@elsewhere.test', NULLIF('', ''), 'synthetic-hash-d', 'USER_ROLE');

-- rollback DELETE FROM cloudbank_customer.customers;
