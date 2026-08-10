package ai.lightyear.carddemo.batch;

import static ai.lightyear.carddemo.codec.CardDemoRecordCodec.ACCOUNT_LENGTH;
import static ai.lightyear.carddemo.codec.CardDemoRecordCodec.TRANSACTION_LENGTH;

import ai.lightyear.carddemo.codec.CardDemoRecordCodec;
import ai.lightyear.carddemo.domain.Records.Account;
import ai.lightyear.carddemo.domain.Records.CardXref;
import ai.lightyear.carddemo.domain.Records.CategoryBalance;
import ai.lightyear.carddemo.domain.Records.Disclosure;
import ai.lightyear.carddemo.io.DatasetIo;
import ai.lightyear.carddemo.service.InterestCalculationService;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.StepContribution;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.infrastructure.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class InterestCalculationTasklet implements Tasklet {

    private final InterestCalculationService service;
    private final Path inputDir;
    private final Path outputDir;
    private final String processingDate;
    private final String timestamp;
    private final String finalAccountPolicy;

    public InterestCalculationTasklet(
            InterestCalculationService service,
            @Value("${carddemo.input-dir}") String inputDir,
            @Value("${carddemo.output-dir}") String outputDir,
            @Value("${carddemo.processing-date}") String processingDate,
            @Value("${carddemo.timestamp}") String timestamp,
            @Value("${carddemo.final-account-policy}") String finalAccountPolicy) {
        this.service = service;
        this.inputDir = Path.of(inputDir);
        this.outputDir = Path.of(outputDir);
        this.processingDate = processingDate;
        this.timestamp = timestamp;
        this.finalAccountPolicy = finalAccountPolicy;
    }

    @Override
    public RepeatStatus execute(StepContribution contribution, ChunkContext chunkContext) throws Exception {
        var balances = DatasetIo.read(inputDir.resolve("tcatbal.txt"), CardDemoRecordCodec::parseCategoryBalance);
        var disclosures = DatasetIo.read(inputDir.resolve("discgrp.txt"), CardDemoRecordCodec::parseDisclosure);
        var xrefs = DatasetIo.read(inputDir.resolve("cardxref.txt"), CardDemoRecordCodec::parseCardXref);
        var accounts = DatasetIo.read(inputDir.resolve("acctdata.txt"), CardDemoRecordCodec::parseAccount);

        var result = service.calculate(
                balances,
                disclosures,
                xrefs,
                accounts,
                processingDate,
                timestamp,
                finalAccountPolicy);

        Path accountOutput = outputDir.resolve("acctdata.txt");
        Path transactionOutput = outputDir.resolve("transactions.txt");
        DatasetIo.write(accountOutput, result.accounts(), CardDemoRecordCodec::renderAccount, ACCOUNT_LENGTH);
        DatasetIo.write(
                transactionOutput,
                result.transactions(),
                CardDemoRecordCodec::renderTransaction,
                TRANSACTION_LENGTH);
        writeReceipt(result, accountOutput, transactionOutput);
        contribution.incrementWriteCount(result.accounts().size() + result.transactions().size());
        return RepeatStatus.FINISHED;
    }

    private void writeReceipt(
            InterestCalculationService.RunResult result,
            Path accountOutput,
            Path transactionOutput) throws IOException, NoSuchAlgorithmException {
        Files.createDirectories(outputDir);
        var observations = result.observations();
        String json = """
                {
                  "candidate": "carddemo-spring-batch-intcalc",
                  "candidateVersion": "0.1.0-SNAPSHOT",
                  "upstreamCommit": "59cc6c2fd7ebd7ef7925cad552a01a4b8b6e4d5e",
                  "processingDate": "%s",
                  "timestamp": "%s",
                  "finalAccountPolicy": "%s",
                  "outputs": {
                    "accounts": {"records": %d, "sha256": "%s"},
                    "transactions": {"records": %d, "sha256": "%s"}
                  },
                  "observations": {
                    "balanceRows": %d,
                    "accountUpdates": %d,
                    "transactionsCreated": %d,
                    "defaultRatesUsed": %d,
                    "zeroRateRows": %d
                  }
                }
                """.formatted(
                processingDate,
                timestamp,
                finalAccountPolicy,
                result.accounts().size(),
                sha256(accountOutput),
                result.transactions().size(),
                sha256(transactionOutput),
                observations.balanceRows(),
                observations.accountUpdates(),
                observations.transactionsCreated(),
                observations.defaultRatesUsed(),
                observations.zeroRateRows());
        Files.writeString(
                outputDir.resolve("candidate-receipt.json"),
                json,
                StandardCharsets.UTF_8);
    }

    private static String sha256(Path path) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, count);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
