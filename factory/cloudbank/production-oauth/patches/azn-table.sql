-- liquibase formatted sql

-- changeset lightyear:ms62-user-repository
CREATE SCHEMA IF NOT EXISTS user_repo;
CREATE TABLE user_repo.users
(
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    password VARCHAR(255) NOT NULL,
    roles VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255),
    otp VARCHAR(255),
    created_on TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT CURRENT_USER,
    updated_on TIMESTAMP WITH TIME ZONE,
    updated_by VARCHAR(255)
);
COMMENT ON TABLE user_repo.users IS
    'Application user repository for OAuth2/OIDC user management';
COMMENT ON COLUMN user_repo.users.password IS
    'BCrypt hash of the application user password; never store cleartext';
COMMENT ON COLUMN user_repo.users.otp IS
    'BCrypt hash of the one-time password; never store cleartext';

-- rollback DROP SCHEMA user_repo CASCADE;
