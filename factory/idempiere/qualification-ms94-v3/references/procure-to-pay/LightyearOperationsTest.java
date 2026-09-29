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
import org.compiere.util.DB;
import org.compiere.util.Env;
import org.compiere.wf.MWorkflow;
import org.junit.jupiter.api.Test;

public class LightyearOperationsTest extends AbstractTestCase {
    private final Properties evidence = new Properties();
    private final Timestamp businessDate = Timestamp.valueOf("2026-09-26 00:00:00");

    private void fact(String key, Object value) {
        JourneySupport.fact(evidence, key, value);
    }

    // Only named lifecycle fields may be replaced; ordinary duplicate facts fail.
    private void lifecycle(String key, Object value) {
        if (evidence.containsKey(key)) JourneySupport.replaceFact(evidence, key, value);
        else JourneySupport.fact(evidence, key, value);
    }

    private void record(String name, PO model) {
        lifecycle(name + ".saved", true);
        lifecycle(name + ".id", model.get_ID());
        lifecycle(name + ".uuid", model.get_UUID());
    }

    private void complete(String name, PO model) {
        ProcessInfo result = MWorkflow.runDocumentActionWorkflow(model, DocAction.ACTION_Complete);
        assertNotNull(result, name + " workflow result");
        assertFalse(result.isError(), name + " workflow failed");
        assertTrue(model.load(getTrxName()), name + " reload");
        assertEquals(DocAction.STATUS_Completed, model.get_ValueAsString("DocStatus"), name);
        assertTrue(model.get_ValueAsBoolean("Processed"), name + " processed");
        record(name, model);
        fact(name + ".status", model.get_ValueAsString("DocStatus"));
    }

    private int documentType(String baseType) {
        int id = DB.getSQLValueEx(getTrxName(),
            "SELECT MIN(C_DocType_ID) FROM C_DocType "
            + "WHERE AD_Client_ID=? AND IsActive='Y' AND IsSOTrx='N' AND DocBaseType=?",
            getAD_Client_ID(), baseType);
        assertTrue(id > 0, "Missing document type: " + baseType);
        return id;
    }

    private BigDecimal onHand(int productId) {
        return DB.getSQLValueBDEx(getTrxName(),
            "SELECT COALESCE(SUM(QtyOnHand),0) FROM M_StorageOnHand WHERE M_Product_ID=?",
            productId);
    }

    private void post(PO document, MAcctSchema[] schemas) {
        JourneySupport.postOnce(document, schemas);
    }

