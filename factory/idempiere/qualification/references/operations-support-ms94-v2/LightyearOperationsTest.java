package org.idempiere.test;

import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

import org.compiere.acct.Doc;
import org.compiere.model.*;
import org.compiere.process.DocAction;
import org.compiere.process.ProcessInfo;
import org.compiere.util.DB;
import org.compiere.util.Env;
import org.compiere.util.Trx;
import org.compiere.wf.MWorkflow;
import org.junit.jupiter.api.Test;

public class LightyearOperationsTest extends AbstractTestCase {
    private final Properties evidence = new Properties();
    private final Timestamp businessDate = Timestamp.valueOf("2026-09-26 00:00:00");
    private static final String LOGICAL_KEY = "LY-BOUNDARY";
    private static final String RETRY_KEY = "LY-BOUNDARY-RETRY";
    private static final String CUSTOMER_NAME = "Café 東京 Łódź";

    private void fact(String key, Object value) {
        if (evidence.containsKey(key)) JourneySupport.replaceFact(evidence, key, value);
        else JourneySupport.fact(evidence, key, value);
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private void record(String name, PO model) {
        fact(name + ".id", model.get_ID());
        fact(name + ".uuid", model.get_UUID());
        fact(name + ".saved", !model.is_new());
    }

    private void action(PO model, String requestedAction) {
        ProcessInfo result = MWorkflow.runDocumentActionWorkflow(model, requestedAction);
        require(result != null, "Workflow returned no ProcessInfo");
        require(!result.isError(), "Workflow failed: " + result.getSummary());
        model.load(model.get_TrxName());
    }

    private void complete(String name, PO model) {
        action(model, DocAction.ACTION_Complete);
        require(DocAction.STATUS_Completed.equals(model.get_ValueAsString("DocStatus")),
            "Document did not complete: " + name);
        record(name, model);
        fact(name + ".status", model.get_ValueAsString("DocStatus"));
    }

    private void readAccounting(PO model, MAcctSchema[] schemas) {
        for (MAcctSchema schema : schemas) {
            int count = DB.getSQLValueEx(model.get_TrxName(),
                "SELECT COUNT(*) FROM Fact_Acct WHERE AD_Table_ID=? AND Record_ID=? AND C_AcctSchema_ID=?",
                model.get_Table_ID(), model.get_ID(), schema.get_ID());
            require(count >= 0, "Accounting row read failed");
            if (count > 0) {
                BigDecimal balance = DB.getSQLValueBDEx(model.get_TrxName(),
                    "SELECT SUM(AmtAcctDr-AmtAcctCr) FROM Fact_Acct WHERE AD_Table_ID=? AND Record_ID=? AND C_AcctSchema_ID=?",
                    model.get_Table_ID(), model.get_ID(), schema.get_ID());
                require(balance != null && balance.signum() == 0,
                    "Unbalanced accounting for " + model.get_TableName() + " " + model.get_ID());
            }
        }
    }

    private void post(PO model, MAcctSchema[] schemas) {
        JourneySupport.postOnce(model, schemas);
        readAccounting(model, schemas);
    }

    private void postAllocations(Properties ctx, int invoiceId, String trx,
                                 MAcctSchema[] schemas) {
        for (MAllocationHdr allocation : MAllocationHdr.getOfInvoice(ctx, invoiceId, trx)) {
            post(allocation, schemas);
        }
    }

    private BigDecimal stock(int productId, String trx) {
        return DB.getSQLValueBDEx(trx,
            "SELECT SUM(QtyOnHand) FROM M_StorageOnHand WHERE M_Product_ID=?", productId);
    }

    private MBPartner newCustomer(Properties ctx, MBPartner template, String key, String trx) {
        MBPartner customer = new MBPartner(ctx, 0, trx);
        customer.setValue(key);
        customer.setName(CUSTOMER_NAME);
        customer.setDescription("");
        customer.setIsCustomer(true);
        customer.setC_BP_Group_ID(template.getC_BP_Group_ID());
        customer.setM_PriceList_ID(template.getM_PriceList_ID());
        customer.setC_PaymentTerm_ID(template.getC_PaymentTerm_ID());
        customer.setPaymentRule(MBPartner.PAYMENTRULE_OnCredit);
        customer.setSO_CreditLimit(new BigDecimal("100.00"));
        return customer;
    }

    private static final class InjectedFailure extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }

