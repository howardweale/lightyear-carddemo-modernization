package ai.lightyear.carddemo.config;

import ai.lightyear.carddemo.batch.InterestCalculationTasklet;

import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class BatchConfiguration {

    @Bean
    public Step cardDemoIntcalcStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            InterestCalculationTasklet tasklet) {
        return new StepBuilder("cardDemoIntcalcStep", jobRepository)
                .tasklet(tasklet, transactionManager)
                .build();
    }

    @Bean
    public Job cardDemoIntcalcJob(JobRepository jobRepository, Step cardDemoIntcalcStep) {
        return new JobBuilder("cardDemoIntcalcJob", jobRepository)
                .start(cardDemoIntcalcStep)
                .build();
    }
}
