package com.example.accounts.model;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@Entity
@Table(name = "transfer_commands")
public class TransferCommand {

    @Id
    @Column(name = "command_id", length = 96)
    private String commandId;

    @Column(name = "source_account_id", nullable = false)
    private long sourceAccountId;

    @Column(name = "target_account_id", nullable = false)
    private long targetAccountId;

    @Column(name = "amount", nullable = false)
    private long amount;

    @Column(name = "state", nullable = false, length = 24)
    private String state;

    @Column(name = "actor", nullable = false, length = 80)
    private String actor;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    public TransferCommand(String commandId, long sourceAccountId, long targetAccountId,
            long amount, String state, String actor) {
        this.commandId = commandId;
        this.sourceAccountId = sourceAccountId;
        this.targetAccountId = targetAccountId;
        this.amount = amount;
        this.state = state;
        this.actor = actor;
        this.createdAt = Instant.now();
    }
}