    private static final class CustomerResult {
        final MBPartner customer;
        final boolean existing;
        CustomerResult(MBPartner customer, boolean existing) {
            this.customer = customer;
            this.existing = existing;
        }
    }

    private CustomerResult findOrCreateRetryCustomer(Properties ctx, MBPartner template)
            throws Exception {
        CustomerResult result = JourneySupport.transaction("LYRetry", trxName -> {
            List<MBPartner> found = new Query(ctx, MBPartner.Table_Name,
                "AD_Client_ID=? AND Value=?", trxName)
                .setParameters(getAD_Client_ID(), RETRY_KEY).list();
            require(found.size() <= 1, "Caller key is not unique");
            boolean existing = !found.isEmpty();
            MBPartner customer = existing ? found.get(0)
                : newCustomer(ctx, template, RETRY_KEY, trxName);
            if (!existing) customer.saveEx();
            return new CustomerResult(customer, existing);
        });
        return new CustomerResult(new MBPartner(ctx, result.customer.get_ID(), null), result.existing);
    }

    private void recovery(Properties ctx, MBPartner template) throws Exception {
        try {
            JourneySupport.transaction("LYRollback", trxName -> {
                MBPartner draft = newCustomer(ctx, template, RETRY_KEY, trxName);
                draft.saveEx();
                Thread.sleep(1500);
                fact("recovery.rolledBackId", draft.get_ID());
                throw new InjectedFailure();
            });
            throw new AssertionError("Injected failure was swallowed");
        } catch (InjectedFailure expected) {
            // The deterministic transaction helper has rolled back and closed.
            Thread.sleep(1500); // Allow independent observation before any retry can commit.
        }
        int rowsAfterRollback = DB.getSQLValueEx(null,
            "SELECT COUNT(*) FROM C_BPartner WHERE AD_Client_ID=? AND Value=?",
            getAD_Client_ID(), RETRY_KEY);
        fact("recovery.rowsAfterRollback", rowsAfterRollback);
        require(rowsAfterRollback == 0, "Draft customer survived rollback");

        CustomerResult retry = findOrCreateRetryCustomer(ctx, template);
        require(!retry.existing, "Retry did not create the rolled-back caller key");
        record("recoveryCustomer", retry.customer);
        CustomerResult repeated = findOrCreateRetryCustomer(ctx, template);
        boolean returnedExisting = repeated.existing
            && repeated.customer.get_ID() == retry.customer.get_ID();
        fact("recovery.repeatedRequest", returnedExisting
            ? "existing-record-returned" : "different-record-returned");
        int rowsAfterRepeatedRequest = DB.getSQLValueEx(null,
            "SELECT COUNT(*) FROM C_BPartner WHERE AD_Client_ID=? AND Value=?",
            getAD_Client_ID(), RETRY_KEY);
        fact("recovery.rowsAfterRepeatedRequest", rowsAfterRepeatedRequest);
        require(returnedExisting && rowsAfterRepeatedRequest == 1,
            "Repeated caller key was not idempotent");
    }

    private MBPartner lockCustomer(Properties ctx, int customerId, String trx) {
        List<MBPartner> rows = new Query(ctx, MBPartner.Table_Name,
            "C_BPartner_ID=?", trx)
            .setParameters(customerId).setForUpdate(true).list();
        require(rows.size() == 1 && rows.get(0).get_ID() == customerId,
            "Expected exactly the requested customer primary key");
        return rows.get(0);
    }

