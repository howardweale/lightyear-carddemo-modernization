package org.idempiere.test;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.util.Properties;
import org.compiere.model.*;
import org.compiere.process.DocAction;
import org.compiere.process.ProcessInfo;
import org.compiere.util.*;
import org.compiere.wf.MWorkflow;
import org.junit.jupiter.api.Test;

/** Local native experiment, using the pinned application's model/workflow APIs. */
public class LightyearOperationsTest extends AbstractTestCase {
    private final Properties evidence = new Properties();
    private final Timestamp businessDate = Timestamp.valueOf("2026-09-26 00:00:00");
    private void fact(String key, Object value) { evidence.setProperty(key, String.valueOf(value)); }
    private void record(String name, PO model) {
        assertTrue(model.get_ID() > 0);
        fact(name+".id", model.get_ID()); fact(name+".uuid", model.get_UUID());
        fact(name+".saved", true);
    }
    private void complete(String name, PO model) {
        ProcessInfo result = MWorkflow.runDocumentActionWorkflow(model, DocAction.ACTION_Complete);
        assertFalse(result.isError(), name+": "+result.getSummary());
        assertTrue(model.load(getTrxName()));
        assertEquals(DocAction.STATUS_Completed, model.get_ValueAsString("DocStatus"), name);
        record(name, model); fact(name+".status", model.get_ValueAsString("DocStatus"));
    }

