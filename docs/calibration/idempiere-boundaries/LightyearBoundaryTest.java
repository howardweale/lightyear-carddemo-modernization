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
public class LightyearBoundaryTest extends AbstractTestCase {
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

    @Test public void fractionalCustomerToPayment() throws Exception {
        Path output = Path.of(System.getProperty("lightyear.output"));
        fact("status", "started"); fact("database", DB.isOracle() ? "oracle" : "postgresql");
        try {
            Properties ctx = Env.getCtx(); String trx = getTrxName();
            int issuesBefore = DB.getSQLValueEx(trx, "SELECT COUNT(*) FROM AD_Issue");
            MBPartner template = new MBPartner(ctx, DictionaryIDs.C_BPartner.JOE_BLOCK.id, trx);
            MBPartner customer = new MBPartner(ctx, 0, trx);
            customer.setValue("LY-BOUNDARY-FRACTION"); customer.setName("Caf\u00e9 \u6771\u4eac \u0141\u00f3d\u017a");
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
            product.setValue("LY-BOUNDARY-FRACTION"); product.setName("Lightyear Equivalence Product");
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
            order.setDeliveryRule(MOrder.DELIVERYRULE_CompleteOrder);
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

            MInOut shipment = new MInOut(order, DictionaryIDs.C_DocType.MM_SHIPMENT.id, businessDate);
            Timestamp fractional = Timestamp.valueOf("2026-09-26 12:34:56.123456");
            shipment.setShipDate(fractional); fact("shipment.shipDate.input", fractional);
            shipment.saveEx(); MInOutLine shipmentLine = new MInOutLine(shipment);
            shipmentLine.setOrderLine(orderLine, DictionaryIDs.M_Locator.HQ.id, new BigDecimal("3"));
            shipmentLine.setQty(new BigDecimal("3")); shipmentLine.saveEx(); complete("shipment", shipment); commit();
            shipment.load(trx); fact("shipment.shipDate.readback", shipment.getShipDate());
            orderLine.load(trx); fact("shipment.delivered", orderLine.getQtyDelivered());
            assertEquals(0, new BigDecimal("3").compareTo(orderLine.getQtyDelivered()));

            MInvoice invoice = new MInvoice(shipment, businessDate);
            invoice.saveEx(); MInvoiceLine invoiceLine = new MInvoiceLine(invoice);
            invoiceLine.setShipLine(shipmentLine); invoiceLine.setQty(new BigDecimal("3"));
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
}