    @Test
    public void procureToPay() throws Exception {
        Path output = Path.of(System.getProperty("lightyear.output"));
        fact("database", DB.isOracle() ? "oracle" : "postgresql");
        lifecycle("status", "started");
        try {
            Properties ctx = Env.getCtx();
            String trx = getTrxName();
            int issuesBefore = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            BigDecimal quantity = new BigDecimal("3");
            BigDecimal priceListAmount = new BigDecimal("19.995");
            BigDecimal priceActual = new BigDecimal("17.9955");

            MBPartner template = new MBPartner(ctx, DictionaryIDs.C_BPartner.JOE_BLOCK.id, trx);
            MBPartnerLocation[] templateLocations = template.getLocations(false);
            assertTrue(templateLocations.length > 0, "Fixture location required");

            int priceListId = DB.getSQLValueEx(trx,
                "SELECT MIN(p.M_PriceList_ID) FROM M_PriceList p "
                + "WHERE p.AD_Client_ID=? AND p.IsActive='Y' AND p.IsSOPriceList='N' "
                + "AND EXISTS (SELECT 1 FROM M_PriceList_Version v "
                + "WHERE v.M_PriceList_ID=p.M_PriceList_ID AND v.IsActive='Y' AND v.ValidFrom<=?)",
                getAD_Client_ID(), businessDate);
            assertTrue(priceListId > 0, "Purchase price list required");
            MPriceList purchasePriceList = MPriceList.get(ctx, priceListId, trx);
            MPriceListVersion version = purchasePriceList.getPriceListVersion(businessDate);
            assertNotNull(version, "Purchase price list version required");

            int paymentTermId = template.getC_PaymentTerm_ID();
            if (paymentTermId <= 0) {
                paymentTermId = DB.getSQLValueEx(trx,
                    "SELECT MIN(C_PaymentTerm_ID) FROM C_PaymentTerm "
                    + "WHERE AD_Client_ID=? AND IsActive='Y' AND IsDefault='Y'",
                    getAD_Client_ID());
            }
            assertTrue(paymentTermId > 0, "Payment term required");

            MBPartner vendor = new MBPartner(ctx, 0, trx);
            vendor.setValue("LY-PROCUREMENT");
            vendor.setName("Caf\u00e9 \u6771\u4eac \u0141\u00f3d\u017a");
            vendor.setDescription("");
            vendor.setIsVendor(true);
            vendor.setIsCustomer(false);
            vendor.setC_BP_Group_ID(template.getC_BP_Group_ID());
            vendor.setPO_PriceList_ID(priceListId);
            vendor.setPO_PaymentTerm_ID(paymentTermId);
            vendor.setPaymentRulePO(MBPartner.PAYMENTRULEPO_OnCredit);
            vendor.saveEx();
            assertTrue(vendor.load(trx));
            record("vendor", vendor);

            MBPartnerLocation vendorLocation = new MBPartnerLocation(ctx, 0, trx);
            vendorLocation.setC_BPartner_ID(vendor.get_ID());
            vendorLocation.setC_Location_ID(templateLocations[0].getC_Location_ID());
            vendorLocation.setName("Evaluation vendor location");
            vendorLocation.setIsBillTo(true);
            vendorLocation.setIsShipTo(true);
            vendorLocation.setIsPayFrom(true);
            vendorLocation.setIsRemitTo(true);
            vendorLocation.saveEx();
            assertTrue(vendorLocation.load(trx));
            record("vendorLocation", vendorLocation);
            commit();

            MProduct product = new MProduct(ctx, 0, trx);
            product.setValue("LY-PROCUREMENT");
            product.setName("Lightyear Procurement Product");
            product.setM_Product_Category_ID(DictionaryIDs.M_Product_Category.STANDARD.id);
            product.setProductType(MProduct.PRODUCTTYPE_Item);
            product.setIsStocked(true);
            product.setIsPurchased(true);
            product.setIsSold(false);
            product.setC_UOM_ID(DictionaryIDs.C_UOM.EACH.id);
            product.setC_TaxCategory_ID(DictionaryIDs.C_TaxCategory.STANDARD.id);
            product.saveEx();
            assertTrue(product.load(trx));
            record("product", product);
            assertEquals(0, onHand(product.get_ID()).compareTo(BigDecimal.ZERO), "Opening stock");

            MProductPrice productPrice = new MProductPrice(ctx, version.get_ID(), product.get_ID(), trx);
            productPrice.setPriceList(priceListAmount);
            productPrice.setPriceStd(priceActual);
            productPrice.setPriceLimit(BigDecimal.ZERO);
            productPrice.saveEx();
            record("productPrice", productPrice);
            commit();

            MOrder purchaseOrder = new MOrder(ctx, 0, trx);
            purchaseOrder.setIsSOTrx(false);
            purchaseOrder.setBPartner(vendor);
            purchaseOrder.setC_BPartner_Location_ID(vendorLocation.get_ID());
            purchaseOrder.setBill_Location_ID(vendorLocation.get_ID());
            purchaseOrder.setM_Warehouse_ID(getM_Warehouse_ID());
            purchaseOrder.setC_DocTypeTarget_ID(documentType("POO"));
            purchaseOrder.setDateOrdered(businessDate);
            purchaseOrder.setDateAcct(businessDate);
            purchaseOrder.setDatePromised(businessDate);
            purchaseOrder.setM_PriceList_ID(priceListId);
            purchaseOrder.setC_Currency_ID(purchasePriceList.getC_Currency_ID());
            purchaseOrder.setIsTaxIncluded(purchasePriceList.isTaxIncluded());
            purchaseOrder.setC_PaymentTerm_ID(paymentTermId);
            purchaseOrder.setPaymentRule(MOrder.PAYMENTRULE_OnCredit);
            purchaseOrder.setDeliveryRule(MOrder.DELIVERYRULE_CompleteOrder);
            purchaseOrder.setInvoiceRule(MOrder.INVOICERULE_Immediate);
            purchaseOrder.saveEx();

            MOrderLine orderLine = new MOrderLine(purchaseOrder);
            orderLine.setLine(10);
            orderLine.setProduct(product);
            orderLine.setQty(quantity);
            orderLine.setPriceList(priceListAmount);
            orderLine.setPrice(priceActual);
            orderLine.setDatePromised(businessDate);
            orderLine.setC_Tax_ID(DictionaryIDs.C_Tax.PST.id);
            orderLine.saveEx();
            complete("purchaseOrder", purchaseOrder);
            commit();
            assertTrue(purchaseOrder.load(trx));
            assertTrue(orderLine.load(trx));
            fact("purchaseOrder.net", purchaseOrder.getTotalLines());
            fact("purchaseOrder.total", purchaseOrder.getGrandTotal());
            fact("purchaseOrder.priceActual", orderLine.getPriceActual());
            fact("purchaseOrder.discount", orderLine.getDiscount());

            MInOut receipt = new MInOut(purchaseOrder, documentType("MMR"), businessDate);
            receipt.setMovementDate(businessDate);
            receipt.setDateAcct(businessDate);
            receipt.saveEx();
            MInOutLine receiptLine = new MInOutLine(receipt);
            receiptLine.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id, quantity);
            receiptLine.setQty(quantity);
            receiptLine.saveEx();
            complete("receipt", receipt);
            commit();
            assertTrue(receiptLine.load(trx));
            fact("receipt.quantity", receiptLine.getMovementQty());

            MInvoice vendorInvoice = new MInvoice(receipt, businessDate);
            vendorInvoice.setIsSOTrx(false);
            vendorInvoice.setC_DocTypeTarget_ID(documentType("API"));
            vendorInvoice.setDateInvoiced(businessDate);
            vendorInvoice.setDateAcct(businessDate);
            vendorInvoice.saveEx();
            MInvoiceLine invoiceLine = new MInvoiceLine(vendorInvoice);
            invoiceLine.setShipLine(receiptLine);
            invoiceLine.setQty(receiptLine.getMovementQty());
            invoiceLine.saveEx();
            complete("vendorInvoice", vendorInvoice);
            commit();
            assertTrue(vendorInvoice.load(trx));
            fact("vendorInvoice.total", vendorInvoice.getGrandTotal());

            MAcctSchema[] schemas = MAcctSchema.getClientAcctSchema(ctx, getAD_Client_ID());
            assertTrue(schemas.length > 0, "Accounting schema required");
            post(vendorInvoice, schemas);
            commit();

            int bankAccountId = DB.getSQLValueEx(trx,
                "SELECT MIN(C_BankAccount_ID) FROM C_BankAccount "
                + "WHERE AD_Client_ID=? AND IsActive='Y' AND IsDefault='Y' AND C_Currency_ID=?",
                getAD_Client_ID(), vendorInvoice.getC_Currency_ID());
            if (bankAccountId <= 0) {
                bankAccountId = DB.getSQLValueEx(trx,
                    "SELECT MIN(C_BankAccount_ID) FROM C_BankAccount "
                    + "WHERE AD_Client_ID=? AND IsActive='Y' AND C_Currency_ID=?",
                    getAD_Client_ID(), vendorInvoice.getC_Currency_ID());
            }
            assertTrue(bankAccountId > 0, "Bank account required");

            MPayment vendorPayment = new MPayment(ctx, 0, trx);
            vendorPayment.setC_DocType_ID(false);
            vendorPayment.setIsReceipt(false);
            vendorPayment.setC_BankAccount_ID(bankAccountId);
            vendorPayment.setC_BPartner_ID(vendor.get_ID());
            vendorPayment.setC_Invoice_ID(vendorInvoice.get_ID());
            vendorPayment.setDateTrx(businessDate);
            vendorPayment.setDateAcct(businessDate);
            vendorPayment.setTenderType(MPayment.TENDERTYPE_DirectDeposit);
            vendorPayment.setC_Currency_ID(vendorInvoice.getC_Currency_ID());
            vendorPayment.setPayAmt(vendorInvoice.getGrandTotal());
            vendorPayment.saveEx();
            complete("vendorPayment", vendorPayment);
            commit();

            post(vendorPayment, schemas);
            MAllocationHdr[] allocations = MAllocationHdr.getOfInvoice(ctx, vendorInvoice.get_ID(), trx);
            assertTrue(allocations.length > 0, "Invoice allocation required");
            for (MAllocationHdr allocation : allocations) {
                assertTrue(allocation.load(trx));
                assertEquals(DocAction.STATUS_Completed, allocation.getDocStatus(), "Allocation completed");
                post(allocation, schemas);
            }
            getTrx().commit(true);

            assertTrue(vendorInvoice.load(trx));
            assertTrue(vendorPayment.load(trx));
            fact("vendorInvoice.paid", vendorInvoice.isPaid());
            fact("vendorPayment.amount", vendorPayment.getPayAmt());
            fact("inventory.onHand", onHand(product.get_ID()));
            assertTrue(vendorInvoice.isPaid(), "Vendor invoice settled");
            assertFalse(vendorPayment.isReceipt(), "Outbound vendor payment");
            int issuesAfter = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            fact("newIssueCount", issuesAfter - issuesBefore);
            lifecycle("status", "completed-and-committed");
        } catch (Exception | AssertionError failure) {
            lifecycle("status", "failed");
            throw failure;
        } finally {
            try (var out = Files.newOutputStream(output)) {
                evidence.storeToXML(out, "Observed iDempiere procurement journey");
            }
        }
    }
}

/** Deterministic plumbing; no business expectations. Review candidate v3. */
final class JourneySupport {
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