    private void concurrency(Properties ctx, int customerId) throws Exception {
        Properties firstCtx = (Properties) ctx.clone();
        Properties secondCtx = (Properties) ctx.clone();
        String firstName = Trx.createTrxName("LYCreditFirst");
        Trx firstTransaction = Trx.get(firstName, true);
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch secondAttempting = new CountDownLatch(1);
        CountDownLatch secondAcquired = new CountDownLatch(1);
        AtomicLong secondAcquiredAt = new AtomicLong();
        Future<BigDecimal> secondResult = null;
        boolean firstCommitted = false;
        try {
            MBPartner first = lockCustomer(firstCtx, customerId, firstName);
            fact("concurrency.lockingApi", "Query.setForUpdate(true).list-single-primary-key");
            first.setSO_CreditLimit(first.getSO_CreditLimit().add(new BigDecimal("0.01")));
            first.saveEx();
            first.load(firstName);
            BigDecimal firstValue = first.getSO_CreditLimit();

            secondResult = executor.submit(() -> {
                String secondName = Trx.createTrxName("LYCreditSecond");
                Trx secondTransaction = Trx.get(secondName, true);
                boolean secondCommitted = false;
                try {
                    secondAttempting.countDown();
                    MBPartner second = lockCustomer(secondCtx, customerId, secondName);
                    secondAcquiredAt.set(System.nanoTime());
                    secondAcquired.countDown();
                    second.setSO_CreditLimit(
                        second.getSO_CreditLimit().add(new BigDecimal("0.01")));
                    second.saveEx();
                    second.load(secondName);
                    BigDecimal readback = second.getSO_CreditLimit();
                    secondTransaction.commit(true);
                    secondCommitted = true;
                    return readback;
                } finally {
                    if (!secondCommitted) {
                        secondTransaction.rollback();
                    }
                    secondTransaction.close();
                }
            });
            require(secondAttempting.await(30, TimeUnit.SECONDS),
                "Second transaction did not reach its lock request");
            boolean remainedPending = !secondAcquired.await(1500, TimeUnit.MILLISECONDS);
            long releaseStartedAt = System.nanoTime();
            firstTransaction.commit(true);
            firstCommitted = true;
            BigDecimal secondValue = secondResult.get(60, TimeUnit.SECONDS);
            boolean waited = remainedPending && secondAcquiredAt.get() >= releaseStartedAt;
            fact("concurrency.firstValue", firstValue);
            fact("concurrency.secondValue", secondValue);
            fact("concurrency.secondWaitedForLock", waited);
            MBPartner finalCustomer = new MBPartner(ctx, customerId, null);
            fact("concurrency.finalCreditLimit", finalCustomer.getSO_CreditLimit());
            require(waited, "Second transaction did not wait for the held row lock");
        } finally {
            if (!firstCommitted) {
                firstTransaction.rollback();
            }
            firstTransaction.close();
            if (secondResult != null && !secondResult.isDone()) {
                secondResult.cancel(true);
            }
            executor.shutdownNow();
            require(executor.awaitTermination(30, TimeUnit.SECONDS),
                "Credit-limit worker did not terminate");
        }
    }

