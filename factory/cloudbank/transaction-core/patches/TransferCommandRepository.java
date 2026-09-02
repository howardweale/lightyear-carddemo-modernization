// Copyright (c) 2023, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts.repository;

import com.example.accounts.model.TransferCommand;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TransferCommandRepository extends JpaRepository<TransferCommand, String> {
}
