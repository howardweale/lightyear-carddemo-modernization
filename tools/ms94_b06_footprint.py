"""Independent owned-row checks, including equal unauthorized writes on both lanes."""
from lightyear_calibration.ms94_v3_errors import business_require as require
from tools.ms94_b06_admission import row_delta

MATERIALS = {
    "product": "m_product", "destinationLocator": "m_locator",
    "openingInventory": "m_inventory", "movement": "m_movement",
    "internalUse": "m_inventory", "physicalCount": "m_inventory",
}
PURCHASING = {
    "vendor": "c_bpartner", "vendorLocation": "c_bpartner_location",
    "product": "m_product", "productPrice": "m_productprice",
    "purchaseOrder": "c_order", "receipt": "m_inout",
    "vendorInvoice": "c_invoice", "vendorPayment": "c_payment",
}
PRODUCT_TABLES = set("""m_product_acct m_product_trl m_productprice m_product_po
 m_cost m_costdetail m_costqueue m_costhistory m_storageonhand m_storagereservation
 m_storagereservationlog m_transaction""".split())
CHILDREN = {
    "m_inventoryline": "m_inventory_id", "m_movementline": "m_movement_id",
    "m_inventorylinema": "m_inventoryline_id", "m_movementlinema": "m_movementline_id",
    "c_orderline": "c_order_id", "c_ordertax": "c_order_id",
    "m_inoutline": "m_inout_id", "m_inoutlinema": "m_inoutline_id",
    "c_invoiceline": "c_invoice_id", "c_invoicetax": "c_invoice_id",
    "c_bp_vendor_acct": "c_bpartner_id", "c_bp_customer_acct": "c_bpartner_id",
    "m_matchinv": "c_invoiceline_id", "m_matchpo": "c_orderline_id",
}