    @Test
    public void operationsJourney() throws Exception {
        Path output = Path.of(System.getProperty("lightyear.output"));
        evidence.clear();
        fact("status", "started");
        fact("database", DB.isOracle() ? "oracle" : "postgresql");
        try {
            Properties ctx = Env.getCtx();
            String trx = getTrxName();
            int issuesBefore = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            MAcctSchema[] schemas = MAcctSchema.getClientAcctSchema(ctx, getAD_Client_ID());
            require(schemas.length > 0, "Client has no accounting schemas");
            MBPartner template = new MBPartner(ctx, DictionaryIDs.C_BPartner.JOE_BLOCK.id, trx);
            MBPartner customer = newCustomer(ctx, template, LOGICAL_KEY, trx);
            fact("customer.name.input", customer.getName());
            fact("customer.description.input", "empty-string");
            customer.saveEx();
            customer.load(trx);
            record("customer", customer);
            fact("customer.name.readback", customer.getName());
            fact("customer.description.readback", customer.getDescription() == null
                ? "SQL-NULL" : customer.getDescription());
            MBPartnerLocation[] templateLocations = template.getLocations(false);
            require(templateLocations.length > 0, "Template customer has no location");
            MBPartnerLocation location = new MBPartnerLocation(ctx, 0, trx);
            location.setC_BPartner_ID(customer.get_ID());
            location.setC_Location_ID(templateLocations[0].getC_Location_ID());
            location.setName("Evaluation location");
            location.setIsBillTo(true);
            location.setIsShipTo(true);
            location.saveEx();
            record("customerLocation", location);
            commit();

            MProduct product = new MProduct(ctx, 0, trx);
            product.setValue(LOGICAL_KEY);
            product.setName("Lightyear Equivalence Product");
            product.setM_Product_Category_ID(DictionaryIDs.M_Product_Category.STANDARD.id);
            product.setProductType(MProduct.PRODUCTTYPE_Item);
            product.setIsStocked(true);
            product.setIsSold(true);
            product.setIsPurchased(true);
            product.setC_UOM_ID(DictionaryIDs.C_UOM.EACH.id);
            product.setC_TaxCategory_ID(DictionaryIDs.C_TaxCategory.STANDARD.id);
            product.saveEx();
            record("product", product);
            commit();

            MInventory inventory = new MInventory(ctx, 0, trx);
            inventory.setM_Warehouse_ID(getM_Warehouse_ID());
            inventory.setMovementDate(businessDate);
            inventory.setC_DocType_ID(DictionaryIDs.C_DocType.MATERIAL_PHYSICAL_INVENTORY.id);
            inventory.saveEx();
            MInventoryLine inventoryLine = new MInventoryLine(inventory,
                DictionaryIDs.M_Locator.HQ.id, product.get_ID(), 0,
                BigDecimal.ZERO, new BigDecimal("10"));
            inventoryLine.saveEx();
            complete("openingInventory", inventory);
            inventoryLine.load(trx);
            fact("openingInventory.quantity", inventoryLine.getQtyCount());
            commit();

            MOrder order = new MOrder(ctx, 0, trx);
            order.setBPartner(customer);
            order.setC_BPartner_Location_ID(location.get_ID());
            order.setBill_Location_ID(location.get_ID());
            order.setM_Warehouse_ID(getM_Warehouse_ID());
            order.setC_DocTypeTarget_ID(MOrder.DocSubTypeSO_Standard);
            order.setDateOrdered(businessDate);
            order.setDatePromised(businessDate);
            order.setDeliveryRule(MOrder.DELIVERYRULE_CompleteOrder);
            order.setPaymentRule(MOrder.PAYMENTRULE_OnCredit);
            order.saveEx();
            MPriceListVersion version = MPriceList.get(ctx, order.getM_PriceList_ID(), trx)
                .getPriceListVersion(businessDate);
            require(version != null, "No price list version for business date");
            MProductPrice price = new MProductPrice(ctx, version.get_ID(), product.get_ID(), trx);
            price.setPriceList(new BigDecimal("19.995"));
            price.setPriceStd(new BigDecimal("17.9955"));
            price.setPriceLimit(BigDecimal.ZERO);
            price.saveEx();
            record("productPrice", price);
            commit();
            MOrderLine orderLine = new MOrderLine(order);
            orderLine.setLine(10);
            orderLine.setProduct(product);
            orderLine.setQty(new BigDecimal("3"));
            orderLine.setPriceList(new BigDecimal("19.995"));
            orderLine.setPrice(new BigDecimal("17.9955"));
            orderLine.setDatePromised(businessDate);
            orderLine.setC_Tax_ID(DictionaryIDs.C_Tax.PST.id);
            orderLine.saveEx();
            complete("order", order);
            commit();
            order.load(trx);
            orderLine.load(trx);
            fact("order.total", order.getGrandTotal());
            fact("order.net", order.getTotalLines());
            fact("order.reserved", orderLine.getQtyReserved());
            fact("order.priceList", orderLine.getPriceList());
            fact("order.priceActual", orderLine.getPriceActual());
            fact("order.discount", orderLine.getDiscount());
            fact("order.taxId", orderLine.getC_Tax_ID());
            fact("order.taxRate", new MTax(ctx, orderLine.getC_Tax_ID(), trx).getRate());

            MInOut firstShipment = new MInOut(order,
                DictionaryIDs.C_DocType.MM_SHIPMENT.id, businessDate);
            firstShipment.saveEx();
            MInOutLine firstShipmentLine = new MInOutLine(firstShipment);
            firstShipmentLine.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id,
                new BigDecimal("1"));
            firstShipmentLine.setQty(new BigDecimal("1"));
            firstShipmentLine.saveEx();
            complete("firstShipment", firstShipment);
            commit();
            orderLine.load(trx);
            fact("partial.delivered", orderLine.getQtyDelivered());
            fact("partial.reserved", orderLine.getQtyReserved());
            fact("partial.stock", stock(product.get_ID(), trx));

            MInOut shipment = new MInOut(order,
                DictionaryIDs.C_DocType.MM_SHIPMENT.id, businessDate);
            Timestamp fractional = Timestamp.valueOf("2026-09-26 12:34:56.123456");
            shipment.setShipDate(fractional);
            fact("shipment.shipDate.input", fractional);
            shipment.saveEx();
            MInOutLine shipmentLine = new MInOutLine(shipment);
            shipmentLine.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id,
                new BigDecimal("2"));
            shipmentLine.setQty(new BigDecimal("2"));
            shipmentLine.saveEx();
            complete("shipment", shipment);
            commit();
            shipment.load(trx);
            orderLine.load(trx);
            fact("shipment.shipDate.readback", shipment.getShipDate());
            fact("shipment.delivered", orderLine.getQtyDelivered());

