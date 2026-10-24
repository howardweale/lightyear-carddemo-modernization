package ai.lightyear.carddemo;

/** Typed boundary to existing fixed-width storage; the original 88-level predicate is retained. */
final class AccountFeedbackState implements AccountValidationFeedback.State {
  private final SourceEdits edits;

  AccountFeedbackState(SourceEdits edits) {
    this.edits = edits;
  }

  @CobolSource(program = "COACTUPC", paragraph = "1215-EDIT-MANDATORY", lines = "1838-1843")
  public String get(AccountValidationFeedback.Field field) {
    return edits.get(field.storage());
  }

  @CobolSource(program = "COACTUPC", paragraph = "1215-EDIT-MANDATORY", lines = "1836-1843")
  public void put(AccountValidationFeedback.Field field, String value) {
    edits.put(field.storage(), value);
  }

  @CobolSource(program = "COACTUPC", paragraph = "1215-EDIT-MANDATORY", lines = "1838-1838")
  public boolean messageOff() {
    return edits.condition("WS-RETURN-MSG-OFF");
  }
}
