package org.idempiere.test;

import org.junit.jupiter.api.Test;

/** Plain JUnit only: no Adempiere test base, database login, fixtures or postings. */
public class B06RuntimeCatalogTest {
    @Test public void resolveWithoutDatabase() throws Exception {
        for (String name : new String[] {"org.compiere.acct.Doc", "org.compiere.acct.DocManager",
                                         "org.compiere.model.PO", "org.compiere.util.DB"}) {
            Class.forName(name, false, getClass().getClassLoader());
        }
        // JUnit loads its terminal/engine classes naturally while running this method.
    }
}