            // One aggregate order-linked invoice line covers both completed deliveries.
            MInvoice invoice = new MInvoice(shipment, businessDate);
            invoice.saveEx();
            MInvoiceLine invoiceLine = new MInvoiceLine(invoice);
            invoiceLine.setOrderLine(orderLine);
            invoiceLine.setQty(new BigDecimal("3"));
            invoiceLine.saveEx();
            complete("invoice", invoice);
            post(invoice, schemas);
            commit();
            invoice.load(trx);
            invoiceLine.load(trx);
            fact("invoice.total", invoice.getGrandTotal());

            MPayment payment = new MPayment(ctx, 0, trx);
            payment.setC_DocType_ID(true);
            int bank = DB.getSQLValueEx(trx,
                "SELECT C_BankAccount_ID FROM C_BankAccount WHERE AD_Client_ID=? AND IsDefault='Y'",
                getAD_Client_ID());
            require(bank > 0, "No default bank account");
            payment.setC_BankAccount_ID(bank);
            payment.setC_BPartner_ID(customer.get_ID());
            payment.setC_Invoice_ID(invoice.get_ID());
            payment.setDateTrx(businessDate);
            payment.setDateAcct(businessDate);
            payment.setTenderType(MPayment.TENDERTYPE_DirectDeposit);
            payment.setPayAmt(invoice.getGrandTotal());
            payment.setC_Currency_ID(invoice.getC_Currency_ID());
            payment.saveEx();
            complete("payment", payment);
            post(payment, schemas);
            MAllocationHdr[] paymentAllocations = MAllocationHdr.getOfInvoice(ctx, invoice.get_ID(), trx);
            for (MAllocationHdr allocation : paymentAllocations) {
                post(allocation, schemas);
            }
            commit();
            payment.load(trx);
            invoice.load(trx);
            fact("payment.amount", payment.getPayAmt());
            fact("payment.allocations", MAllocationHdr.getOfInvoice(ctx, invoice.get_ID(), trx).length);
            fact("invoice.paid", invoice.isPaid());