    @Test public void partialCreditReversalAndRecovery() throws Exception {
        Path output = Path.of(System.getProperty("lightyear.output"));
        fact("status", "started"); fact("database", DB.isOracle() ? "oracle" : "postgresql");
        try {
            Properties ctx = Env.getCtx(); String trx = getTrxName();
            int issuesBefore = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            MBPartner template = new MBPartner(ctx, DictionaryIDs.C_BPartner.JOE_BLOCK.id, trx);
            MBPartner customer = new MBPartner(ctx, 0, trx);
            customer.setValue("LY-BOUNDARY-OPERATIONS"); customer.setName("Caf\u00e9 \u6771\u4eac \u0141\u00f3d\u017a");
            customer.setDescription(""); fact("customer.name.input", customer.getName());
            fact("customer.description.input", "empty-string");
            customer.setIsCustomer(true); customer.setC_BP_Group_ID(template.getC_BP_Group_ID());
            customer.setM_PriceList_ID(template.getM_PriceList_ID());
            customer.setC_PaymentTerm_ID(template.getC_PaymentTerm_ID());
            customer.setPaymentRule(MBPartner.PAYMENTRULE_OnCredit);
            customer.saveEx(); record("customer", customer);
            customer.load(trx); fact("customer.name.readback", customer.getName());
            fact("customer.description.readback", customer.getDescription() == null ? "SQL-NULL" : customer.getDescription());
            MBPartnerLocation[] locations = template.getLocations(false);
            assertTrue(locations.length > 0);
            MBPartnerLocation location = new MBPartnerLocation(ctx, 0, trx);
            location.setC_BPartner_ID(customer.get_ID()); location.setC_Location_ID(locations[0].getC_Location_ID());
            location.setName("Evaluation location"); location.setIsBillTo(true); location.setIsShipTo(true);
            location.saveEx(); record("customerLocation", location); commit();

            MProduct product = new MProduct(ctx, 0, trx);
            product.setValue("LY-BOUNDARY-OPERATIONS"); product.setName("Lightyear Equivalence Product");
            product.setM_Product_Category_ID(DictionaryIDs.M_Product_Category.STANDARD.id);
            product.setProductType(MProduct.PRODUCTTYPE_Item); product.setIsStocked(true);
            product.setIsSold(true); product.setIsPurchased(true);
            product.setC_UOM_ID(DictionaryIDs.C_UOM.EACH.id);
            product.setC_TaxCategory_ID(DictionaryIDs.C_TaxCategory.STANDARD.id);
            product.saveEx(); record("product", product); commit();

            MInventory inventory = new MInventory(ctx, 0, trx);
            inventory.setM_Warehouse_ID(getM_Warehouse_ID()); inventory.setMovementDate(businessDate);
            inventory.setC_DocType_ID(DictionaryIDs.C_DocType.MATERIAL_PHYSICAL_INVENTORY.id);
            inventory.saveEx();
            MInventoryLine inventoryLine = new MInventoryLine(inventory, DictionaryIDs.M_Locator.HQ.id,
                product.get_ID(), 0, BigDecimal.ZERO, new BigDecimal("10"));
            inventoryLine.saveEx(); complete("openingInventory", inventory);
            fact("openingInventory.quantity", inventoryLine.getQtyCount()); commit();

            MOrder order = new MOrder(ctx, 0, trx);
            order.setBPartner(customer); order.setC_BPartner_Location_ID(location.get_ID());
            order.setBill_Location_ID(location.get_ID()); order.setM_Warehouse_ID(getM_Warehouse_ID());
            order.setC_DocTypeTarget_ID(MOrder.DocSubTypeSO_Standard);
            order.setDateOrdered(businessDate); order.setDatePromised(businessDate);
            order.setDeliveryRule(MOrder.DELIVERYRULE_Availability);
            order.setPaymentRule(MOrder.PAYMENTRULE_OnCredit); order.saveEx();
            MPriceListVersion version = MPriceList.get(ctx, order.getM_PriceList_ID(), trx).getPriceListVersion(businessDate);
            assertNotNull(version);
            MProductPrice price = new MProductPrice(ctx, version.get_ID(), product.get_ID(), trx);
            price.setPriceList(new BigDecimal("19.995")); price.setPriceStd(new BigDecimal("17.9955"));
            price.setPriceLimit(new BigDecimal("0")); price.saveEx(); record("productPrice", price); commit();
            MOrderLine orderLine = new MOrderLine(order);
            orderLine.setLine(10); orderLine.setProduct(product); orderLine.setQty(new BigDecimal("3"));
            orderLine.setPriceList(new BigDecimal("19.995")); orderLine.setPrice(new BigDecimal("17.9955")); orderLine.setDatePromised(businessDate);
            orderLine.setC_Tax_ID(DictionaryIDs.C_Tax.PST.id); orderLine.saveEx(); complete("order", order); commit();
            fact("order.total", order.getGrandTotal()); fact("order.net", order.getTotalLines());
            orderLine.load(trx); fact("order.reserved", orderLine.getQtyReserved());
            fact("order.priceList", orderLine.getPriceList()); fact("order.priceActual", orderLine.getPriceActual());
            fact("order.discount", orderLine.getDiscount()); fact("order.taxId", orderLine.getC_Tax_ID());
            fact("order.taxRate", new MTax(ctx, orderLine.getC_Tax_ID(), trx).getRate());
            assertEquals(0, new BigDecimal("58.04").compareTo(order.getGrandTotal()));
            assertEquals(0, new BigDecimal("53.99").compareTo(order.getTotalLines()));

            MInOut first = new MInOut(order, DictionaryIDs.C_DocType.MM_SHIPMENT.id, businessDate);
            first.saveEx(); MInOutLine firstLine = new MInOutLine(first);
            firstLine.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id, BigDecimal.ONE);
            firstLine.setQty(BigDecimal.ONE); firstLine.saveEx(); complete("firstShipment", first); commit();
            orderLine.load(trx); fact("partial.delivered", orderLine.getQtyDelivered());
            fact("partial.reserved", orderLine.getQtyReserved());
            fact("partial.stock", DB.getSQLValueBDEx(trx, "SELECT SUM(QtyOnHand) FROM M_StorageOnHand WHERE M_Product_ID=?", product.get_ID()));
            assertEquals(0, BigDecimal.ONE.compareTo(orderLine.getQtyDelivered()));
            assertEquals(0, new BigDecimal("2").compareTo(orderLine.getQtyReserved()));
            MInOut shipment = new MInOut(order, DictionaryIDs.C_DocType.MM_SHIPMENT.id, businessDate);
            shipment.saveEx(); MInOutLine shipmentLine = new MInOutLine(shipment);
            shipmentLine.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id, new BigDecimal("2"));
            shipmentLine.setQty(new BigDecimal("2")); shipmentLine.saveEx(); complete("shipment", shipment); commit();
            orderLine.load(trx); fact("shipment.delivered", orderLine.getQtyDelivered());
            assertEquals(0, new BigDecimal("3").compareTo(orderLine.getQtyDelivered()));

            MInvoice invoice = new MInvoice(order, 0, businessDate);
            invoice.saveEx(); MInvoiceLine invoiceLine = new MInvoiceLine(invoice);
            invoiceLine.setOrderLine(orderLine); invoiceLine.setQty(new BigDecimal("3"));
            invoiceLine.saveEx(); complete("invoice", invoice); commit();
            fact("invoice.total", invoice.getGrandTotal());
            assertEquals(0, order.getGrandTotal().compareTo(invoice.getGrandTotal()));

