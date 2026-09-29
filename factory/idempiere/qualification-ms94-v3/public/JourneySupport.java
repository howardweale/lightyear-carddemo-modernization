package org.idempiere.test;

/** Deterministic plumbing; no business expectations. Review candidate v3. */
public final class JourneySupport {
    private JourneySupport() {}

    public static String text(Object value) {
        if (value == null) return "SQL-NULL";
        if (value instanceof Double || value instanceof Float)
            throw new IllegalArgumentException("Binary floating-point trace values are forbidden");
        if (value instanceof java.math.BigDecimal)
            return ((java.math.BigDecimal)value).stripTrailingZeros().toPlainString();
        String text = String.valueOf(value);
        if (text.equals("SQL-NULL"))
            throw new IllegalArgumentException("SQL-NULL is reserved for null observations");
        return text;
    }

    public static void fact(java.util.Properties trace, String key, Object value) {
        if (key == null || key.isBlank()) throw new IllegalArgumentException("Missing trace key");
        if (trace.containsKey(key)) throw new IllegalArgumentException("Duplicate trace key");
        trace.setProperty(key, text(value));
    }

    /** Explicit lifecycle transition; cannot create a previously absent field. */
    public static void replaceFact(java.util.Properties trace, String key, Object value) {
        if (!trace.containsKey(key)) throw new IllegalArgumentException("Missing trace key to replace");
        trace.setProperty(key, text(value));
    }

    public static boolean posted(org.compiere.model.PO model) {
        return model.get_ValueAsBoolean("Posted");
    }

    /** Does not prevent application-internal costing or reposting. */
    public static void postOnce(org.compiere.model.PO model, org.compiere.model.MAcctSchema[] schemas) {
        if (!model.load(model.get_TrxName())) throw new IllegalStateException("Reload before posting failed");
        if (!posted(model)) {
            String error = org.compiere.acct.DocManager.postDocument(schemas,
                model.get_Table_ID(), model.get_ID(), false, false, model.get_TrxName());
            // Native application logs are private; the diagnostic exporter must not forward this text.
            if (error != null && !error.isEmpty())
                throw new IllegalStateException("Posting failed", new IllegalStateException(error));
            if (!model.load(model.get_TrxName())) throw new IllegalStateException("Reload after posting failed");
        }
        if (!posted(model)) throw new IllegalStateException("Document remains unposted");
    }

    @FunctionalInterface
    public interface TransactionBody<T> { T run(String name) throws Exception; }

    public static <T> T transaction(String prefix, TransactionBody<T> body) throws Exception {
        String name = org.compiere.util.Trx.createTrxName(prefix);
        org.compiere.util.Trx transaction = org.compiere.util.Trx.get(name, true);
        Throwable primary = null;
        try {
            T value = body.run(name);
            if (!transaction.commit(true)) throw new IllegalStateException("Commit failed");
            return value;
        } catch (Exception | Error failure) {
            primary = failure;
            try {
                if (!transaction.rollback()) throw new IllegalStateException("Rollback failed");
            } catch (Exception | Error rollbackFailure) {
                if (rollbackFailure != failure) failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            try { transaction.close(); }
            catch (Exception | Error closeFailure) {
                if (primary == null) throw closeFailure;
                if (primary != closeFailure) primary.addSuppressed(closeFailure);
            }
        }
    }
}
