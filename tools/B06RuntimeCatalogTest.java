package org.idempiere.test;

import org.junit.jupiter.api.Test;

/** Plain JUnit only: no Adempiere test base, database login, fixtures or postings. */
public class B06RuntimeCatalogTest {
    @Test public void resolveWithoutDatabase() throws Exception {
        for (String name : new String[] {"org.compiere.acct.Doc", "org.compiere.acct.DocManager",
                                         "org.compiere.model.PO", "org.compiere.util.DB"}) {
            Class.forName(name, false, getClass().getClassLoader());
        }
        // Tycho may explicitly exit its JVM after this method returns.
        String output=System.getProperty("b06.closure.output");
        if(output==null)throw new IllegalStateException("closure agent is not installed");
        java.nio.file.Path root=java.nio.file.Path.of(output).getParent();
        long deadline=System.nanoTime()+600_000_000_000L;
        while(System.nanoTime()<deadline) {
            if(java.nio.file.Files.exists(root.resolve("closure-error.json")))
                throw new AssertionError(java.nio.file.Files.readString(root.resolve("closure-error.json")));
            if(java.nio.file.Files.exists(root.resolve("closure-complete.json"))) {
                if(!java.nio.file.Files.isRegularFile(java.nio.file.Path.of(output)))
                    throw new AssertionError("completion without observation");
                return;
            }
            Thread.sleep(50);
        }
        throw new AssertionError("closure completion marker missing after 600 seconds");
    }
}