            MPayment payment = new MPayment(ctx, 0, trx);
            payment.setC_DocType_ID(true);
            int bank = DB.getSQLValueEx(trx, "SELECT C_BankAccount_ID FROM C_BankAccount WHERE AD_Client_ID=? AND IsDefault='Y'", getAD_Client_ID());
            assertTrue(bank > 0); payment.setC_BankAccount_ID(bank);
            payment.setC_BPartner_ID(customer.get_ID()); payment.setC_Invoice_ID(invoice.get_ID());
            payment.setDateTrx(businessDate); payment.setDateAcct(businessDate);
            payment.setTenderType(MPayment.TENDERTYPE_DirectDeposit);
            payment.setPayAmt(invoice.getGrandTotal()); payment.setC_Currency_ID(invoice.getC_Currency_ID());
            payment.saveEx(); complete("payment", payment);
            fact("payment.amount", payment.getPayAmt());
            invoice.load(trx); fact("invoice.paid", invoice.isPaid()); assertTrue(invoice.isPaid());
            MAllocationHdr[] allocations = MAllocationHdr.getOfInvoice(ctx, invoice.get_ID(), trx);
            assertTrue(allocations.length > 0); fact("payment.allocations", allocations.length);
            int movements = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM M_Transaction WHERE M_Product_ID=?", product.get_ID());
            fact("inventory.movements", movements); assertTrue(movements >= 2);
            BigDecimal balance = DB.getSQLValueBDEx(trx, "SELECT SUM(QtyOnHand) FROM M_StorageOnHand WHERE M_Product_ID=?", product.get_ID());
            fact("inventory.onHand", balance); assertEquals(0, new BigDecimal("7").compareTo(balance));
            commit();
            MInvoice credit = new MInvoice(order, DictionaryIDs.C_DocType.AR_CREDIT_MEMO.id, businessDate);
            credit.setRef_Invoice_ID(invoice.get_ID()); credit.saveEx();
            MInvoiceLine creditLine = new MInvoiceLine(credit);
            creditLine.setOrderLine(orderLine); creditLine.setQty(BigDecimal.ONE); creditLine.saveEx();
            complete("credit", credit); commit();
            fact("credit.net", credit.getTotalLines()); fact("credit.total", credit.getGrandTotal());
            assertEquals(0, new BigDecimal("19.35").compareTo(credit.getGrandTotal()));
            ProcessInfo reverse = MWorkflow.runDocumentActionWorkflow(credit, DocAction.ACTION_Reverse_Correct);
            assertFalse(reverse.isError(), reverse.getSummary()); credit.load(trx);
            assertEquals(DocAction.STATUS_Reversed, credit.getDocStatus());
            fact("credit.finalStatus", credit.getDocStatus()); fact("credit.reversalId", credit.getReversal_ID());
            MInvoice reversing = new MInvoice(ctx, credit.getReversal_ID(), trx);
            record("creditReversal", reversing); fact("creditReversal.status", reversing.getDocStatus());
            fact("creditReversal.total", reversing.getGrandTotal());
            assertEquals(0, credit.getGrandTotal().add(reversing.getGrandTotal()).compareTo(BigDecimal.ZERO));
            commit();
            recovery(ctx, customer);
            concurrency(ctx, customer);
            getTrx().commit(true);
            int issuesAfter = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            fact("newIssueCount", issuesAfter-issuesBefore); assertEquals(issuesBefore, issuesAfter);
            fact("status", "completed-and-committed");
        } catch (Exception | AssertionError failure) {
            fact("status", "failed"); fact("failure", failure.toString()); throw failure;
        } finally {
            try (var out = Files.newOutputStream(output)) { evidence.storeToXML(out, "Observed iDempiere application journey"); }
        }
    }
    private void recovery(Properties ctx, MBPartner template) throws Exception {
        String name = Trx.createTrxName("LYRecovery_"); Trx transaction = Trx.get(name, true);
        transaction.start(); boolean injected = false;
        try {
            MBPartner draft = new MBPartner(ctx, 0, name);
            draft.setValue("LY-BOUNDARY-RETRY"); draft.setName("Retry boundary customer");
            draft.setC_BP_Group_ID(template.getC_BP_Group_ID()); draft.setIsCustomer(true); draft.saveEx();
            fact("recovery.rolledBackId", draft.get_ID());
            throw new IllegalStateException("LIGHTYEAR_INJECTED_BEFORE_COMMIT");
        } catch (IllegalStateException expected) {
            assertEquals("LIGHTYEAR_INJECTED_BEFORE_COMMIT", expected.getMessage());
            injected = true; transaction.rollback(true);
        } finally { transaction.close(); }
        assertTrue(injected);
        int absent = DB.getSQLValueEx(null, "SELECT COUNT(*) FROM C_BPartner WHERE Value='LY-BOUNDARY-RETRY'");
        fact("recovery.rowsAfterRollback", absent); assertEquals(0, absent);
        MBPartner retry = new MBPartner(ctx, 0, getTrxName());
        retry.setValue("LY-BOUNDARY-RETRY"); retry.setName("Retry boundary customer");
        retry.setC_BP_Group_ID(template.getC_BP_Group_ID()); retry.setIsCustomer(true); retry.saveEx();
        record("recoveryCustomer", retry); commit();
        // The retry caller explicitly checks the logical key before redispatching.
        int found = DB.getSQLValueEx(null, "SELECT C_BPartner_ID FROM C_BPartner WHERE Value='LY-BOUNDARY-RETRY'");
        assertEquals(retry.get_ID(), found); fact("recovery.repeatedRequest", "existing-record-returned");
        fact("recovery.rowsAfterRepeatedRequest", DB.getSQLValueEx(null, "SELECT COUNT(*) FROM C_BPartner WHERE Value='LY-BOUNDARY-RETRY'"));
    }

    private void concurrency(Properties ctx, MBPartner customer) throws Exception {
        customer.load(getTrxName()); customer.setSO_CreditLimit(new BigDecimal("100.00")); customer.saveEx(); commit();
        var locked = new java.util.concurrent.CountDownLatch(1);
        var attempting = new java.util.concurrent.CountDownLatch(1);
        var release = new java.util.concurrent.CountDownLatch(1);
        var pool = java.util.concurrent.Executors.newFixedThreadPool(2);
        try {
            var first = pool.submit(() -> creditIncrement(ctx, customer.get_ID(), true, locked, attempting, release));
            assertTrue(locked.await(10, java.util.concurrent.TimeUnit.SECONDS));
            var second = pool.submit(() -> creditIncrement(ctx, customer.get_ID(), false, locked, attempting, release));
            assertTrue(attempting.await(10, java.util.concurrent.TimeUnit.SECONDS));
            Thread.sleep(300); assertFalse(second.isDone(), "Second update should wait for the held row lock");
            fact("concurrency.lockingApi", "Query.setForUpdate(true).list-single-primary-key");
            fact("concurrency.secondWaitedForLock", true); release.countDown();
            BigDecimal a = first.get(20, java.util.concurrent.TimeUnit.SECONDS);
            BigDecimal b = second.get(20, java.util.concurrent.TimeUnit.SECONDS);
            fact("concurrency.firstValue", a); fact("concurrency.secondValue", b);
            assertEquals(0, new BigDecimal("100.01").compareTo(a));
            assertEquals(0, new BigDecimal("100.02").compareTo(b));
            customer.load(getTrxName()); fact("concurrency.finalCreditLimit", customer.getSO_CreditLimit());
            assertEquals(0, new BigDecimal("100.02").compareTo(customer.getSO_CreditLimit()));
        } finally { release.countDown(); pool.shutdownNow(); pool.awaitTermination(25, java.util.concurrent.TimeUnit.SECONDS); }
    }

    private BigDecimal creditIncrement(Properties source, int id, boolean first,
            java.util.concurrent.CountDownLatch locked, java.util.concurrent.CountDownLatch attempting,
            java.util.concurrent.CountDownLatch release) throws Exception {
        Properties ctx = new Properties(); ctx.putAll(source);
        org.adempiere.util.ServerContext.setCurrentInstance(ctx);
        String name = Trx.createTrxName("LYConcurrent_"); Trx transaction = Trx.get(name, true);
        transaction.start();
        try {
            if (!first) attempting.countDown();
            java.util.List<MBPartner> selected = new Query(ctx, MBPartner.Table_Name, "C_BPartner_ID=?", name)
                .setParameters(id).setForUpdate(true).list();
            assertEquals(1, selected.size()); MBPartner row = selected.get(0);
            if (first) { locked.countDown(); assertTrue(release.await(15, java.util.concurrent.TimeUnit.SECONDS)); }
            BigDecimal value = row.getSO_CreditLimit().add(new BigDecimal("0.01"));
            row.setSO_CreditLimit(value); row.saveEx(); transaction.commit(true); return value;
        } finally { if (transaction.isActive()) transaction.rollback(); transaction.close(); org.adempiere.util.ServerContext.dispose(); }
    }

}
