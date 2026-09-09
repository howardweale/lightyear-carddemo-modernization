package ai.lightyear.tests;

import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LoggingApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoggingApplication.class, args);
        LoggerFactory.getLogger(LoggingApplication.class).info("business-logging-preserved");
    }

    @PostMapping("/probe")
    public String probe() {
        return "ok";
    }
}
