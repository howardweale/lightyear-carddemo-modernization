-- liquibase formatted sql

--changeset account:postgresql-transaction-core-data-1
INSERT INTO accounts
    (account_id, account_name, account_type, customer_id, account_other_details, account_balance)
VALUES
    (1, 'Synthetic source', 'CH', 'cust-source', 'MS59 synthetic data', 1000),
    (2, 'Synthetic target', 'SA', 'cust-target', 'MS59 synthetic data', 250),
    (3, 'Synthetic empty', 'CH', 'cust-empty', 'MS59 synthetic data', 5);

SELECT setval(pg_get_serial_sequence('accounts', 'account_id'), 3, true);

--rollback DELETE FROM accounts;
