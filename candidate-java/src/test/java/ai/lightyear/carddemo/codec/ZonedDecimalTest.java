package ai.lightyear.carddemo.codec;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;

class ZonedDecimalTest {

    @Test
    void positiveRoundTrip() {
        String encoded = ZonedDecimal.encode(new BigDecimal("123.45"), 7, 2);
        assertThat(encoded).isEqualTo("001234E");
        assertThat(ZonedDecimal.decode(encoded, 2)).isEqualByComparingTo("123.45");
    }

    @Test
    void negativeRoundTrip() {
        String encoded = ZonedDecimal.encode(new BigDecimal("-123.45"), 7, 2);
        assertThat(encoded).isEqualTo("001234N");
        assertThat(ZonedDecimal.decode(encoded, 2)).isEqualByComparingTo("-123.45");
    }

    @Test
    void truncatesTowardZero() {
        assertThat(ZonedDecimal.encode(new BigDecimal("1.239"), 4, 2)).isEqualTo("012C");
        assertThat(ZonedDecimal.encode(new BigDecimal("-1.239"), 4, 2)).isEqualTo("012L");
    }
}

