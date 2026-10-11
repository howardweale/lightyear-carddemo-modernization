package ai.lightyear.carddemo.service;

import ai.lightyear.carddemo.CardDemoCandidateApplication;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = CardDemoCandidateApplication.class, properties = {
    "carddemo.input-dir=target/twin-context-input", "carddemo.output-dir=target/twin-context-output",
    "carddemo.processing-date=2022071800", "carddemo.timestamp=2022-07-18-00.00.00.000000",
    "carddemo.final-account-policy=source-faithful", "spring.batch.job.enabled=false", "spring.main.web-application-type=none",
    "spring.datasource.url=jdbc:h2:mem:twin-context;DB_CLOSE_DELAY=-1"
})
class TwinApplicationContextTest {
    @Autowired ApplicationContext context;
    @Autowired InterestCalculationService service;
    @Test void deployedServiceExecutesThroughRealContext() {
        assertThat(service).isSameAs(context.getBean(InterestCalculationService.class));
        assertThat(context.containsBean("cardDemoIntcalcJob")).isTrue();
        var result=service.calculate(List.of(),List.of(),List.of(),List.of(),
            "2022071800","2022-07-18-00.00.00.000000","source-faithful");
        assertThat(result.accounts()).isEmpty();
        assertThat(result.transactions()).isEmpty();
    }
}
