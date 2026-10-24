package ai.lightyear.carddemo;

import java.util.Arrays;

/** Source FICO range; input syntax is checked separately before this edit. */
public final class AccountFicoRule {
  @CobolSource(program = "COACTUPC", paragraph = "1275-EDIT-FICO-SCORE", lines = "2514-2530")
  public static boolean validScore(int score) {
    return score >= 300 && score <= 850;
  }

  @CobolSource(program = "COACTUPC", paragraph = "1275-EDIT-FICO-SCORE", lines = "2514-2530")
  public static boolean validDisplay(String display) {
    // Three ASCII digits have the same numeric and IBM037 lexical order.
    // One path preserves the disclosed invalid-DISPLAY bound and makes both
    // inclusive endpoints reachable by the same comparison under test.
    byte[] bytes = Commarea.encode(display);
    return Arrays.compareUnsigned(bytes, Commarea.encode("300")) >= 0
        && Arrays.compareUnsigned(bytes, Commarea.encode("850")) <= 0;
  }
}