def validate(before, after, trace, contract, runtime_facts=None):
    stages = MATERIALS if contract["journey"] == "J3" else PURCHASING
    roots, documents = {}, set()
    client, org = contract["client_id"], contract["organization_id"]
    for stage, table in stages.items():
        identity = int(trace[stage + ".id"])
        key = table + "_id"
        require(not any(r[key] == identity for r in before[table]), "owned-root-not-new")
        found = [r for r in after[table] if r[key] == identity]
        require(len(found) == 1 and found[0]["ad_client_id"] == client and
                found[0]["ad_org_id"] == org, "owned-root-identity-or-organization")
        roots.setdefault(key, set()).add(identity)
        if table in contract["document_table_ids"]:
            documents.add((contract["document_table_ids"][table], identity))
    additions = {}
    changed = []
    for table in before:
        removed, added = row_delta(before[table], after[table])
        if not removed and not added:
            continue
        changed.append(table)
        if table == 'ad_system':
            require(runtime_facts is not None, 'system-runtime-identity-missing')
            old = {r['ad_system_id']: r for r in before[table]}
            new = {r['ad_system_id']: r for r in after[table]}
            require(set(old) == set(new), 'system-identity-inventory-changed')
            for identity, row in new.items():
                fields = {k for k in set(row) | set(old[identity]) if row.get(k) != old[identity].get(k)}
                require(fields <= {'dbaddress', 'dbinstance'}, 'unowned-system-configuration-change')
                if 'dbaddress' in fields:
                    require(row['dbaddress'] == runtime_facts['expected_database_address'], 'wrong-runtime-address')
                if 'dbinstance' in fields:
                    require(runtime_facts['native_database_instance'] is not None and
                            row['dbinstance'] == runtime_facts['native_database_instance'], 'wrong-runtime-instance')
            continue
        if table in ("ad_sequence", "c_acctschema"):
            _existing_metadata(table, before, after, documents, contract)
            continue
        require(not removed, "preexisting-row-modified-or-deleted")
        additions[table] = added

    # Derive child identities exclusively from independently captured native
    # links. Process parent tables before their dependent material allocations.
    pending = dict(additions)
    for _ in range(len(CHILDREN) + 3):
        progressed = False
        for table, added in list(pending.items()):
            own_key = table + "_id"
            if table in stages.values():
                matches = all(r.get(own_key) in roots[own_key] for r in added)
            elif table in PRODUCT_TABLES:
                matches = all(r.get("m_product_id") in roots["m_product_id"] for r in added)
            elif table in CHILDREN and CHILDREN[table] in roots:
                matches = all(r.get(CHILDREN[table]) in roots[CHILDREN[table]] for r in added)
            elif table in ("fact_acct", "t_fact_acct_history", "ad_wf_process", "ad_pinstance"):
                matches = all((r.get("ad_table_id"), r.get("record_id")) in documents for r in added)
            elif table in ("ad_wf_activity", "ad_wf_eventaudit") and "ad_wf_process_id" in roots:
                matches = all(r.get("ad_wf_process_id") in roots["ad_wf_process_id"] for r in added)
            elif table in ("ad_treenodepr", "ad_treenodebp"):
                field = "m_product_id" if table == "ad_treenodepr" else "c_bpartner_id"
                matches = field in roots and all(r.get("node_id") in roots[field] for r in added)
            elif table == "c_allocationline" and contract["journey"] == "J2":
                matches = all(r.get("c_invoice_id") in roots["c_invoice_id"] and
                              r.get("c_payment_id") in roots["c_payment_id"] for r in added)
                if matches:
                    roots["c_allocationhdr_id"] = {r["c_allocationhdr_id"] for r in added}
                    documents.update((735, n) for n in roots["c_allocationhdr_id"])
            elif table == "c_allocationhdr" and "c_allocationhdr_id" in roots:
                matches = all(r[own_key] in roots[own_key] for r in added)
            else:
                continue
            if not matches:
                continue
            require(all(r.get("ad_client_id") == client and r.get("ad_org_id") in (0, org)
                        for r in added), "owned-delta-client-or-organization")
            if added and own_key in added[0]:
                roots.setdefault(own_key, set()).update(r[own_key] for r in added)
                if table in contract['document_table_ids']:
                    documents.update((contract['document_table_ids'][table], r[own_key]) for r in added)
            del pending[table]
            progressed = True
        if not progressed:
            break
    require(not pending, "unowned-or-undeclared-native-write")
    return {"passed": True, "changed_tables": sorted(changed),
            "owned_added_rows": {t: len(v) for t, v in sorted(additions.items())},
            "preexisting_business_rows_unchanged": True}


def _existing_metadata(table, before, after, documents, contract):
    key = table + "_id"
    old, new = ({r[key]: r for r in records[table]} for records in (before, after))
    require(set(old) == set(new), "metadata-row-inventory-changed")
    for identity, row in new.items():
        prior = old[identity]
        changed = {k for k in set(row) | set(prior) if row.get(k) != prior.get(k)}
        if not changed:
            continue
        if table == "ad_sequence":
            require(changed <= {"currentnext", "currentnextsys", "updated", "updatedby"}
                    and prior["istableid"] == "Y" and prior["isactive"] == "Y",
                    "undeclared-sequence-mutation")
            for column in changed & {"currentnext", "currentnextsys"}:
                require(0 <= int(row[column]) - int(prior[column]) <= contract["maximum_sequence_advance"],
                        "sequence-advance-outside-declared-bound")
        else:
            require(changed <= {"c_period_id", "updated", "updatedby"}, "accounting-configuration-changed")
            facts = [r for r in after["fact_acct"] if r["c_acctschema_id"] == identity and
                     (r["ad_table_id"], r["record_id"]) in documents]
            require(facts and {r["c_period_id"] for r in facts} == {row["c_period_id"]} and
                    all(r["ad_client_id"] == row["ad_client_id"] for r in facts) and
                    row["updatedby"] in {r["createdby"] for r in facts},
                    "accounting-cache-not-bound-to-postings")
