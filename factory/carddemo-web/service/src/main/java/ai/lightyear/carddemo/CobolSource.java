package ai.lightyear.carddemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Physical lines in the pinned public source, checked by CI. */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@java.lang.annotation.Repeatable(CobolSources.class)
public @interface CobolSource {
    String program();
    String paragraph();
    String lines();
}
