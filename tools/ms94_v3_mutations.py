"""Private reference-source negative controls; never builder feedback."""
from lightyear_calibration.contracts import require


def own_match_repost(source):
    anchor='            post(vendorInvoice, schemas);\n            commit();'
    require(source.count(anchor)==1,'Purchasing reference injection anchor changed')
    inserted=anchor+'''
            // Deliberate qualification fault: explicitly repost this journey's match.
            MMatchInv[] injectedMatches = MMatchInv.getInvoice(ctx, vendorInvoice.get_ID(), trx);
            assertTrue(injectedMatches.length > 0, "Mutation needs a journey match");
            for (MMatchInv injected : injectedMatches) {
                String injectedError = org.compiere.acct.DocManager.postDocument(schemas,
                    MMatchInv.Table_ID, injected.get_ID(), false, true, trx);
                assertTrue(injectedError == null || injectedError.isEmpty(), "Repost injection failed");
            }
            commit();'''
    return source.replace(anchor,inserted)


def duplicate_trace(source):
    anchor='            fact("newIssueCount", issuesAfter - issuesBefore);'
    require(source.count(anchor)==1,'Reference trace injection anchor changed')
    return source.replace(anchor,anchor+'\n            fact("newIssueCount", issuesAfter - issuesBefore);')
