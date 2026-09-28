package org.idempiere.test;

/** Public deterministic plumbing. Contains no expected business amounts or judge rules. */
public final class JourneySupport {
    private JourneySupport() {}

    public static String text(Object value) {
        if (value == null) return "SQL-NULL";
        if (value instanceof java.math.BigDecimal)
            return ((java.math.BigDecimal)value).stripTrailingZeros().toPlainString();
        return String.valueOf(value);
    }

    public static void fact(java.util.Properties trace, String key, Object value) {
        if (key == null || key.isBlank()) throw new IllegalArgumentException("Missing trace key");
        if (trace.containsKey(key)) throw new IllegalArgumentException("Duplicate trace key");
        trace.setProperty(key, text(value));
    }

    /** Explicit lifecycle update; serialization still contains one entry per key. */
    public static void replaceFact(java.util.Properties trace, String key, Object value) {
        if (!trace.containsKey(key)) throw new IllegalArgumentException("Missing trace key to replace");
        trace.setProperty(key, text(value));
    }

    public static boolean posted(org.compiere.model.PO model) {
        return model.get_ValueAsBoolean("Posted");
    }

    /** Skips already-posted documents. Application-owned downstream costing may still repost matching records. */
    public static void postOnce(org.compiere.model.PO model, org.compiere.model.MAcctSchema[] schemas) {
        model.load(model.get_TrxName());
        if (!posted(model)) {
            String error = org.compiere.acct.DocManager.postDocument(schemas,
                model.get_Table_ID(), model.get_ID(), false, false, model.get_TrxName());
            if (error != null && !error.isEmpty()) throw new IllegalStateException("Posting failed");
            model.load(model.get_TrxName());
        }
        if (!posted(model)) throw new IllegalStateException("Document remains unposted");
    }

    @FunctionalInterface
    public interface TransactionBody<T> { T run(String name) throws Exception; }

    public static <T> T transaction(String prefix, TransactionBody<T> body) throws Exception {
        String name = org.compiere.util.Trx.createTrxName(prefix);
        org.compiere.util.Trx transaction = org.compiere.util.Trx.get(name, true);
        boolean committed = false;
        try {
            T value = body.run(name);
            if (!transaction.commit(true)) throw new IllegalStateException("Commit failed");
            committed = true;
            return value;
        } finally {
            try {
                if (!committed && !transaction.rollback())
                    throw new IllegalStateException("Rollback failed");
            } finally { transaction.close(); }
        }
    }
}
