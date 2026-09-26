package org.idempiere.test;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Timestamp;
import java.util.Properties;
import org.compiere.acct.Doc;
import org.compiere.model.*;
import org.compiere.process.DocAction;
import org.compiere.process.ProcessInfo;
import org.compiere.util.*;
import org.compiere.wf.MWorkflow;
import org.junit.jupiter.api.Test;

public class LightyearPartialInvoiceTest extends AbstractTestCase {
    private final Properties evidence = new Properties();
    private final Timestamp businessDate = Timestamp.valueOf("2026-09-26 00:00:00");

    private void fact(String key, Object value) {
        evidence.setProperty(key, String.valueOf(value));
    }

    private void amount(String expected, BigDecimal actual) {
        assertNotNull(actual);
        assertEquals(0, new BigDecimal(expected).compareTo(actual));
    }

    private void record(String name, PO model) {
        assertTrue(model.get_ID() > 0, name);
        fact(name + ".id", model.get_ID());
        fact(name + ".uuid", model.get_UUID());
        fact(name + ".saved", true);
        fact(name + ".status", model instanceof DocAction
            ? ((DocAction) model).getDocStatus() : "saved");
    }

    private void complete(String name, PO model) {
        ProcessInfo result = MWorkflow.runDocumentActionWorkflow(model, DocAction.ACTION_Complete);
        assertNotNull(result, name);
        assertFalse(result.isError(), name + ": " + result.getSummary());
        assertTrue(model.load(getTrxName()), name);
        assertEquals(DocAction.STATUS_Completed, model.get_ValueAsString("DocStatus"), name);
        record(name, model);
        commit();
    }

    private void postAndCommit(PO model) {
        String error = model.get_ValueAsBoolean("Posted") ? null : Doc.postImmediate(MAcctSchema.getClientAcctSchema(Env.getCtx(), getAD_Client_ID()),
            model.get_Table_ID(), model.get_ID(), false, getTrxName());
        assertNull(error, "Application posting failed: " + error);
        assertTrue(model.load(getTrxName()));
        assertTrue(model.get_ValueAsBoolean("Posted"), "Document must be posted");
        commit();
        assertTrue(model.load(getTrxName()));
        assertTrue(model.get_ValueAsBoolean("Posted"), "Committed document must be posted");
    }