            MDocType creditType = new Query(ctx, MDocType.Table_Name,
                "AD_Client_ID=? AND DocBaseType=? AND IsSOTrx='Y'", trx)
                .setParameters(getAD_Client_ID(), "ARC").setOnlyActiveRecords(true)
                .setOrderBy("IsDefault DESC, C_DocType_ID").first();
            require(creditType != null, "No sales credit memo document type");
            MInvoice credit = new MInvoice(ctx, 0, trx);
            credit.setIsSOTrx(true);
            credit.setBPartner(customer);
            credit.setC_BPartner_Location_ID(location.get_ID());
            credit.setC_DocTypeTarget_ID(creditType.get_ID());
            credit.setDateInvoiced(businessDate);
            credit.setDateAcct(businessDate);
            credit.setM_PriceList_ID(invoice.getM_PriceList_ID());
            credit.setC_Currency_ID(invoice.getC_Currency_ID());
            credit.setC_PaymentTerm_ID(invoice.getC_PaymentTerm_ID());
            credit.setPaymentRule(MInvoice.PAYMENTRULE_OnCredit);
            credit.setIsTaxIncluded(invoice.isTaxIncluded());
            credit.set_ValueOfColumn("Ref_Invoice_ID", invoice.get_ID());
            credit.saveEx();
            MInvoiceLine creditLine = new MInvoiceLine(credit);
            creditLine.setLine(10);
            creditLine.setProduct(product);
            creditLine.setQty(new BigDecimal("1"));
            creditLine.setPriceList(invoiceLine.getPriceList());
            creditLine.setPrice(invoiceLine.getPriceActual());
            creditLine.setPriceLimit(invoiceLine.getPriceLimit());
            creditLine.setC_Tax_ID(invoiceLine.getC_Tax_ID());
            creditLine.saveEx();
            complete("credit", credit);
            post(credit, schemas);
            postAllocations(ctx, credit.get_ID(), trx, schemas);
            commit();
            credit.load(trx);
            fact("credit.net", credit.getTotalLines());
            fact("credit.total", credit.getGrandTotal());

            action(credit, DocAction.ACTION_Reverse_Correct);
            require(DocAction.STATUS_Reversed.equals(credit.getDocStatus()),
                "Credit memo was not reversed");
            int reversalId = credit.getReversal_ID();
            require(reversalId > 0 && reversalId != credit.get_ID(),
                "Credit memo has no distinct reversal");
            MInvoice creditReversal = new MInvoice(ctx, reversalId, trx);
            post(creditReversal, schemas);
            postAllocations(ctx, invoice.get_ID(), trx, schemas);
            postAllocations(ctx, credit.get_ID(), trx, schemas);
            postAllocations(ctx, creditReversal.get_ID(), trx, schemas);
            readAccounting(credit, schemas);
            commit();
            credit.load(trx);
            creditReversal.load(trx);
            record("creditReversal", creditReversal);
            fact("credit.finalStatus", credit.getDocStatus());
            fact("credit.reversalId", credit.getReversal_ID());
            fact("creditReversal.status", creditReversal.getDocStatus());
            fact("creditReversal.total", creditReversal.getGrandTotal());

            recovery(ctx, template);
            concurrency(ctx, customer.get_ID());
            fact("inventory.movements", DB.getSQLValueEx(trx,
                "SELECT COUNT(*) FROM M_Transaction WHERE M_Product_ID=?", product.get_ID()));
            fact("inventory.onHand", stock(product.get_ID(), trx));
            invoice.load(trx);
            fact("invoice.paid", invoice.isPaid());
            getTrx().commit(true);
            int issuesAfter = DB.getSQLValueEx(null, "SELECT COUNT(*) FROM AD_Issue");
            fact("newIssueCount", issuesAfter - issuesBefore);
            fact("status", "completed-and-committed");
        } catch (Exception | AssertionError failure) {
            fact("status", "failed");
            fact("failure", failure.toString());
            throw failure;
        } finally {
            try (var out = Files.newOutputStream(output)) {
                evidence.storeToXML(out, "Observed iDempiere operations journey");
            }
        }
    }
}



/** Public deterministic plumbing. Contains no expected business amounts or judge rules. */
final class JourneySupport {
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
