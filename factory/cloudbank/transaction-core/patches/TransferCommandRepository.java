package com.example.accounts.repository;

import com.example.accounts.model.TransferCommand;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TransferCommandRepository extends JpaRepository<TransferCommand, String> {
}