    private MInOutLine ship(String name, MOrder order, MOrderLine orderLine,
            BigDecimal quantity) {
        MInOut shipment = new MInOut(order, DictionaryIDs.C_DocType.MM_SHIPMENT.id, businessDate);
        shipment.setDateAcct(businessDate);
        shipment.saveEx();
        MInOutLine line = new MInOutLine(shipment);
        line.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id, quantity);
        line.setQty(quantity);
        line.saveEx();
        complete(name, shipment);
        assertTrue(line.load(getTrxName()));
        assertEquals(0, quantity.compareTo(line.getMovementQty()));
        return line;
    }

    private MInvoice invoice(String name, MOrder order, MOrderLine orderLine,
            MInOutLine shipmentLine, BigDecimal quantity, String net, String gross) {
        MInvoice invoice = new MInvoice(order, 0, businessDate);
        invoice.setDateAcct(businessDate);
        invoice.saveEx();
        MInvoiceLine line = new MInvoiceLine(invoice);
        line.setOrderLine(orderLine);
        line.setM_InOutLine_ID(shipmentLine.get_ID());
        line.setQty(quantity);
        line.saveEx();
        complete(name, invoice);
        postAndCommit(invoice);
        assertTrue(line.load(getTrxName()));
        assertEquals(0, quantity.compareTo(line.getQtyInvoiced()));
        fact(name + ".total", invoice.getGrandTotal());
        fact(name + ".net", invoice.getTotalLines());
        amount(net, invoice.getTotalLines());
        amount(gross, invoice.getGrandTotal());
        return invoice;
    }

    private void pay(String name, MBPartner customer, MInvoice invoice, int bank) {
        MPayment payment = new MPayment(Env.getCtx(), 0, getTrxName());
        payment.setC_DocType_ID(true);
        payment.setC_BankAccount_ID(bank);
        payment.setC_BPartner_ID(customer.get_ID());
        payment.setC_Invoice_ID(invoice.get_ID());
        payment.setDateTrx(businessDate);
        payment.setDateAcct(businessDate);
        payment.setTenderType(MPayment.TENDERTYPE_DirectDeposit);
        payment.setC_Currency_ID(invoice.getC_Currency_ID());
        payment.setPayAmt(invoice.getGrandTotal());
        payment.saveEx();
        complete(name, payment);
        postAndCommit(payment);
        fact(name + ".amount", payment.getPayAmt());
        assertEquals(0, invoice.getGrandTotal().compareTo(payment.getPayAmt()));
        assertTrue(invoice.load(getTrxName()));
        assertTrue(invoice.isPaid());
        assertTrue(invoice.get_ValueAsBoolean("Posted"));
        assertTrue(MAllocationHdr.getOfInvoice(Env.getCtx(), invoice.get_ID(), getTrxName()).length > 0);
        commit();
    }

    @Test
    public void partialInvoicing() throws Exception {
        Path output = Path.of(System.getProperty("lightyear.output"));
        fact("status", "failed");
        fact("database", DB.isOracle() ? "oracle" : "postgresql");
        try {
            Properties ctx = Env.getCtx();
            String trx = getTrxName();
            int issuesBefore = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            MBPartner template = new MBPartner(ctx, DictionaryIDs.C_BPartner.JOE_BLOCK.id, trx);
            MBPartner customer = new MBPartner(ctx, 0, trx);
            customer.setValue("LY-PARTIAL-INVOICE");
            customer.setName("Caf\u00e9 \u6771\u4eac \u0141\u00f3d\u017a");
            customer.setDescription("");
            fact("customer.name.input", customer.getName());
            fact("customer.description.input", "empty-string");
            customer.setIsCustomer(true);
            customer.setC_BP_Group_ID(template.getC_BP_Group_ID());
            customer.setM_PriceList_ID(template.getM_PriceList_ID());
            customer.setC_PaymentTerm_ID(template.getC_PaymentTerm_ID());
            customer.setPaymentRule(MBPartner.PAYMENTRULE_OnCredit);
            customer.saveEx();
            record("customer", customer);
            assertTrue(customer.load(trx));
            fact("customer.name.readback", customer.getName());
            fact("customer.description.readback", customer.getDescription() == null
                ? "SQL-NULL" : customer.getDescription());
            assertEquals("Caf\u00e9 \u6771\u4eac \u0141\u00f3d\u017a", customer.getName());
            assertNull(customer.getDescription());
            MBPartnerLocation[] locations = template.getLocations(false);
            assertTrue(locations.length > 0);
            MBPartnerLocation location = new MBPartnerLocation(ctx, 0, trx);
            location.setC_BPartner_ID(customer.get_ID());
            location.setC_Location_ID(locations[0].getC_Location_ID());
            location.setName("Evaluation location");
            location.setIsBillTo(true);
            location.setIsShipTo(true);
            location.saveEx();
            record("customerLocation", location);
            commit();

            MProduct product = new MProduct(ctx, 0, trx);
            product.setValue("LY-PARTIAL-INVOICE");
            product.setName("Lightyear Partial Invoice Product");
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
            MInventoryLine inventoryLine = new MInventoryLine(inventory, DictionaryIDs.M_Locator.HQ.id,
                product.get_ID(), 0, BigDecimal.ZERO, new BigDecimal("10"));
            inventoryLine.saveEx();
            complete("openingInventory", inventory);
            amount("10", DB.getSQLValueBDEx(trx,
                "SELECT SUM(QtyOnHand) FROM M_StorageOnHand WHERE M_Product_ID=?", product.get_ID()));

            MOrder order = new MOrder(ctx, 0, trx);
            order.setBPartner(customer);
            order.setC_BPartner_Location_ID(location.get_ID());
            order.setBill_Location_ID(location.get_ID());
            order.setM_Warehouse_ID(getM_Warehouse_ID());
            order.setC_DocTypeTarget_ID(MOrder.DocSubTypeSO_Standard);
            order.setDateOrdered(businessDate);
            order.setDatePromised(businessDate);
            order.setDeliveryRule(MOrder.DELIVERYRULE_Availability);
            order.setPaymentRule(MOrder.PAYMENTRULE_OnCredit);
            order.saveEx();
            MPriceListVersion version = MPriceList.get(ctx, order.getM_PriceList_ID(), trx)
                .getPriceListVersion(businessDate);
            assertNotNull(version);
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
            orderLine.setDiscount(new BigDecimal("10"));
            orderLine.setDatePromised(businessDate);
            orderLine.setC_Tax_ID(DictionaryIDs.C_Tax.PST.id);
            orderLine.saveEx();
            complete("order", order);
            assertTrue(orderLine.load(trx));
            amount("3", orderLine.getQtyOrdered());
            amount("3", orderLine.getQtyReserved());
            amount("19.995", orderLine.getPriceList());
            amount("17.9955", orderLine.getPriceActual());
            amount("10", orderLine.getDiscount());
            amount("7.5", new MTax(ctx, orderLine.getC_Tax_ID(), trx).getRate());
            amount("53.99", order.getTotalLines());
            amount("58.04", order.getGrandTotal());

            int bank = DB.getSQLValueEx(trx,
                "SELECT C_BankAccount_ID FROM C_BankAccount WHERE AD_Client_ID=? AND IsDefault='Y'",
                getAD_Client_ID());
            assertTrue(bank > 0);
            MInOutLine firstShipmentLine = ship("firstShipment", order, orderLine, BigDecimal.ONE);
            assertTrue(orderLine.load(trx));
            amount("1", orderLine.getQtyDelivered());
            amount("2", orderLine.getQtyReserved());
            MInvoice firstInvoice = invoice("firstInvoice", order, orderLine,
                firstShipmentLine, BigDecimal.ONE, "18.00", "19.35");
            assertTrue(orderLine.load(trx));
            fact("invoicing.afterFirst", orderLine.getQtyInvoiced());
            amount("1", orderLine.getQtyInvoiced());
            pay("firstPayment", customer, firstInvoice, bank);

            MInOutLine shipmentLine = ship("shipment", order, orderLine, new BigDecimal("2"));
            assertTrue(orderLine.load(trx));
            amount("3", orderLine.getQtyDelivered());
            amount("0", orderLine.getQtyReserved());
            MInvoice invoice = invoice("invoice", order, orderLine,
                shipmentLine, new BigDecimal("2"), "35.99", "38.69");
            assertTrue(orderLine.load(trx));
            fact("invoicing.final", orderLine.getQtyInvoiced());
            amount("3", orderLine.getQtyInvoiced());
            pay("payment", customer, invoice, bank);
            assertNotEquals(firstInvoice.get_ID(), invoice.get_ID());
            assertEquals(0, order.getGrandTotal().compareTo(
                firstInvoice.getGrandTotal().add(invoice.getGrandTotal())));
            assertEquals(0, order.getTotalLines().compareTo(
                firstInvoice.getTotalLines().add(invoice.getTotalLines())));
            getTrx().commit(true);

            assertTrue(firstInvoice.load(trx));
            assertTrue(invoice.load(trx));
            assertTrue(firstInvoice.isPaid());
            assertTrue(invoice.isPaid());
            assertTrue(firstInvoice.get_ValueAsBoolean("Posted"));
            assertTrue(invoice.get_ValueAsBoolean("Posted"));
            BigDecimal onHand = DB.getSQLValueBDEx(trx,
                "SELECT SUM(QtyOnHand) FROM M_StorageOnHand WHERE M_Product_ID=?", product.get_ID());
            fact("inventory.onHand", onHand);
            amount("7", onHand);
            int issuesAfter = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            fact("newIssueCount", issuesAfter - issuesBefore);
            assertEquals(issuesBefore, issuesAfter);
            getTrx().commit(true);
            fact("status", "completed-and-committed");
        } finally {
            try (var out = Files.newOutputStream(output)) {
                evidence.storeToXML(out, "Observed iDempiere partial invoicing journey");
            }
        }
    }
}
