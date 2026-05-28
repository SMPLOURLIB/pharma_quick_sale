import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate, now_datetime, add_days
from erpnext.stock.get_item_details import get_item_details


class PharmaQuickSale(Document):
    def validate(self):
        self.set_item_totals()
        self.validate_items_and_batches()

    def set_item_totals(self):
        allocations_by_row = {}
        for alloc in self.batch_allocations:
            allocations_by_row.setdefault(alloc.item_row_id, {"qty": 0, "free_qty": 0})
            allocations_by_row[alloc.item_row_id]["qty"] += flt(alloc.qty)
            allocations_by_row[alloc.item_row_id]["free_qty"] += flt(alloc.free_qty)

        for row in self.items:
            totals = allocations_by_row.get(row.row_id, {"qty": 0, "free_qty": 0})
            row.total_qty = totals["qty"]
            row.total_free_qty = totals["free_qty"]

    def validate_items_and_batches(self):
        if not self.items:
            frappe.throw("Please add at least one item.")
        if not self.batch_allocations:
            frappe.throw("Please add batch allocations.")

        item_by_row = {row.row_id: row for row in self.items}

        for row in self.items:
            if not row.row_id:
                frappe.throw("Each item row must have a row_id.")
            if not row.item_code:
                frappe.throw("Item is required.")
            item = frappe.get_doc("Item", row.item_code)
            row.item_name = item.item_name
            row.uom = row.uom or item.stock_uom
            row.conversion_factor = flt(row.conversion_factor) or 1

        for alloc in self.batch_allocations:
            if alloc.item_row_id not in item_by_row:
                frappe.throw(f"Invalid item_row_id in batch allocation: {alloc.item_row_id}")
            item_row = item_by_row[alloc.item_row_id]

            if alloc.item_code != item_row.item_code:
                frappe.throw(f"Batch allocation item {alloc.item_code} does not match item row {item_row.item_code}.")

            requested = flt(alloc.qty) + flt(alloc.free_qty)
            if requested <= 0:
                continue

            if not alloc.batch_no:
                frappe.throw(f"Batch is required for item {alloc.item_code}.")

            batch = frappe.get_doc("Batch", alloc.batch_no)
            if batch.item != alloc.item_code:
                frappe.throw(f"Batch {alloc.batch_no} does not belong to item {alloc.item_code}.")

            alloc.expiry_date = batch.expiry_date

            if batch.expiry_date and getdate(batch.expiry_date) < getdate(self.posting_date or nowdate()):
                frappe.throw(f"Expired batch: {alloc.batch_no}")

            physical_qty = get_batch_qty(alloc.item_code, alloc.batch_no, self.warehouse)
            reserved_qty = get_reserved_batch_qty(alloc.item_code, alloc.batch_no, self.warehouse)
            available_qty = max(physical_qty - reserved_qty, 0)
            alloc.available_qty = available_qty

            if available_qty < requested:
                frappe.throw(
                    f"Insufficient stock for {alloc.item_code}, batch {alloc.batch_no}. "
                    f"Available: {available_qty}, Required: {requested}"
                )

    def _get_item_details(self, item_code, doctype):
        currency = frappe.db.get_value("Company", self.company, "default_currency") or "INR"
        args = {
            "doctype": doctype,
            "item_code": item_code,
            "company": self.company,
            "customer": self.customer,
            "selling_price_list": self.price_list or "Standard Selling",
            "currency": currency,
            "conversion_rate": 1,
            "price_list_currency": currency,
            "plc_conversion_rate": 1,
            "transaction_date": self.posting_date or nowdate()
        }
        return get_item_details(args)

    def _append_items(self, target_doc, target_doctype):
        item_by_row = {row.row_id: row for row in self.items}

        def append_row(qty, rate, row, alloc, item_details, description=None):
            values = {
                "item_code": row.item_code,
                "qty": qty,
                "rate": rate,
                "warehouse": self.warehouse,
                "uom": row.uom or item_details.get("uom"),
                "conversion_factor": flt(row.conversion_factor) or item_details.get("conversion_factor") or 1,
                "item_tax_template": (
                item_details.get("item_tax_template")
                or row.get("item_tax_template")
                or _get_item_tax_template_from_item(
                    item_code,
                    tax_category=tax_category,
                    posting_date=data.get("posting_date") or nowdate()
                )
            ),
                "income_account": item_details.get("income_account"),
                "cost_center": item_details.get("cost_center"),
                "description": description or item_details.get("description") or row.item_name
            }

            if rate:
                values["discount_percentage"] = flt(row.discount_percentage)

            # Sales Invoice needs standard batch_no for stock posting.
            # Sales Order Item may not have batch_no in ERPNext v14/v15.
            if target_doctype == "Sales Invoice":
                values["batch_no"] = alloc.batch_no

            # Custom fields shipped as fixtures for SO/SI traceability.
            values["pharma_batch_no"] = alloc.batch_no
            values["pharma_quick_sale"] = self.name

            target_doc.append("items", values)

        for alloc in self.batch_allocations:
            row = item_by_row[alloc.item_row_id]
            item_details = self._get_item_details(row.item_code, target_doctype)

            if flt(alloc.qty) > 0:
                append_row(flt(alloc.qty), flt(row.rate), row, alloc, item_details)

            if flt(alloc.free_qty) > 0:
                append_row(
                    flt(alloc.free_qty),
                    0,
                    row,
                    alloc,
                    item_details,
                    description=f"Free Sample - {row.item_name or row.item_code}"
                )

    def create_sales_invoice(self):
        if self.sales_invoice:
            return frappe.get_doc("Sales Invoice", self.sales_invoice)

        invoice = frappe.new_doc("Sales Invoice")
        invoice.customer = self.customer
        invoice.company = self.company
        invoice.posting_date = self.posting_date or nowdate()
        invoice.set_posting_time = 1
        invoice.update_stock = 1
        invoice.selling_price_list = self.price_list or "Standard Selling"

        self._append_items(invoice, "Sales Invoice")

        if flt(self.bill_discount_amount) > 0:
            invoice.apply_discount_on = "Grand Total"
            invoice.discount_amount = flt(self.bill_discount_amount)

        invoice.run_method("set_missing_values")
        invoice.calculate_taxes_and_totals()
        invoice.insert(ignore_permissions=True)
        invoice.submit()

        self.db_set("sales_invoice", invoice.name)
        return invoice

    def create_sales_order(self):
        if self.sales_order:
            return frappe.get_doc("Sales Order", self.sales_order)

        sales_order = frappe.new_doc("Sales Order")
        sales_order.customer = self.customer
        sales_order.company = self.company
        sales_order.transaction_date = self.posting_date or nowdate()
        sales_order.delivery_date = self.posting_date or nowdate()
        sales_order.selling_price_list = self.price_list or "Standard Selling"

        self._append_items(sales_order, "Sales Order")

        if flt(self.bill_discount_amount) > 0:
            sales_order.apply_discount_on = "Grand Total"
            sales_order.discount_amount = flt(self.bill_discount_amount)

        sales_order.run_method("set_missing_values")
        sales_order.calculate_taxes_and_totals()
        sales_order.insert(ignore_permissions=True)
        sales_order.submit()

        self.db_set("sales_order", sales_order.name)
        reserve_batches_for_sales_order(sales_order.name)
        return sales_order


@frappe.whitelist()
def get_batch_qty(item_code, batch_no, warehouse):
    return flt(frappe.db.sql("""
        SELECT SUM(actual_qty)
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND batch_no = %s
          AND warehouse = %s
          AND is_cancelled = 0
    """, (item_code, batch_no, warehouse))[0][0] or 0)


@frappe.whitelist()
def get_item_price_lookup(item_code, customer=None, warehouse=None, price_list="Standard Selling"):
    item = frappe.get_doc("Item", item_code)

    price = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
        "price_list_rate"
    ) or 0

    last_sale = []
    if customer:
        last_sale = frappe.db.sql("""
            SELECT
                sii.parent,
                si.posting_date,
                sii.qty,
                sii.rate,
                sii.discount_percentage
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.docstatus = 1
              AND si.customer = %s
              AND sii.item_code = %s
            ORDER BY si.posting_date DESC, si.creation DESC
            LIMIT 5
        """, (customer, item_code), as_dict=True)

    stock_qty = 0
    if warehouse:
        stock_qty = flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0)

    return {
        "item_code": item_code,
        "item_name": item.item_name,
        "stock_uom": item.stock_uom,
        "price": price,
        "stock_qty": stock_qty,
        "last_sale": last_sale,
        "pharma_price": get_pharma_price_snapshot(item_code, price_list=price_list)
    }


@frappe.whitelist()
def get_last_sales(customer, item_code=None, limit=10):
    conditions = ["si.docstatus = 1", "si.customer = %s"]
    values = [customer]

    if item_code:
        conditions.append("sii.item_code = %s")
        values.append(item_code)

    values.append(int(limit))

    return frappe.db.sql(f"""
        SELECT
            si.name AS invoice,
            si.posting_date,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.rate,
            sii.discount_percentage,
            sii.amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(conditions)}
        ORDER BY si.posting_date DESC, si.creation DESC
        LIMIT %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_reserved_batch_qty(item_code, batch_no, warehouse):
    """Return app-level active reservation quantity.

    This is not a DB row lock. It is an application-level reservation helper.
    """
    if not frappe.db.table_exists("Pharma Batch Reservation"):
        return 0

    return flt(frappe.db.sql("""
        SELECT SUM(reserved_qty)
        FROM `tabPharma Batch Reservation`
        WHERE docstatus = 1
          AND status = 'Active'
          AND item_code = %s
          AND batch_no = %s
          AND warehouse = %s
    """, (item_code, batch_no, warehouse))[0][0] or 0)


@frappe.whitelist()
def allocate_fefo(item_code, warehouse, qty):
    requested_qty = flt(qty)
    if requested_qty <= 0:
        return []

    batches = frappe.db.sql("""
        SELECT
            sle.batch_no,
            b.expiry_date,
            SUM(sle.actual_qty) AS available_qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE sle.item_code = %s
          AND sle.warehouse = %s
          AND sle.batch_no IS NOT NULL
          AND sle.is_cancelled = 0
          AND (b.expiry_date IS NULL OR b.expiry_date >= CURDATE())
        GROUP BY sle.batch_no, b.expiry_date
        HAVING available_qty > 0
        ORDER BY b.expiry_date ASC
    """, (item_code, warehouse), as_dict=True)

    remaining = requested_qty
    allocations = []

    for batch in batches:
        if remaining <= 0:
            break

        reserved_qty = get_reserved_batch_qty(item_code, batch.batch_no, warehouse)
        net_available = max(flt(batch.available_qty) - flt(reserved_qty), 0)
        if net_available <= 0:
            continue

        alloc_qty = min(net_available, remaining)
        allocations.append({
            "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date,
            "available_qty": net_available,
            "reserved_qty": reserved_qty,
            "qty": alloc_qty,
            "free_qty": 0
        })
        remaining -= alloc_qty

    if remaining > 0:
        frappe.throw(f"Insufficient stock for {item_code}. Short by {remaining}")

    return allocations


@frappe.whitelist()
def get_item_by_barcode(barcode, warehouse=None, customer=None, price_list="Standard Selling"):
    """Resolve barcode safely across ERPNext v14 variants.

    Lookup order:
    1. Item Barcode child table
    2. Item.name exactly equals scanned value
    3. Item.item_code exactly equals scanned value, where field exists
    """
    if not barcode:
        frappe.throw("Barcode is required.")

    item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")

    if not item_code and frappe.db.exists("Item", barcode):
        item_code = barcode

    if not item_code:
        try:
            item_code = frappe.db.get_value("Item", {"item_code": barcode}, "name")
        except Exception:
            item_code = None

    if not item_code:
        frappe.throw(f"No item found for barcode {barcode}")

    return get_item_price_lookup(item_code, customer=customer, warehouse=warehouse, price_list=price_list)


@frappe.whitelist()
def create_batch(item_code, expiry_date, batch_id=None):
    """Create or return a Batch idempotently.

    If batch_id is supplied and already exists for the same item, it is returned.
    If it exists for another item, the function blocks to prevent traceability errors.
    """
    if not item_code or not expiry_date:
        frappe.throw("Item and expiry date are required.")

    requested_batch = batch_id

    if requested_batch and frappe.db.exists("Batch", requested_batch):
        existing_item = frappe.db.get_value("Batch", requested_batch, "item")
        if existing_item != item_code:
            frappe.throw(f"Batch {requested_batch} already exists for item {existing_item}.")
        return requested_batch

    batch = frappe.new_doc("Batch")
    batch.batch_id = requested_batch or frappe.generate_hash(length=8).upper()
    batch.item = item_code
    batch.expiry_date = expiry_date
    batch.insert(ignore_permissions=True)
    return batch.name


@frappe.whitelist()
def create_fast_grn(data):
    """Create Purchase Receipt from fast pharma inward screen.

    Important valuation rule:
    - Paid qty is added at supplier rate.
    - Free qty is added as a separate row at rate 0.
    This avoids overstating purchase value.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    pr = frappe.new_doc("Purchase Receipt")
    pr.supplier = data.get("supplier")
    pr.company = data.get("company")
    pr.posting_date = data.get("posting_date") or nowdate()
    pr.set_posting_time = 1

    for item in data.get("items", []):
        item_code = item.get("item_code")
        batch_no = item.get("batch_no") or item.get("supplier_batch")

        if batch_no:
            if not frappe.db.exists("Batch", batch_no):
                batch_no = create_batch(item_code, item.get("expiry_date"), batch_no)
            else:
                existing_item = frappe.db.get_value("Batch", batch_no, "item")
                if existing_item != item_code:
                    frappe.throw(f"Batch {batch_no} belongs to {existing_item}, not {item_code}.")
        else:
            batch_no = create_batch(item_code, item.get("expiry_date"), item.get("supplier_batch"))

        warehouse = item.get("warehouse") or data.get("warehouse")
        paid_qty = flt(item.get("qty"))
        free_qty = flt(item.get("free_qty"))
        rate = flt(item.get("rate"))

        if paid_qty > 0:
            pr.append("items", {
                "item_code": item_code,
                "qty": paid_qty,
                "rate": rate,
                "warehouse": warehouse,
                "batch_no": batch_no
            })

        if free_qty > 0:
            pr.append("items", {
                "item_code": item_code,
                "qty": free_qty,
                "rate": 0,
                "warehouse": warehouse,
                "batch_no": batch_no,
                "description": f"Free Qty - {item_code}"
            })

    pr.run_method("set_missing_values")
    pr.calculate_taxes_and_totals()
    pr.insert(ignore_permissions=True)
    pr.submit()
    return pr.name


@frappe.whitelist()
def get_expiry_dashboard(days=180, warehouse=None):
    """Return batch expiry dashboard rows.

    Compatible with ERPNext v14/v15. Uses one warehouse placeholder only when
    warehouse is supplied, and one days placeholder for HAVING clause.
    """
    conditions = [
        "sle.batch_no IS NOT NULL",
        "sle.is_cancelled = 0",
        "b.expiry_date IS NOT NULL"
    ]
    values = []

    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)

    values.append(int(days))

    return frappe.db.sql(f"""
        SELECT
            sle.item_code,
            b.name AS batch_no,
            b.expiry_date,
            SUM(sle.actual_qty) AS qty,
            DATEDIFF(b.expiry_date, CURDATE()) AS days_to_expiry
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.item_code, b.name, b.expiry_date
        HAVING qty > 0 AND days_to_expiry <= %s
        ORDER BY b.expiry_date ASC
    """, tuple(values), as_dict=True)



@frappe.whitelist()
def copy_pharma_fields_to_sales_invoice(doc, method=None):
    """Copy pharma custom fields from Sales Order Item to Sales Invoice Item.

    ERPNext usually maps same-name custom fields, but this hook makes the
    behavior explicit across v14/v15 and custom mapping paths.
    """
    invoice = doc if hasattr(doc, "items") else frappe.get_doc("Sales Invoice", doc)

    for row in invoice.items:
        if getattr(row, "pharma_batch_no", None):
            continue

        so_detail = getattr(row, "so_detail", None)
        sales_order = getattr(row, "sales_order", None) or getattr(row, "against_sales_order", None)

        if so_detail:
            so_row = frappe.db.get_value(
                "Sales Order Item",
                so_detail,
                ["pharma_batch_no", "pharma_quick_sale"],
                as_dict=True
            )
            if so_row:
                if so_row.get("pharma_batch_no"):
                    row.pharma_batch_no = so_row.get("pharma_batch_no")
                if so_row.get("pharma_quick_sale"):
                    row.pharma_quick_sale = so_row.get("pharma_quick_sale")
                continue

        if sales_order and row.item_code and row.warehouse:
            so_row = frappe.db.sql("""
                SELECT pharma_batch_no, pharma_quick_sale
                FROM `tabSales Order Item`
                WHERE parent = %s
                  AND item_code = %s
                  AND warehouse = %s
                  AND IFNULL(pharma_batch_no, '') != ''
                ORDER BY idx ASC
                LIMIT 1
            """, (sales_order, row.item_code, row.warehouse), as_dict=True)

            if so_row:
                row.pharma_batch_no = so_row[0].pharma_batch_no
                row.pharma_quick_sale = so_row[0].pharma_quick_sale

    return invoice


@frappe.whitelist()
def get_reservation_validation(sales_order=None):
    """Return reservation status rows for audit/UAT."""
    conditions = ["1=1"]
    values = []

    if sales_order:
        conditions.append("sales_order = %s")
        values.append(sales_order)

    return frappe.db.sql(f"""
        SELECT
            sales_order,
            sales_invoice,
            item_code,
            warehouse,
            batch_no,
            original_reserved_qty,
            reserved_qty,
            consumed_qty,
            status,
            docstatus
        FROM `tabPharma Batch Reservation`
        WHERE {' AND '.join(conditions)}
        ORDER BY modified DESC
        LIMIT 200
    """, tuple(values), as_dict=True)

def _get_batch_from_sales_row(row):
    return getattr(row, "pharma_batch_no", None) or getattr(row, "batch_no", None)


def _get_quick_sale_from_sales_row(row):
    return getattr(row, "pharma_quick_sale", None)


def _reservation_key(sales_order, item_code, batch_no, warehouse):
    return (sales_order or "", item_code or "", batch_no or "", warehouse or "")


def _get_sales_order_from_invoice_row(row):
    return (
        getattr(row, "sales_order", None)
        or getattr(row, "against_sales_order", None)
        or getattr(row, "so_detail", None)
    )


@frappe.whitelist()
def reserve_batches_for_sales_order(sales_order):
    """Aggregate and reserve Sales Order quantities by SO + item + batch + warehouse.

    This fixes split-row cases where the same item/batch appears more than once
    for billable and free quantities.
    """
    so = frappe.get_doc("Sales Order", sales_order)

    aggregate = {}

    for item in so.items:
        batch_no = _get_batch_from_sales_row(item)
        warehouse = item.warehouse

        if not batch_no or not warehouse:
            continue

        key = _reservation_key(so.name, item.item_code, batch_no, warehouse)
        aggregate.setdefault(key, 0)
        aggregate[key] += flt(item.qty)

    created_or_updated = []

    for key, required_qty in aggregate.items():
        sales_order_name, item_code, batch_no, warehouse = key

        existing = frappe.db.get_value(
            "Pharma Batch Reservation",
            {
                "sales_order": sales_order_name,
                "item_code": item_code,
                "warehouse": warehouse,
                "batch_no": batch_no,
                "status": "Active",
                "docstatus": 1
            },
            ["name", "reserved_qty"],
            as_dict=True
        )

        physical_qty = get_batch_qty(item_code, batch_no, warehouse)
        active_reserved = get_reserved_batch_qty(item_code, batch_no, warehouse)
        existing_qty = flt(existing.reserved_qty) if existing else 0
        net_available = physical_qty - active_reserved + existing_qty

        if net_available < required_qty:
            frappe.throw(
                f"Cannot reserve {required_qty} of {item_code}, batch {batch_no}. "
                f"Net available after active reservations: {net_available}"
            )

        if existing:
            res = frappe.get_doc("Pharma Batch Reservation", existing.name)
            if flt(res.reserved_qty) != flt(required_qty):
                res.db_set("reserved_qty", required_qty)
            created_or_updated.append(res.name)
        else:
            res = frappe.new_doc("Pharma Batch Reservation")
            res.sales_order = sales_order_name
            res.item_code = item_code
            res.warehouse = warehouse
            res.batch_no = batch_no
            res.reserved_qty = required_qty
            res.original_reserved_qty = required_qty
            res.status = "Active"
            res.insert(ignore_permissions=True)
            res.submit()
            created_or_updated.append(res.name)

    return created_or_updated


@frappe.whitelist()
def release_reservations_for_sales_order(doc, method=None):
    """Release active reservations when Sales Order is cancelled."""
    sales_order = doc.name if hasattr(doc, "name") else doc

    reservations = frappe.get_all(
        "Pharma Batch Reservation",
        filters={
            "sales_order": sales_order,
            "status": "Active",
            "docstatus": 1
        },
        pluck="name"
    )

    released = []
    for name in reservations:
        res = frappe.get_doc("Pharma Batch Reservation", name)
        res.db_set("status", "Released")
        released.append(name)

    return released


def _reservation_candidates_for_invoice(invoice):
    """Aggregate invoice rows against sales orders by SO + item + batch + warehouse."""
    aggregate = {}

    for row in invoice.items:
        sales_order = _get_sales_order_from_invoice_row(row)
        batch_no = _get_batch_from_sales_row(row)
        warehouse = row.warehouse

        if not sales_order or not batch_no or not warehouse:
            continue

        key = _reservation_key(sales_order, row.item_code, batch_no, warehouse)
        aggregate.setdefault(key, 0)
        aggregate[key] += flt(row.qty)

    return aggregate


@frappe.whitelist()
def consume_reservations_for_sales_invoice(doc, method=None):
    """Consume matching reservations when a Sales Invoice is submitted.

    v9 behavior:
    - Aggregates invoice rows by SO + item + batch + warehouse.
    - Supports full and partial consumption.
    - Tracks consumed_qty and last_sales_invoice for safer reversal.
    """
    invoice = doc if hasattr(doc, "items") else frappe.get_doc("Sales Invoice", doc)
    consumed = []

    for key, invoice_qty in _reservation_candidates_for_invoice(invoice).items():
        sales_order, item_code, batch_no, warehouse = key

        res_name = frappe.db.get_value(
            "Pharma Batch Reservation",
            {
                "sales_order": sales_order,
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "status": "Active",
                "docstatus": 1
            },
            "name"
        )

        if not res_name:
            continue

        res = frappe.get_doc("Pharma Batch Reservation", res_name)

        remaining_after_invoice = flt(res.reserved_qty) - flt(invoice_qty)
        consumed_qty = flt(res.consumed_qty) + flt(invoice_qty)

        res.db_set("last_sales_invoice", invoice.name)
        if hasattr(res, "sales_invoice"):
            res.db_set("sales_invoice", invoice.name)
        res.db_set("consumed_qty", consumed_qty)

        if remaining_after_invoice <= 0:
            res.db_set("reserved_qty", 0)
            res.db_set("status", "Consumed")
        else:
            res.db_set("reserved_qty", remaining_after_invoice)

        consumed.append(res_name)

    return consumed


@frappe.whitelist()
def release_reservations_for_sales_invoice(doc, method=None):
    """On Sales Invoice cancellation, restore matching consumed reservation qty.

    v9 behavior:
    - Uses aggregate invoice qty.
    - Restores reserved_qty by the cancelled invoice quantity.
    - Reactivates reservation if status was Consumed.
    """
    invoice = doc if hasattr(doc, "items") else frappe.get_doc("Sales Invoice", doc)
    restored = []

    for key, invoice_qty in _reservation_candidates_for_invoice(invoice).items():
        sales_order, item_code, batch_no, warehouse = key

        # Prefer reservation linked to this invoice.
        res_name = frappe.db.get_value(
            "Pharma Batch Reservation",
            {
                "sales_order": sales_order,
                "item_code": item_code,
                "batch_no": batch_no,
                "warehouse": warehouse,
                "last_sales_invoice": invoice.name,
                "docstatus": 1
            },
            "name"
        )

        if not res_name:
            # Fallback for earlier records without last_sales_invoice.
            res_name = frappe.db.get_value(
                "Pharma Batch Reservation",
                {
                    "sales_order": sales_order,
                    "item_code": item_code,
                    "batch_no": batch_no,
                    "warehouse": warehouse,
                    "status": "Consumed",
                    "docstatus": 1
                },
                "name"
            )

        if not res_name:
            continue

        res = frappe.get_doc("Pharma Batch Reservation", res_name)
        new_reserved = flt(res.reserved_qty) + flt(invoice_qty)
        new_consumed = max(flt(res.consumed_qty) - flt(invoice_qty), 0)

        res.db_set("reserved_qty", new_reserved)
        res.db_set("consumed_qty", new_consumed)
        res.db_set("status", "Active")
        restored.append(res_name)

    return restored


@frappe.whitelist()
def validate_pharma_master_data(company=None, warehouse=None):
    """Go-live preflight master-data validation.

    Returns warnings/errors without changing data.
    """
    results = {
        "errors": [],
        "warnings": [],
        "checks": []
    }

    def ok(msg):
        results["checks"].append(msg)

    if company:
        if not frappe.db.exists("Company", company):
            results["errors"].append(f"Company not found: {company}")
        else:
            ok(f"Company exists: {company}")
    else:
        results["warnings"].append("Company not supplied for preflight.")

    if warehouse:
        if not frappe.db.exists("Warehouse", warehouse):
            results["errors"].append(f"Warehouse not found: {warehouse}")
        else:
            ok(f"Warehouse exists: {warehouse}")
    else:
        results["warnings"].append("Warehouse not supplied for preflight.")

    # Check required DocTypes exist.
    required_doctypes = [
        "Pharma Quick Sale",
        "Pharma Quick Sale Item",
        "Pharma Quick Sale Batch Allocation",
        "Pharma Batch Reservation",
        "Sales Invoice",
        "Sales Order",
        "Purchase Receipt",
        "Batch",
        "Item"
    ]

    for dt in required_doctypes:
        if not frappe.db.exists("DocType", dt):
            results["errors"].append(f"Required DocType missing: {dt}")
        else:
            ok(f"DocType available: {dt}")

    # Custom fields.
    required_custom_fields = [
        "Sales Order Item-pharma_batch_no",
        "Sales Order Item-pharma_quick_sale",
        "Sales Invoice Item-pharma_batch_no",
        "Sales Invoice Item-pharma_quick_sale"
    ]

    for cf in required_custom_fields:
        if not frappe.db.exists("Custom Field", cf):
            results["errors"].append(f"Required Custom Field missing: {cf}")
        else:
            ok(f"Custom Field available: {cf}")

    # Check stock settings negative stock.
    try:
        allow_negative_stock = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
        if allow_negative_stock:
            results["warnings"].append("Allow Negative Stock is enabled. Recommended: disable for pharma go-live.")
        else:
            ok("Allow Negative Stock is disabled.")
    except Exception as exc:
        results["warnings"].append(f"Could not verify Stock Settings: {exc}")

    return results


@frappe.whitelist()
def validate_pharma_transactions(company=None, warehouse=None, limit=20):
    """Go-live transaction validation for existing pharma/batch data.

    Returns warnings/errors without changing data.
    """
    results = {
        "errors": [],
        "warnings": [],
        "checks": []
    }

    def ok(msg):
        results["checks"].append(msg)

    # Check batch-enabled items with stock.
    batch_stock = frappe.db.sql("""
        SELECT
            sle.item_code,
            sle.batch_no,
            SUM(sle.actual_qty) AS qty
        FROM `tabStock Ledger Entry` sle
        WHERE sle.batch_no IS NOT NULL
          AND sle.is_cancelled = 0
        GROUP BY sle.item_code, sle.batch_no
        HAVING qty > 0
        LIMIT %s
    """, int(limit), as_dict=True)

    if batch_stock:
        ok(f"Batch stock found: {len(batch_stock)} sample rows.")
    else:
        results["warnings"].append("No positive batch stock found. Quick Sale FEFO cannot be tested without batch stock.")

    # Check item prices.
    prices = frappe.db.count("Item Price", {"selling": 1})
    if prices:
        ok(f"Selling Item Prices found: {prices}")
    else:
        results["warnings"].append("No selling Item Price records found. Quick Sale will default rates to zero.")

    # Check submitted Sales Invoices exist for last-sale lookup.
    sinv_count = frappe.db.count("Sales Invoice", {"docstatus": 1})
    if sinv_count:
        ok(f"Submitted Sales Invoices found: {sinv_count}")
    else:
        results["warnings"].append("No submitted Sales Invoices found. Last Sale Lookup will be empty until transactions exist.")

    return results


@frappe.whitelist()
def run_go_live_preflight(company=None, warehouse=None):
    """Run consolidated go-live preflight checks."""
    master = validate_pharma_master_data(company=company, warehouse=warehouse)
    transactions = validate_pharma_transactions(company=company, warehouse=warehouse)

    status = "PASS"
    if master["errors"] or transactions["errors"]:
        status = "FAIL"
    elif master["warnings"] or transactions["warnings"]:
        status = "PASS_WITH_WARNINGS"

    return {
        "status": status,
        "master_data": master,
        "transactions": transactions
    }



def _doctype_has_field(doctype, fieldname):
    """Safe field existence check for ERPNext v14/v15/customized sites."""
    try:
        return frappe.get_meta(doctype).has_field(fieldname)
    except Exception:
        return False


def _safe_get_value_if_field_exists(doctype, name_or_filters, fieldname):
    """Read a field only when the field exists to avoid runtime SQL errors."""
    if not _doctype_has_field(doctype, fieldname):
        return None
    try:
        return frappe.db.get_value(doctype, name_or_filters, fieldname)
    except Exception:
        return None


def _apply_sales_taxes_template_for_live_calc(invoice, customer=None):
    """Apply Sales Taxes and Charges Template to an unsaved invoice.

    Hardened for ERPNext v14/v15:
    - Does not assume Customer has taxes_and_charges.
    - Does not assume Company has default_sales_taxes_and_charges_template.
    - Falls back to default/first enabled Sales Taxes and Charges Template.
    - Returns None cleanly if no template exists.
    """
    template = None

    # 1. Customer-specific tax template, only if field exists.
    if customer:
        template = _safe_get_value_if_field_exists("Customer", customer, "taxes_and_charges")

    # 2. Company default Sales Taxes and Charges Template, only if field exists.
    if not template and invoice.company:
        template = _safe_get_value_if_field_exists(
            "Company",
            invoice.company,
            "default_sales_taxes_and_charges_template"
        )

    # 3. Default enabled company template.
    if not template and invoice.company:
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "company": invoice.company,
                "is_default": 1,
                "disabled": 0
            },
            "name"
        )

    # 4. First enabled company template.
    if not template and invoice.company:
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "company": invoice.company,
                "disabled": 0
            },
            "name"
        )

    # 5. Last fallback: first enabled template regardless of company.
    # Useful for early UAT where company may not be tagged on templates.
    if not template:
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {
                "disabled": 0
            },
            "name"
        )

    if not template:
        return None

    invoice.taxes_and_charges = template

    tax_rows = frappe.get_all(
        "Sales Taxes and Charges",
        filters={
            "parent": template,
            "parenttype": "Sales Taxes and Charges Template"
        },
        fields=[
            "charge_type",
            "row_id",
            "account_head",
            "description",
            "included_in_print_rate",
            "included_in_paid_amount",
            "cost_center",
            "rate",
            "tax_amount",
            "total",
            "tax_amount_after_discount_amount",
            "base_tax_amount",
            "base_total",
            "base_tax_amount_after_discount_amount",
            "item_wise_tax_detail",
            "dont_recompute_tax"
        ],
        order_by="idx asc"
    )

    invoice.set("taxes", [])

    for tax in tax_rows:
        row = invoice.append("taxes", {})
        for key, value in tax.items():
            if key not in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
                row.set(key, value)

    return template


def _get_item_tax_template_from_item(item_code, tax_category=None, posting_date=None):
    """Resolve Item Tax Template directly from Item -> Taxes child table.

    Works across ERPNext v14/v15 field variants by inspecting Item Tax metadata.
    """
    if not item_code:
        return None

    try:
        meta = frappe.get_meta("Item Tax")
    except Exception:
        return None

    fields = [df.fieldname for df in meta.fields]
    if "item_tax_template" not in fields:
        return None

    conditions = ["parent = %s", "parenttype = 'Item'", "IFNULL(item_tax_template, '') != ''"]
    values = [item_code]

    if tax_category and "tax_category" in fields:
        conditions.append("(tax_category = %s OR IFNULL(tax_category, '') = '')")
        values.append(tax_category)

    if posting_date and "valid_from" in fields:
        conditions.append("(valid_from IS NULL OR valid_from <= %s)")
        values.append(posting_date)

    order_by = "idx ASC"
    if "valid_from" in fields:
        order_by = "valid_from DESC, idx ASC"

    rows = frappe.db.sql(f"""
        SELECT item_tax_template
        FROM `tabItem Tax`
        WHERE {' AND '.join(conditions)}
        ORDER BY {order_by}
        LIMIT 1
    """, tuple(values), as_dict=True)

    return rows[0].item_tax_template if rows else None


def _get_item_tax_template_accounts(item_tax_template):
    """Return account/rate rows from Item Tax Template Detail."""
    if not item_tax_template:
        return []

    try:
        meta = frappe.get_meta("Item Tax Template Detail")
    except Exception:
        return []

    fields = [df.fieldname for df in meta.fields]

    account_field = "tax_type" if "tax_type" in fields else None
    rate_field = "tax_rate" if "tax_rate" in fields else None

    if not account_field or not rate_field:
        return []

    return frappe.db.sql(f"""
        SELECT {account_field} AS account_head, {rate_field} AS rate
        FROM `tabItem Tax Template Detail`
        WHERE parent = %s
        ORDER BY idx ASC
    """, item_tax_template, as_dict=True)


def _ensure_tax_rows_for_live_item_tax_templates(invoice):
    """Ensure tax rows exist for item-wise tax calculation.

    ERPNext item tax templates override rates on tax accounts, but tax rows must
    still exist on the Sales Invoice. If no Sales Taxes and Charges Template is
    applied, this creates one tax row per account used by the item tax templates.
    """
    existing_accounts = set()
    for tax in invoice.taxes:
        if getattr(tax, "account_head", None):
            existing_accounts.add(tax.account_head)

    account_rates = {}

    for item in invoice.items:
        item_tax_template = getattr(item, "item_tax_template", None)
        if not item_tax_template:
            continue

        for row in _get_item_tax_template_accounts(item_tax_template):
            account_head = row.get("account_head")
            if not account_head:
                continue

            # Use the actual rate as default; ERPNext may override item-wise.
            account_rates[account_head] = flt(row.get("rate"))

    for account_head, rate in account_rates.items():
        if account_head in existing_accounts:
            continue

        invoice.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": account_head,
            "description": account_head,
            "rate": rate
        })


@frappe.whitelist()
def get_live_sales_totals(data):
    """Return live ERPNext-calculated totals for Quick Sale.

    v19 behavior:
    - Reads Item Tax Template directly from Item master when get_item_details()
      does not return it.
    - Assigns item_tax_template to every live Sales Invoice row.
    - Ensures required tax account rows exist.
    - Allows different items to carry different item tax templates.
    - Does not insert or submit any document.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    customer = data.get("customer")
    company = data.get("company")
    warehouse = data.get("warehouse")
    tax_category = data.get("tax_category")
    posting_date = data.get("posting_date") or nowdate()

    if not customer or not company:
        return {
            "ready": False,
            "message": "Customer and Company are required for live tax calculation.",
            "net_total": 0,
            "total_taxes_and_charges": 0,
            "grand_total": 0,
            "taxes": [],
            "tax_template": None,
            "items": []
        }

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = customer
    invoice.company = company
    invoice.posting_date = posting_date
    invoice.set_posting_time = 1
    invoice.update_stock = 1
    invoice.selling_price_list = data.get("price_list") or "Standard Selling"

    item_by_row = {}
    allocations_by_row = {}

    for item in data.get("items", []):
        row_id = item.get("row_id")
        if row_id and item.get("item_code"):
            item_by_row[row_id] = item

    for alloc in data.get("batch_allocations", []):
        row_id = alloc.get("item_row_id")
        if row_id:
            allocations_by_row.setdefault(row_id, [])
            allocations_by_row[row_id].append(alloc)

    def get_item_details_for(item_code):
        currency = frappe.db.get_value("Company", company, "default_currency") or "INR"
        args = {
            "doctype": "Sales Invoice",
            "item_code": item_code,
            "company": company,
            "customer": customer,
            "selling_price_list": data.get("price_list") or "Standard Selling",
            "currency": currency,
            "conversion_rate": 1,
            "price_list_currency": currency,
            "plc_conversion_rate": 1,
            "transaction_date": posting_date,
            "warehouse": warehouse
        }
        return get_item_details(args)

    def resolve_item_tax_template(row, item_details):
        item_code = row.get("item_code")
        return (
            item_details.get("item_tax_template")
            or row.get("item_tax_template")
            or _get_item_tax_template_from_item(
                item_code,
                tax_category=tax_category,
                posting_date=posting_date
            )
        )

    def append_invoice_row(row, qty, rate, item_details, batch_no=None, description=None):
        if flt(qty) <= 0:
            return

        item_code = row.get("item_code")
        item_tax_template = resolve_item_tax_template(row, item_details)

        values = {
            "item_code": item_code,
            "qty": flt(qty),
            "rate": flt(rate),
            "warehouse": warehouse,
            "uom": row.get("uom") or item_details.get("uom"),
            "conversion_factor": flt(row.get("conversion_factor")) or item_details.get("conversion_factor") or 1,
            "discount_percentage": flt(row.get("discount_percentage")),
            "item_tax_template": item_tax_template,
            "income_account": item_details.get("income_account"),
            "cost_center": item_details.get("cost_center"),
            "description": description or item_details.get("description") or row.get("item_name") or item_code
        }

        if batch_no:
            values["batch_no"] = batch_no

        invoice.append("items", values)

    for row_id, row in item_by_row.items():
        item_code = row.get("item_code")
        if not item_code:
            continue

        item_details = get_item_details_for(item_code)
        row_allocations = allocations_by_row.get(row_id) or []

        if row_allocations:
            for alloc in row_allocations:
                append_invoice_row(
                    row,
                    alloc.get("qty"),
                    row.get("rate"),
                    item_details,
                    batch_no=alloc.get("batch_no")
                )
                append_invoice_row(
                    row,
                    alloc.get("free_qty"),
                    0,
                    item_details,
                    batch_no=alloc.get("batch_no"),
                    description=f"Free Sample - {item_code}"
                )
        else:
            append_invoice_row(row, row.get("qty"), row.get("rate"), item_details)
            append_invoice_row(
                row,
                row.get("free_qty"),
                0,
                item_details,
                description=f"Free Sample - {item_code}"
            )

    if not invoice.items:
        return {
            "ready": False,
            "message": "Add item and quantity for live calculation.",
            "net_total": 0,
            "total_taxes_and_charges": 0,
            "grand_total": 0,
            "taxes": [],
            "tax_template": None,
            "items": []
        }

    if flt(data.get("bill_discount_amount")) > 0:
        invoice.apply_discount_on = "Grand Total"
        invoice.discount_amount = flt(data.get("bill_discount_amount"))

    tax_template = _apply_sales_taxes_template_for_live_calc(invoice, customer=customer)

    invoice.run_method("set_missing_values")

    if tax_template and not invoice.taxes:
        _apply_sales_taxes_template_for_live_calc(invoice, customer=customer)

    _ensure_tax_rows_for_live_item_tax_templates(invoice)

    invoice.calculate_taxes_and_totals()

    return {
        "ready": True,
        "message": "",
        "tax_template": tax_template,
        "net_total": flt(invoice.net_total),
        "total_taxes_and_charges": flt(invoice.total_taxes_and_charges),
        "grand_total": flt(invoice.grand_total),
        "rounded_total": flt(getattr(invoice, "rounded_total", 0)),
        "discount_amount": flt(getattr(invoice, "discount_amount", 0)),
        "taxes": [
            {
                "description": tax.description,
                "account_head": tax.account_head,
                "charge_type": tax.charge_type,
                "rate": flt(tax.rate),
                "tax_amount": flt(tax.tax_amount),
                "total": flt(tax.total),
                "item_wise_tax_detail": tax.item_wise_tax_detail
            }
            for tax in invoice.taxes
        ],
        "items": [
            {
                "item_code": item.item_code,
                "item_tax_template": item.item_tax_template,
                "net_amount": flt(item.net_amount),
                "amount": flt(item.amount)
            }
            for item in invoice.items
        ]
    }



@frappe.whitelist()
def get_customer_credit_snapshot(customer, company=None):
    if not customer:
        return {}

    outstanding = flt(frappe.db.sql("""
        SELECT SUM(outstanding_amount)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND customer = %s
          AND outstanding_amount > 0
    """, customer)[0][0] or 0)

    overdue = flt(frappe.db.sql("""
        SELECT SUM(outstanding_amount)
        FROM `tabSales Invoice`
        WHERE docstatus = 1
          AND customer = %s
          AND outstanding_amount > 0
          AND due_date IS NOT NULL
          AND due_date < CURDATE()
    """, customer)[0][0] or 0)

    credit_limit = 0

    try:
        if frappe.db.exists("DocType", "Customer Credit Limit"):
            conditions = ["parent = %s", "parenttype = 'Customer'"]
            values = [customer]

            if company:
                conditions.append("(company = %s OR IFNULL(company, '') = '')")
                values.append(company)

            rows = frappe.db.sql(f"""
                SELECT credit_limit
                FROM `tabCustomer Credit Limit`
                WHERE {' AND '.join(conditions)}
                ORDER BY CASE WHEN company = %s THEN 0 ELSE 1 END, idx ASC
                LIMIT 1
            """, tuple(values + [company or ""]), as_dict=True)

            if rows:
                credit_limit = flt(rows[0].credit_limit)
    except Exception:
        credit_limit = 0

    if not credit_limit:
        try:
            if frappe.get_meta("Customer").has_field("credit_limit"):
                credit_limit = flt(frappe.db.get_value("Customer", customer, "credit_limit") or 0)
        except Exception:
            credit_limit = 0

    available_credit = credit_limit - outstanding if credit_limit else 0

    status = "OK"
    if credit_limit and outstanding > credit_limit:
        status = "BLOCK"
    elif overdue > 0:
        status = "WARNING"

    return {
        "customer": customer,
        "outstanding": outstanding,
        "overdue": overdue,
        "credit_limit": credit_limit,
        "available_credit": available_credit,
        "status": status
    }


@frappe.whitelist()
def get_pharma_price_snapshot(item_code, price_list="Standard Selling"):
    """Return MRP/PTR/PTS/PTD from Item Price first, then Item master."""
    if not item_code:
        return {}

    price = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list, "selling": 1},
        ["price_list_rate", "pharma_mrp", "pharma_ptr", "pharma_pts", "pharma_ptd"],
        as_dict=True
    ) or {}

    item_vals = frappe.db.get_value(
        "Item",
        item_code,
        ["pharma_mrp", "pharma_ptr", "pharma_pts", "pharma_ptd", "pharma_brand", "pharma_composition", "pharma_manufacturer"],
        as_dict=True
    ) or {}

    return {
        "rate": flt(price.get("price_list_rate") or 0),
        "mrp": flt(price.get("pharma_mrp") or item_vals.get("pharma_mrp") or 0),
        "ptr": flt(price.get("pharma_ptr") or item_vals.get("pharma_ptr") or 0),
        "pts": flt(price.get("pharma_pts") or item_vals.get("pharma_pts") or 0),
        "ptd": flt(price.get("pharma_ptd") or item_vals.get("pharma_ptd") or 0),
        "brand": item_vals.get("pharma_brand"),
        "composition": item_vals.get("pharma_composition"),
        "manufacturer": item_vals.get("pharma_manufacturer")
    }



@frappe.whitelist()
def get_applicable_schemes(customer=None, item_code=None, qty=0, posting_date=None):
    """Return applicable pharma schemes for item/customer/qty.

    v20.3 supports per-multiple free-quantity behavior:
    10+1 and Qty 25 returns Free Qty 2.
    """
    if not item_code:
        return []

    posting_date = posting_date or nowdate()
    qty = flt(qty)

    item_group = frappe.db.get_value("Item", item_code, "item_group")
    customer_group = frappe.db.get_value("Customer", customer, "customer_group") if customer else None

    schemes = frappe.get_all(
        "Pharma Scheme",
        filters={"enabled": 1},
        fields=[
            "name", "scheme_name", "priority", "valid_from", "valid_to",
            "customer", "customer_group", "item_group", "apply_automatically"
        ],
        order_by="priority asc, modified desc"
    )

    applicable = []

    for scheme in schemes:
        if scheme.valid_from and getdate(scheme.valid_from) > getdate(posting_date):
            continue
        if scheme.valid_to and getdate(scheme.valid_to) < getdate(posting_date):
            continue
        if scheme.customer and scheme.customer != customer:
            continue
        if scheme.customer_group and scheme.customer_group != customer_group:
            continue
        if scheme.item_group and scheme.item_group != item_group:
            continue

        scheme_items = frappe.get_all(
            "Pharma Scheme Item",
            filters={"parent": scheme.name},
            fields=["item_code", "item_group"]
        )

        if scheme_items:
            matched = False
            for si in scheme_items:
                if si.item_code and si.item_code == item_code:
                    matched = True
                if si.item_group and si.item_group == item_group:
                    matched = True
            if not matched:
                continue

        slabs = frappe.get_all(
            "Pharma Scheme Slab",
            filters={"parent": scheme.name},
            fields=["min_qty", "free_qty"],
            order_by="min_qty desc"
        )

        best_slab = None
        for slab in slabs:
            if qty >= flt(slab.min_qty):
                best_slab = slab
                break

        if not best_slab:
            continue

        min_qty = flt(best_slab.min_qty)
        slab_free = flt(best_slab.free_qty)
        multiplier = int(qty // min_qty) if min_qty else 1
        calculated_free_qty = slab_free * max(multiplier, 1)

        applicable.append({
            "scheme": scheme.name,
            "scheme_name": scheme.scheme_name,
            "priority": scheme.priority,
            "free_qty": calculated_free_qty,
            "single_slab_free_qty": slab_free,
            "min_qty": min_qty,
            "multiplier": multiplier,
            "apply_automatically": scheme.apply_automatically
        })

    return applicable


@frappe.whitelist()
def apply_best_scheme(customer=None, item_code=None, qty=0, posting_date=None):
    """Return best auto-applicable scheme for a row."""
    schemes = get_applicable_schemes(customer=customer, item_code=item_code, qty=qty, posting_date=posting_date)
    for scheme in schemes:
        if scheme.get("apply_automatically"):
            return scheme
    return schemes[0] if schemes else None


@frappe.whitelist()
def pharma_item_search(txt="", warehouse=None, customer=None, price_list="Standard Selling", limit=20):
    """Smart pharma item search.

    Searches item code, item name, barcode, brand, composition, manufacturer.
    """
    txt = (txt or "").strip()
    like = f"%{txt}%"

    barcode_items = []
    if txt:
        barcode_items = frappe.get_all(
            "Item Barcode",
            filters={"barcode": ["like", like]},
            fields=["parent"],
            limit=limit
        )
    barcode_item_codes = [d.parent for d in barcode_items]

    conditions = ["disabled = 0"]
    values = []

    if txt:
        search_parts = [
            "item_code LIKE %s",
            "item_name LIKE %s"
        ]
        values.extend([like, like])

        for field in ["pharma_brand", "pharma_composition", "pharma_manufacturer"]:
            if frappe.get_meta("Item").has_field(field):
                search_parts.append(f"{field} LIKE %s")
                values.append(like)

        if barcode_item_codes:
            placeholders = ", ".join(["%s"] * len(barcode_item_codes))
            search_parts.append(f"item_code IN ({placeholders})")
            values.extend(barcode_item_codes)

        conditions.append("(" + " OR ".join(search_parts) + ")")

    values.append(int(limit))

    rows = frappe.db.sql(f"""
        SELECT
            item_code,
            item_name,
            stock_uom,
            item_group,
            pharma_brand,
            pharma_composition,
            pharma_manufacturer,
            pharma_mrp,
            pharma_ptr,
            pharma_pts,
            pharma_ptd
        FROM `tabItem`
        WHERE {' AND '.join(conditions)}
        ORDER BY item_name ASC
        LIMIT %s
    """, tuple(values), as_dict=True)

    results = []
    for row in rows:
        stock_qty = 0
        if warehouse:
            stock_qty = flt(frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": warehouse}, "actual_qty") or 0)

        price = get_pharma_price_snapshot(row.item_code, price_list=price_list)

        results.append({
            "item_code": row.item_code,
            "item_name": row.item_name,
            "stock_uom": row.stock_uom,
            "item_group": row.item_group,
            "brand": row.get("pharma_brand"),
            "composition": row.get("pharma_composition"),
            "manufacturer": row.get("pharma_manufacturer"),
            "stock_qty": stock_qty,
            "rate": price.get("rate"),
            "mrp": price.get("mrp"),
            "ptr": price.get("ptr"),
            "pts": price.get("pts"),
            "ptd": price.get("ptd")
        })

    return results

@frappe.whitelist()
def get_whatsapp_invoice_url(sales_invoice):
    inv = frappe.get_doc("Sales Invoice", sales_invoice)
    phone = None
    try:
        if frappe.get_meta("Customer").has_field("pharma_whatsapp_no"):
            phone = frappe.db.get_value("Customer", inv.customer, "pharma_whatsapp_no")
    except Exception:
        pass
    if not phone:
        phone = frappe.db.get_value("Customer", inv.customer, "mobile_no")
    message = f"Invoice {inv.name} amount {inv.grand_total}. Please contact us for the PDF copy."
    import urllib.parse
    encoded = urllib.parse.quote(message)
    phone_clean = "".join([c for c in str(phone or "") if c.isdigit()])
    return {"phone": phone_clean, "url": f"https://wa.me/{phone_clean}?text={encoded}" if phone_clean else None, "message": message}

@frappe.whitelist()
def get_license_expiry_dashboard(days=90):
    days = int(days or 90)
    out = []
    for dt in ["Customer", "Supplier"]:
        expiry_field = "pharma_drug_license_expiry"
        license_field = "pharma_drug_license_no"
        if not frappe.get_meta(dt).has_field(expiry_field):
            continue
        rows = frappe.db.sql(f"""
            SELECT name, {license_field} AS license_no, {expiry_field} AS expiry_date, DATEDIFF({expiry_field}, CURDATE()) AS days_to_expiry
            FROM `tab{dt}`
            WHERE {expiry_field} IS NOT NULL AND DATEDIFF({expiry_field}, CURDATE()) <= %s
            ORDER BY {expiry_field} ASC
        """, days, as_dict=True)
        for row in rows:
            row["party_type"] = dt
            out.append(row)
    return out


@frappe.whitelist()
def validate_pharma_return_data(data):
    """Validate return payload before creating Pharma Return."""
    if isinstance(data, str):
        data = frappe.parse_json(data)

    errors = []

    if not data.get("customer"):
        errors.append("Customer is required.")
    if not data.get("company"):
        errors.append("Company is required.")
    if not data.get("warehouse"):
        errors.append("Return Warehouse is required.")
    if not data.get("items"):
        errors.append("At least one return item is required.")

    for idx, row in enumerate(data.get("items", []), start=1):
        if not row.get("item_code"):
            errors.append(f"Row {idx}: Item is required.")
        if flt(row.get("qty")) <= 0:
            errors.append(f"Row {idx}: Qty must be greater than zero.")
        if row.get("batch_no") and not frappe.db.exists("Batch", row.get("batch_no")):
            errors.append(f"Row {idx}: Batch does not exist: {row.get('batch_no')}")

    return {
        "valid": not bool(errors),
        "errors": errors
    }


@frappe.whitelist()
def get_return_claim_dashboard(days=90):
    """Return summary metrics for pharma returns and claims."""
    days = int(days or 90)

    return_rows = frappe.db.sql("""
        SELECT
            return_type,
            status,
            COUNT(*) AS count
        FROM `tabPharma Return`
        WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY return_type, status
    """, days, as_dict=True)

    claim_rows = frappe.db.sql("""
        SELECT
            claim_type,
            status,
            COUNT(*) AS count,
            SUM(claim_amount) AS amount
        FROM `tabPharma Supplier Claim`
        WHERE posting_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        GROUP BY claim_type, status
    """, days, as_dict=True)

    return {
        "returns": return_rows,
        "claims": claim_rows
    }


@frappe.whitelist()
def get_customer_return_history(customer, limit=20):
    """Return recent customer returns."""
    if not customer:
        return []

    return frappe.get_all(
        "Pharma Return",
        filters={"customer": customer},
        fields=["name", "return_type", "posting_date", "status", "sales_return_invoice", "supplier_claim"],
        order_by="posting_date desc, modified desc",
        limit=int(limit or 20)
    )


def _resolve_supplier_for_claim_item(item_code):
    """Resolve supplier for a claim item safely.

    Priority:
    1. Item Default.default_supplier
    2. Latest Purchase Receipt supplier for the item
    3. Latest Purchase Invoice supplier for the item
    """
    supplier = frappe.db.get_value(
        "Item Default",
        {"parent": item_code},
        "default_supplier"
    )
    if supplier:
        return supplier

    row = frappe.db.sql("""
        SELECT pr.supplier
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.item_code = %s
          AND pr.docstatus = 1
          AND IFNULL(pr.supplier, '') != ''
        ORDER BY pr.posting_date DESC, pr.creation DESC
        LIMIT 1
    """, item_code, as_dict=True)
    if row:
        return row[0].supplier

    row = frappe.db.sql("""
        SELECT pi.supplier
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.item_code = %s
          AND pi.docstatus = 1
          AND IFNULL(pi.supplier, '') != ''
        ORDER BY pi.posting_date DESC, pi.creation DESC
        LIMIT 1
    """, item_code, as_dict=True)
    if row:
        return row[0].supplier

    return None


def _append_return_credit_note_item_from_original(credit_note, ret, return_row):
    """Append sales-return item row using original invoice row where possible.

    This preserves rate, discount, item tax template, income account, cost center,
    UOM and conversion factor better than constructing a bare row.
    """
    original = None

    if ret.against_sales_invoice:
        filters = {
            "parent": ret.against_sales_invoice,
            "item_code": return_row.item_code
        }
        if return_row.batch_no:
            filters["batch_no"] = return_row.batch_no

        original = frappe.db.get_value(
            "Sales Invoice Item",
            filters,
            [
                "item_code", "item_name", "description", "uom", "conversion_factor",
                "rate", "discount_percentage", "item_tax_template",
                "income_account", "cost_center", "warehouse"
            ],
            as_dict=True
        )

    values = {
        "item_code": return_row.item_code,
        "qty": -1 * flt(return_row.qty),
        "rate": flt(return_row.rate),
        "warehouse": ret.warehouse,
        "batch_no": return_row.batch_no
    }

    if original:
        for key in [
            "item_name", "description", "uom", "conversion_factor",
            "discount_percentage",
            "item_tax_template", "income_account", "cost_center"
        ]:
            if original.get(key) is not None:
                values[key] = original.get(key)

        # User-selected return warehouse should override original warehouse.
        values["warehouse"] = ret.warehouse
        if not values.get("rate"):
            values["rate"] = original.get("rate")

    credit_note.append("items", values)


@frappe.whitelist()
def create_pharma_return(data, create_credit_note=0):
    """Create Pharma Return and optionally ERPNext Sales Return Credit Note.

    v21.2 fixes:
    - validates payload before insert
    - maps original Sales Invoice item fields when credit note is created
    - uses return warehouse for stock receipt
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    validation = validate_pharma_return_data(data)
    if not validation.get("valid"):
        frappe.throw("<br>".join(validation.get("errors") or []))

    license_validation = validate_party_license_for_transaction(
        customer=data.get("customer"),
        posting_date=data.get("posting_date") or nowdate()
    )
    if not license_validation.get("valid"):
        frappe.throw("<br>".join(license_validation.get("messages") or []))

    ret = frappe.new_doc("Pharma Return")
    ret.return_type = data.get("return_type") or "Sales Return"
    ret.customer = data.get("customer")
    ret.company = data.get("company")
    ret.warehouse = data.get("warehouse")
    ret.posting_date = data.get("posting_date") or nowdate()
    ret.against_sales_invoice = data.get("against_sales_invoice")
    ret.status = "Draft"

    for row in data.get("items", []):
        ret.append("items", {
            "item_code": row.get("item_code"),
            "batch_no": row.get("batch_no"),
            "expiry_date": frappe.db.get_value("Batch", row.get("batch_no"), "expiry_date") if row.get("batch_no") else None,
            "qty": flt(row.get("qty")),
            "rate": flt(row.get("rate")),
            "reason": row.get("reason") or ret.return_type
        })

    ret.insert(ignore_permissions=True)
    ret.submit()
    ret.db_set("status", "Submitted")

    credit_note = None

    if int(create_credit_note):
        credit_note = frappe.new_doc("Sales Invoice")
        credit_note.customer = ret.customer
        credit_note.company = ret.company
        credit_note.posting_date = ret.posting_date
        credit_note.is_return = 1
        credit_note.return_against = ret.against_sales_invoice
        credit_note.update_stock = 1

        for row in ret.items:
            _append_return_credit_note_item_from_original(credit_note, ret, row)

        _copy_sales_invoice_taxes_from_original(credit_note, ret.against_sales_invoice)
        credit_note.run_method("set_missing_values")
        if ret.against_sales_invoice and not credit_note.taxes:
            _copy_sales_invoice_taxes_from_original(credit_note, ret.against_sales_invoice)
        credit_note.calculate_taxes_and_totals()
        credit_note.insert(ignore_permissions=True)
        credit_note.submit()

        ret.db_set("sales_return_invoice", credit_note.name)
        ret.db_set("status", "Credit Note Created")

    create_audit_log(
        "Pharma Return Created",
        reference_doctype="Pharma Return",
        reference_name=ret.name,
        severity="Info",
        details={"return_type": ret.return_type, "credit_note": credit_note.name if credit_note else None}
    )

    return {
        "pharma_return": ret.name,
        "sales_return_invoice": credit_note.name if credit_note else None
    }


@frappe.whitelist()
def create_supplier_claim_from_return(pharma_return, supplier=None):
    """Create Supplier Claim from submitted Pharma Return.

    v21.2 requires supplier to be resolved or explicitly provided.
    """
    ret = frappe.get_doc("Pharma Return", pharma_return)

    if not ret.items:
        frappe.throw("Return has no items.")

    resolved_supplier = supplier
    if not resolved_supplier:
        resolved_supplier = _resolve_supplier_for_claim_item(ret.items[0].item_code)

    if not resolved_supplier:
        frappe.throw(
            "Supplier could not be resolved. Please pass supplier explicitly "
            "or set default supplier / purchase history for the item."
        )

    claim = frappe.new_doc("Pharma Supplier Claim")
    claim.claim_type = "Expiry Claim" if ret.return_type == "Expiry Return" else "Breakage Claim"
    claim.supplier = resolved_supplier
    claim.company = ret.company
    claim.posting_date = nowdate()
    claim.status = "Draft"

    total = 0
    for row in ret.items:
        amount = flt(row.qty) * flt(row.rate)
        total += amount
        claim.append("items", {
            "item_code": row.item_code,
            "batch_no": row.batch_no,
            "expiry_date": row.expiry_date,
            "qty": row.qty,
            "rate": row.rate,
            "amount": amount,
            "source_return": ret.name
        })

    claim.claim_amount = total
    claim.insert(ignore_permissions=True)
    claim.submit()
    claim.db_set("status", "Submitted")

    ret.db_set("supplier_claim", claim.name)
    if ret.status != "Credit Note Created":
        ret.db_set("status", "Claim Created")

    return claim.name


def _create_replacement_batch_if_needed(item_code, source_batch_no=None, replacement_batch_no=None, expiry_date=None):
    """Create/use replacement batch safely.

    Replacement stock should not blindly reuse expired/damaged batch unless the
    user intentionally provides that batch.
    """
    if replacement_batch_no and frappe.db.exists("Batch", replacement_batch_no):
        return replacement_batch_no

    if replacement_batch_no:
        batch = frappe.new_doc("Batch")
        batch.batch_id = replacement_batch_no
        batch.item = item_code
        batch.expiry_date = expiry_date
        batch.insert(ignore_permissions=True)
        return batch.name

    source_expiry = None
    if source_batch_no:
        source_expiry = frappe.db.get_value("Batch", source_batch_no, "expiry_date")

    # For replacement goods, if no new batch is provided, create a generated batch.
    batch = frappe.new_doc("Batch")
    batch.batch_id = frappe.generate_hash(length=10)
    batch.item = item_code
    batch.expiry_date = expiry_date or source_expiry
    batch.insert(ignore_permissions=True)
    return batch.name


def _get_original_invoice_item_for_return(against_sales_invoice, item_code, batch_no=None):
    """Find the best matching original Sales Invoice Item for a return row."""
    if not against_sales_invoice or not item_code:
        return None

    filters = {
        "parent": against_sales_invoice,
        "item_code": item_code
    }
    if batch_no:
        filters["batch_no"] = batch_no

    row = frappe.db.get_value(
        "Sales Invoice Item",
        filters,
        [
            "name", "item_code", "item_name", "description", "uom", "conversion_factor",
            "qty", "rate", "amount", "net_rate", "net_amount",
            "discount_percentage", "discount_amount", "item_tax_template",
            "income_account", "cost_center", "warehouse", "batch_no"
        ],
        as_dict=True
    )

    if row:
        return row

    return frappe.db.get_value(
        "Sales Invoice Item",
        {
            "parent": against_sales_invoice,
            "item_code": item_code
        },
        [
            "name", "item_code", "item_name", "description", "uom", "conversion_factor",
            "qty", "rate", "amount", "net_rate", "net_amount",
            "discount_percentage", "discount_amount", "item_tax_template",
            "income_account", "cost_center", "warehouse", "batch_no"
        ],
        as_dict=True
    )


def _copy_sales_invoice_taxes_from_original(target_invoice, original_invoice_name):
    """Copy tax rows from original Sales Invoice into return Credit Note.

    This reduces tax divergence where item-wise tax templates or custom GST
    templates were used on the original invoice.
    """
    if not original_invoice_name:
        return

    try:
        original = frappe.get_doc("Sales Invoice", original_invoice_name)
    except Exception:
        return

    if original.taxes:
        target_invoice.set("taxes", [])
        target_invoice.taxes_and_charges = original.taxes_and_charges
        for tax in original.taxes:
            row = {}
            for key, value in tax.as_dict().items():
                if key in [
                    "charge_type", "row_id", "account_head", "description",
                    "included_in_print_rate", "included_in_paid_amount",
                    "cost_center", "rate", "account_currency",
                    "add_deduct_tax", "category"
                ]:
                    row[key] = value
            target_invoice.append("taxes", row)


@frappe.whitelist()
def create_expiry_return_and_supplier_claim(data, supplier=None, create_credit_note=1):
    """One-step UAT-safe flow:
    Expiry Return -> optional Sales Return Credit Note -> Supplier Claim.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    data["return_type"] = "Expiry Return"

    ret_result = create_pharma_return(data, create_credit_note=create_credit_note)
    claim_name = create_supplier_claim_from_return(
        ret_result.get("pharma_return"),
        supplier=supplier
    )

    return {
        "pharma_return": ret_result.get("pharma_return"),
        "sales_return_invoice": ret_result.get("sales_return_invoice"),
        "supplier_claim": claim_name
    }


@frappe.whitelist()
def settle_supplier_claim(pharma_supplier_claim, settlement_type="Credit Note", supplier_credit_note=None, notes=None, replacement_purchase_receipt=None):
    """Settle supplier claim.

    v21.3 hardening:
    - Credit Note settlement requires supplier_credit_note reference.
    - Replacement settlement may include linked replacement Purchase Receipt.
    """
    claim = frappe.get_doc("Pharma Supplier Claim", pharma_supplier_claim)

    if claim.docstatus == 0:
        claim.submit()

    if settlement_type == "Credit Note":
        if not supplier_credit_note:
            frappe.throw("Supplier Credit Note reference is required for Credit Note settlement.")
        claim.db_set("status", "Credit Note Received")
        claim.db_set("supplier_credit_note", supplier_credit_note)

    elif settlement_type == "Replacement":
        claim.db_set("status", "Replacement Received")
        if replacement_purchase_receipt:
            notes = ((notes or "") + f"\nReplacement Purchase Receipt: {replacement_purchase_receipt}").strip()

    elif settlement_type == "Rejected":
        claim.db_set("status", "Rejected")

    elif settlement_type == "Write Off":
        claim.db_set("status", "Closed")

    else:
        frappe.throw("Invalid settlement type.")

    if notes:
        claim.db_set("notes", notes)

    return {
        "claim": claim.name,
        "status": frappe.db.get_value("Pharma Supplier Claim", claim.name, "status")
    }


@frappe.whitelist()
def compare_return_credit_note_to_original(pharma_return=None, sales_return_invoice=None):
    """Compare return Credit Note to original invoice for tax/discount matching.

    Returns line-level comparison and summary. This is a UAT helper and audit tool.
    """
    if pharma_return:
        ret = frappe.get_doc("Pharma Return", pharma_return)
        sales_return_invoice = sales_return_invoice or ret.sales_return_invoice
        original_invoice = ret.against_sales_invoice
    else:
        ret = None
        if not sales_return_invoice:
            frappe.throw("sales_return_invoice or pharma_return is required.")
        si = frappe.get_doc("Sales Invoice", sales_return_invoice)
        original_invoice = si.return_against

    if not sales_return_invoice:
        frappe.throw("Sales Return Credit Note is missing.")
    if not original_invoice:
        frappe.throw("Original invoice reference is missing.")

    original = frappe.get_doc("Sales Invoice", original_invoice)
    returned = frappe.get_doc("Sales Invoice", sales_return_invoice)

    details = []
    for r_item in returned.items:
        orig = _get_original_invoice_item_for_return(
            original_invoice,
            r_item.item_code,
            r_item.batch_no
        )

        details.append({
            "item_code": r_item.item_code,
            "batch_no": r_item.batch_no,
            "return_qty": flt(r_item.qty),
            "return_rate": flt(r_item.rate),
            "original_rate": flt(orig.rate) if orig else None,
            "return_discount_percentage": flt(r_item.discount_percentage),
            "original_discount_percentage": flt(orig.discount_percentage) if orig else None,
            "return_item_tax_template": r_item.item_tax_template,
            "original_item_tax_template": orig.item_tax_template if orig else None,
            "rate_match": bool(orig and flt(r_item.rate) == flt(orig.rate)),
            "discount_match": bool(orig and flt(r_item.discount_percentage) == flt(orig.discount_percentage)),
            "tax_template_match": bool(orig and (r_item.item_tax_template or "") == (orig.item_tax_template or ""))
        })

    return {
        "original_invoice": original.name,
        "sales_return_invoice": returned.name,
        "original_grand_total": flt(original.grand_total),
        "return_grand_total_abs": abs(flt(returned.grand_total)),
        "original_taxes_and_charges": original.taxes_and_charges,
        "return_taxes_and_charges": returned.taxes_and_charges,
        "tax_template_match": (original.taxes_and_charges or "") == (returned.taxes_and_charges or ""),
        "items": details
    }


@frappe.whitelist()
def simulate_return_credit_note_from_original(original_sales_invoice, return_items=None):
    """Build an in-memory Sales Return Credit Note from the original Sales Invoice.

    Purpose:
    - UAT helper for GST / Item Tax Template behavior.
    - Does not insert or submit.
    - Compares calculated return totals to expected original proportional values.

    return_items optional:
    [
      {"item_code": "ITEM-001", "batch_no": "B1", "qty": 2}
    ]
    If omitted, simulates full return of all rows.
    """
    if isinstance(return_items, str):
        return_items = frappe.parse_json(return_items)

    original = frappe.get_doc("Sales Invoice", original_sales_invoice)

    credit_note = frappe.new_doc("Sales Invoice")
    credit_note.customer = original.customer
    credit_note.company = original.company
    credit_note.posting_date = nowdate()
    credit_note.is_return = 1
    credit_note.return_against = original.name
    credit_note.update_stock = 1
    credit_note.selling_price_list = original.selling_price_list
    credit_note.currency = original.currency
    credit_note.conversion_rate = original.conversion_rate

    wanted = return_items or []
    wanted_map = {}
    for row in wanted:
        key = (row.get("item_code"), row.get("batch_no") or "")
        wanted_map[key] = flt(row.get("qty"))

    expected_net = 0

    for orig in original.items:
        key = (orig.item_code, orig.batch_no or "")
        if wanted:
            return_qty = wanted_map.get(key)
            if not return_qty:
                # fallback if caller did not provide batch
                return_qty = wanted_map.get((orig.item_code, ""))
            if not return_qty:
                continue
        else:
            return_qty = abs(flt(orig.qty))

        ratio = return_qty / abs(flt(orig.qty)) if flt(orig.qty) else 1
        expected_net += flt(orig.net_amount) * ratio

        credit_note.append("items", {
            "item_code": orig.item_code,
            "item_name": orig.item_name,
            "description": orig.description,
            "qty": -1 * abs(flt(return_qty)),
            "uom": orig.uom,
            "conversion_factor": orig.conversion_factor,
            "rate": orig.rate,
            "discount_percentage": orig.discount_percentage,
            "discount_amount": getattr(orig, "discount_amount", 0),
            "item_tax_template": orig.item_tax_template,
            "income_account": orig.income_account,
            "cost_center": orig.cost_center,
            "warehouse": orig.warehouse,
            "batch_no": orig.batch_no
        })

    _copy_sales_invoice_taxes_from_original(credit_note, original.name)
    credit_note.run_method("set_missing_values")
    if not credit_note.taxes:
        _copy_sales_invoice_taxes_from_original(credit_note, original.name)
    credit_note.calculate_taxes_and_totals()

    item_debug = []
    for item in credit_note.items:
        item_debug.append({
            "item_code": item.item_code,
            "batch_no": item.batch_no,
            "qty": flt(item.qty),
            "rate": flt(item.rate),
            "discount_percentage": flt(item.discount_percentage),
            "item_tax_template": item.item_tax_template,
            "net_amount": flt(item.net_amount),
            "amount": flt(item.amount)
        })

    return {
        "ready": True,
        "original_sales_invoice": original.name,
        "simulated_return_net_total": flt(credit_note.net_total),
        "simulated_return_tax_total": flt(credit_note.total_taxes_and_charges),
        "simulated_return_grand_total": flt(credit_note.grand_total),
        "expected_original_net_proportion": flt(expected_net),
        "taxes_and_charges": credit_note.taxes_and_charges,
        "items": item_debug,
        "taxes": [
            {
                "account_head": tax.account_head,
                "description": tax.description,
                "rate": flt(tax.rate),
                "tax_amount": flt(tax.tax_amount),
                "item_wise_tax_detail": tax.item_wise_tax_detail
            }
            for tax in credit_note.taxes
        ]
    }


@frappe.whitelist()
def preflight_replacement_purchase_receipt(pharma_supplier_claim, target_warehouse=None, replacement_batches=None, require_new_batch=1):
    """Validate replacement PR before creation.

    Checks:
    - supplier / company / warehouse
    - batch-enabled item requires replacement batch_no
    - item with expiry requires replacement expiry_date
    - replacement batch belongs to correct item if it already exists
    """
    if isinstance(replacement_batches, str):
        replacement_batches = frappe.parse_json(replacement_batches)
    replacement_batches = replacement_batches or {}

    claim = frappe.get_doc("Pharma Supplier Claim", pharma_supplier_claim)

    errors = []
    warnings = []

    if not claim.supplier:
        errors.append("Supplier is missing on claim.")
    if not claim.company:
        errors.append("Company is missing on claim.")

    warehouse = target_warehouse or frappe.db.get_single_value("Stock Settings", "default_warehouse")
    if not warehouse:
        errors.append("Target warehouse is required.")

    for row in claim.items:
        item = frappe.db.get_value(
            "Item",
            row.item_code,
            ["has_batch_no", "has_expiry_date"],
            as_dict=True
        ) or {}

        repl = replacement_batches.get(row.name) or replacement_batches.get(row.item_code) or {}
        repl_batch_no = repl.get("batch_no")
        repl_expiry = repl.get("expiry_date")

        if int(require_new_batch):
            if item.get("has_batch_no") and not repl_batch_no:
                errors.append(f"{row.item_code}: replacement batch_no is required.")
            if item.get("has_expiry_date") and not repl_expiry:
                errors.append(f"{row.item_code}: replacement expiry_date is required.")

        if repl_batch_no and frappe.db.exists("Batch", repl_batch_no):
            batch_item = frappe.db.get_value("Batch", repl_batch_no, "item")
            if batch_item and batch_item != row.item_code:
                errors.append(f"{row.item_code}: replacement batch {repl_batch_no} belongs to item {batch_item}.")

        if row.batch_no and repl_batch_no and row.batch_no == repl_batch_no:
            errors.append(f"{row.item_code}: replacement batch cannot be same as source damaged/expired batch.")

        if not item.get("has_batch_no"):
            warnings.append(f"{row.item_code}: item is not batch-enabled.")

    return {
        "valid": not bool(errors),
        "errors": errors,
        "warnings": warnings,
        "warehouse": warehouse
    }


@frappe.whitelist()
def create_replacement_purchase_receipt(pharma_supplier_claim, target_warehouse=None, replacement_batches=None, require_new_batch=1):
    """Create Purchase Receipt for replacement stock after preflight validation."""
    preflight = preflight_replacement_purchase_receipt(
        pharma_supplier_claim=pharma_supplier_claim,
        target_warehouse=target_warehouse,
        replacement_batches=replacement_batches,
        require_new_batch=require_new_batch
    )

    if not preflight.get("valid"):
        frappe.throw("<br>".join(preflight.get("errors") or []))

    if isinstance(replacement_batches, str):
        replacement_batches = frappe.parse_json(replacement_batches)
    replacement_batches = replacement_batches or {}

    claim = frappe.get_doc("Pharma Supplier Claim", pharma_supplier_claim)
    warehouse = preflight.get("warehouse")

    pr = frappe.new_doc("Purchase Receipt")
    pr.supplier = claim.supplier
    pr.company = claim.company
    pr.posting_date = nowdate()

    for row in claim.items:
        repl = replacement_batches.get(row.name) or replacement_batches.get(row.item_code) or {}

        replacement_batch = _create_replacement_batch_if_needed(
            item_code=row.item_code,
            source_batch_no=None if int(require_new_batch) else row.batch_no,
            replacement_batch_no=repl.get("batch_no"),
            expiry_date=repl.get("expiry_date")
        )

        pr.append("items", {
            "item_code": row.item_code,
            "qty": flt(row.qty),
            "rate": flt(row.rate),
            "warehouse": warehouse,
            "batch_no": replacement_batch
        })

    pr.run_method("set_missing_values")
    pr.insert(ignore_permissions=True)
    pr.submit()

    settle_supplier_claim(
        pharma_supplier_claim=claim.name,
        settlement_type="Replacement",
        replacement_purchase_receipt=pr.name,
        notes=f"Replacement Purchase Receipt: {pr.name}"
    )

    return {
        "purchase_receipt": pr.name,
        "claim": claim.name,
        "preflight": preflight
    }


@frappe.whitelist()
def run_returns_claims_uat_checks(original_sales_invoice=None, pharma_supplier_claim=None, replacement_batches=None, target_warehouse=None):
    """Combined UAT helper for returns/claims hardening."""
    result = {
        "return_credit_note_simulation": None,
        "replacement_pr_preflight": None
    }

    if original_sales_invoice:
        result["return_credit_note_simulation"] = simulate_return_credit_note_from_original(original_sales_invoice)

    if pharma_supplier_claim:
        result["replacement_pr_preflight"] = preflight_replacement_purchase_receipt(
            pharma_supplier_claim=pharma_supplier_claim,
            target_warehouse=target_warehouse,
            replacement_batches=replacement_batches,
            require_new_batch=1
        )

    return result


@frappe.whitelist()
def create_audit_log(action, reference_doctype=None, reference_name=None, severity="Info", details=None):
    """Create immutable pharma audit log entry."""
    log = frappe.new_doc("Pharma Audit Log")
    log.posting_datetime = now_datetime()
    log.user = frappe.session.user
    log.action = action
    log.reference_doctype = reference_doctype
    log.reference_name = reference_name
    log.severity = severity or "Info"
    if isinstance(details, (dict, list)):
        log.details = frappe.as_json(details, indent=2)
    else:
        log.details = details
    log.insert(ignore_permissions=True)
    return log.name


@frappe.whitelist()
def check_drug_license_status(party_type, party, posting_date=None):
    """Check Customer/Supplier drug license expiry."""
    posting_date = getdate(posting_date or nowdate())

    if party_type not in ["Customer", "Supplier"]:
        return {"valid": True, "message": ""}

    meta = frappe.get_meta(party_type)
    if not meta.has_field("pharma_drug_license_expiry"):
        return {"valid": True, "message": "Drug license expiry field not configured."}

    expiry = frappe.db.get_value(party_type, party, "pharma_drug_license_expiry")
    license_no = frappe.db.get_value(party_type, party, "pharma_drug_license_no") if meta.has_field("pharma_drug_license_no") else None

    if not expiry:
        return {
            "valid": False,
            "status": "MISSING",
            "message": f"{party_type} {party} drug license expiry is missing.",
            "license_no": license_no,
            "expiry_date": expiry
        }

    if getdate(expiry) < posting_date:
        return {
            "valid": False,
            "status": "EXPIRED",
            "message": f"{party_type} {party} drug license expired on {expiry}.",
            "license_no": license_no,
            "expiry_date": expiry
        }

    return {
        "valid": True,
        "status": "OK",
        "message": "",
        "license_no": license_no,
        "expiry_date": expiry
    }


@frappe.whitelist()
def validate_party_license_for_transaction(customer=None, supplier=None, posting_date=None, allow_override=0):
    """Block expired/missing licenses when production setting is enabled."""
    try:
        enabled = frappe.db.get_single_value("Pharma Production Settings", "enable_license_block")
    except Exception:
        enabled = 1

    if not int(enabled):
        return {"valid": True, "messages": []}

    messages = []

    if customer:
        status = check_drug_license_status("Customer", customer, posting_date)
        if not status.get("valid"):
            messages.append(status.get("message"))

    if supplier:
        status = check_drug_license_status("Supplier", supplier, posting_date)
        if not status.get("valid"):
            messages.append(status.get("message"))

    if messages and not int(allow_override):
        return {"valid": False, "messages": messages}

    if messages and int(allow_override):
        create_audit_log(
            "Drug License Override",
            severity="Warning",
            details={"customer": customer, "supplier": supplier, "messages": messages}
        )

    return {"valid": True, "messages": messages}


@frappe.whitelist()
def create_approval_request(approval_type, reason=None, reference_doctype=None, reference_name=None):
    req = frappe.new_doc("Pharma Approval Request")
    req.approval_type = approval_type
    req.reason = reason
    req.reference_doctype = reference_doctype
    req.reference_name = reference_name
    req.status = "Pending"
    req.requested_by = frappe.session.user
    req.insert(ignore_permissions=True)
    create_audit_log(
        "Approval Requested",
        reference_doctype="Pharma Approval Request",
        reference_name=req.name,
        severity="Warning",
        details={"approval_type": approval_type, "reason": reason}
    )
    return req.name


@frappe.whitelist()
def approve_pharma_request(approval_request, notes=None):
    req = frappe.get_doc("Pharma Approval Request", approval_request)
    req.db_set("status", "Approved")
    req.db_set("approved_by", frappe.session.user)
    if notes:
        req.db_set("decision_notes", notes)
    create_audit_log(
        "Approval Approved",
        reference_doctype="Pharma Approval Request",
        reference_name=req.name,
        severity="Info",
        details={"notes": notes}
    )
    return req.name


@frappe.whitelist()
def reject_pharma_request(approval_request, notes=None):
    req = frappe.get_doc("Pharma Approval Request", approval_request)
    req.db_set("status", "Rejected")
    req.db_set("approved_by", frappe.session.user)
    if notes:
        req.db_set("decision_notes", notes)
    create_audit_log(
        "Approval Rejected",
        reference_doctype="Pharma Approval Request",
        reference_name=req.name,
        severity="Warning",
        details={"notes": notes}
    )
    return req.name


@frappe.whitelist()
def validate_gst_stock_for_invoice(sales_invoice):
    """Validate GST/item-tax and stock ledger consistency after invoice submit."""
    inv = frappe.get_doc("Sales Invoice", sales_invoice)

    issues = []

    for item in inv.items:
        if not item.item_code:
            continue

        item_master = frappe.db.get_value(
            "Item",
            item.item_code,
            ["has_batch_no", "has_expiry_date", "gst_hsn_code"],
            as_dict=True
        ) or {}

        if item_master.get("has_batch_no") and not item.batch_no:
            issues.append(f"{item.item_code}: batch_no missing on invoice row.")

        if not item.item_tax_template:
            # Not always mandatory, but important in user's pharma setup.
            issues.append(f"{item.item_code}: item_tax_template missing on invoice row.")

        if not item_master.get("gst_hsn_code"):
            issues.append(f"{item.item_code}: HSN code missing on Item master.")

    if inv.update_stock:
        sle_count = frappe.db.count("Stock Ledger Entry", {
            "voucher_type": "Sales Invoice",
            "voucher_no": inv.name
        })
        if not sle_count:
            issues.append("No Stock Ledger Entry found for stock-updated Sales Invoice.")

    return {
        "valid": not bool(issues),
        "issues": issues,
        "sales_invoice": inv.name,
        "grand_total": flt(inv.grand_total),
        "total_taxes_and_charges": flt(inv.total_taxes_and_charges)
    }


@frappe.whitelist()
def validate_pharma_transaction_preflight(customer=None, company=None, posting_date=None, projected_grand_total=0):
    """Combined production preflight: license + credit."""
    license_check = validate_party_license_for_transaction(customer=customer, posting_date=posting_date)
    credit_check = validate_credit_before_quick_sale(customer, company, projected_grand_total)

    valid = license_check.get("valid") and credit_check.get("allow", True)

    return {
        "valid": valid,
        "license": license_check,
        "credit": credit_check
    }


@frappe.whitelist()
def validate_credit_before_quick_sale(customer, company=None, projected_grand_total=0, allow_override=0):
    """Production hardened credit-control gate."""
    snapshot = get_customer_credit_snapshot(customer, company)

    try:
        enabled = frappe.db.get_single_value("Pharma Production Settings", "enable_credit_hard_block")
    except Exception:
        enabled = 1

    credit_limit = flt(snapshot.get("credit_limit"))
    outstanding = flt(snapshot.get("outstanding"))
    projected = flt(projected_grand_total)

    if int(enabled) and credit_limit and (outstanding + projected) > credit_limit and not int(allow_override):
        return {
            "allow": False,
            "status": "BLOCK",
            "message": (
                f"Credit limit exceeded. Limit: {credit_limit}, "
                f"Outstanding: {outstanding}, Current Bill: {projected}"
            ),
            "snapshot": snapshot
        }

    if credit_limit and (outstanding + projected) > credit_limit and int(allow_override):
        create_audit_log(
            "Credit Override",
            severity="Critical",
            details={"customer": customer, "company": company, "projected_grand_total": projected, "snapshot": snapshot}
        )

    if flt(snapshot.get("overdue")) > 0:
        return {
            "allow": True,
            "status": "WARNING",
            "message": f"Customer has overdue outstanding: {snapshot.get('overdue')}",
            "snapshot": snapshot
        }

    return {
        "allow": True,
        "status": "OK",
        "message": "",
        "snapshot": snapshot
    }


@frappe.whitelist()
def get_margin_scheme_impact(from_date=None, to_date=None):
    """Basic margin + discount/scheme impact analytics from Sales Invoice Items."""
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    rows = frappe.db.sql("""
        SELECT
            sii.item_code,
            i.item_name,
            SUM(sii.qty) AS qty,
            SUM(sii.net_amount) AS net_sales,
            SUM(IFNULL(sii.discount_amount, 0) * ABS(sii.qty)) AS discount_amount,
            SUM((sii.net_amount) - (IFNULL(sii.incoming_rate, 0) * ABS(sii.qty))) AS gross_margin
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabItem` i ON i.name = sii.item_code
        WHERE si.docstatus = 1
          AND si.posting_date BETWEEN %s AND %s
        GROUP BY sii.item_code, i.item_name
        ORDER BY net_sales DESC
    """, (from_date, to_date), as_dict=True)

    return rows


@frappe.whitelist()
def get_advanced_applicable_schemes(customer=None, item_code=None, qty=0, posting_date=None, bill_items=None):
    """Advanced sales scheme engine.

    Supports:
    - Free Qty
    - Discount %
    - Flat Discount
    - Brand/manufacturer filters
    - Mix-and-match combined quantity
    """
    if isinstance(bill_items, str):
        bill_items = frappe.parse_json(bill_items)
    bill_items = bill_items or []

    base = get_applicable_schemes(customer=customer, item_code=item_code, qty=qty, posting_date=posting_date)
    posting_date = posting_date or nowdate()
    qty = flt(qty)
    item = frappe.db.get_value("Item", item_code, ["item_group", "pharma_brand", "pharma_manufacturer"], as_dict=True) or {}
    customer_group = frappe.db.get_value("Customer", customer, "customer_group") if customer else None

    schemes = frappe.get_all(
        "Pharma Scheme",
        filters={"enabled": 1},
        fields=[
            "name", "scheme_name", "priority", "valid_from", "valid_to",
            "customer", "customer_group", "item_group", "scheme_type",
            "discount_percentage", "flat_discount_amount",
            "manufacturer", "brand", "allow_mix_and_match", "minimum_bill_qty",
            "apply_automatically"
        ],
        order_by="priority asc, modified desc"
    )

    advanced = []
    seen = {b.get("scheme") for b in base}

    for scheme in schemes:
        if scheme.name in seen:
            continue
        if scheme.valid_from and getdate(scheme.valid_from) > getdate(posting_date):
            continue
        if scheme.valid_to and getdate(scheme.valid_to) < getdate(posting_date):
            continue
        if scheme.customer and scheme.customer != customer:
            continue
        if scheme.customer_group and scheme.customer_group != customer_group:
            continue
        if scheme.item_group and scheme.item_group != item.get("item_group"):
            continue
        if scheme.brand and scheme.brand != item.get("pharma_brand"):
            continue
        if scheme.manufacturer and scheme.manufacturer != item.get("pharma_manufacturer"):
            continue

        effective_qty = qty
        if scheme.allow_mix_and_match:
            effective_qty = 0
            for row in bill_items:
                row_item = frappe.db.get_value("Item", row.get("item_code"), ["item_group", "pharma_brand", "pharma_manufacturer"], as_dict=True) or {}
                if scheme.item_group and row_item.get("item_group") != scheme.item_group:
                    continue
                if scheme.brand and row_item.get("pharma_brand") != scheme.brand:
                    continue
                if scheme.manufacturer and row_item.get("pharma_manufacturer") != scheme.manufacturer:
                    continue
                effective_qty += flt(row.get("qty"))

        if scheme.minimum_bill_qty and effective_qty < flt(scheme.minimum_bill_qty):
            continue

        advanced.append({
            "scheme": scheme.name,
            "scheme_name": scheme.scheme_name,
            "priority": scheme.priority,
            "scheme_type": scheme.scheme_type,
            "free_qty": 0,
            "discount_percentage": flt(scheme.discount_percentage),
            "flat_discount_amount": flt(scheme.flat_discount_amount),
            "effective_qty": effective_qty,
            "apply_automatically": scheme.apply_automatically
        })

    return sorted(base + advanced, key=lambda x: flt(x.get("priority") or 100))


@frappe.whitelist()
def apply_advanced_best_scheme(customer=None, item_code=None, qty=0, posting_date=None, bill_items=None):
    schemes = get_advanced_applicable_schemes(customer, item_code, qty, posting_date, bill_items)
    for scheme in schemes:
        if scheme.get("apply_automatically"):
            return scheme
    return schemes[0] if schemes else None


@frappe.whitelist()
def get_applicable_purchase_schemes(supplier=None, item_code=None, qty=0, posting_date=None):
    """Return purchase-side supplier schemes."""
    posting_date = posting_date or nowdate()
    qty = flt(qty)
    item_group = frappe.db.get_value("Item", item_code, "item_group") if item_code else None

    rows = frappe.get_all(
        "Pharma Purchase Scheme",
        filters={"enabled": 1},
        fields=[
            "name", "scheme_name", "supplier", "valid_from", "valid_to", "scheme_type",
            "item_code", "item_group", "min_qty", "free_qty", "discount_percentage", "flat_discount_amount"
        ],
        order_by="modified desc"
    )

    out = []
    for row in rows:
        if row.supplier and row.supplier != supplier:
            continue
        if row.valid_from and getdate(row.valid_from) > getdate(posting_date):
            continue
        if row.valid_to and getdate(row.valid_to) < getdate(posting_date):
            continue
        if row.item_code and row.item_code != item_code:
            continue
        if row.item_group and row.item_group != item_group:
            continue
        if qty < flt(row.min_qty):
            continue
        multiplier = int(qty // flt(row.min_qty)) if flt(row.min_qty) else 1
        out.append({
            "scheme": row.name,
            "scheme_name": row.scheme_name,
            "scheme_type": row.scheme_type,
            "free_qty": flt(row.free_qty) * max(multiplier, 1),
            "discount_percentage": flt(row.discount_percentage),
            "flat_discount_amount": flt(row.flat_discount_amount),
            "min_qty": flt(row.min_qty)
        })
    return out


@frappe.whitelist()
def apply_purchase_scheme_preview(supplier=None, item_code=None, qty=0, rate=0, posting_date=None):
    schemes = get_applicable_purchase_schemes(supplier, item_code, qty, posting_date)
    scheme = schemes[0] if schemes else None
    qty = flt(qty)
    rate = flt(rate)
    result = {
        "scheme": scheme,
        "base_amount": qty * rate,
        "free_qty": 0,
        "discount_amount": 0,
        "net_amount": qty * rate
    }
    if not scheme:
        return result
    if scheme.get("scheme_type") == "Free Qty":
        result["free_qty"] = flt(scheme.get("free_qty"))
    elif scheme.get("scheme_type") == "Discount %":
        result["discount_amount"] = result["base_amount"] * flt(scheme.get("discount_percentage")) / 100
    elif scheme.get("scheme_type") == "Flat Discount":
        result["discount_amount"] = flt(scheme.get("flat_discount_amount"))
    result["net_amount"] = result["base_amount"] - result["discount_amount"]
    return result


@frappe.whitelist()
def create_supplier_debit_note_for_claim(pharma_supplier_claim, expense_account=None, payable_account=None):
    """Create Purchase Invoice return/debit note for supplier claim.

    This is the accounting counterpart for monetary settlement.
    """
    claim = frappe.get_doc("Pharma Supplier Claim", pharma_supplier_claim)
    if not claim.supplier:
        frappe.throw("Supplier is required.")
    if not claim.items:
        frappe.throw("Claim has no items.")

    pi = frappe.new_doc("Purchase Invoice")
    pi.supplier = claim.supplier
    pi.company = claim.company
    pi.posting_date = nowdate()
    pi.is_return = 1

    for row in claim.items:
        values = {
            "item_code": row.item_code,
            "qty": -1 * flt(row.qty),
            "rate": flt(row.rate)
        }
        if expense_account:
            values["expense_account"] = expense_account
        pi.append("items", values)

    if payable_account:
        pi.credit_to = payable_account

    pi.run_method("set_missing_values")
    pi.calculate_taxes_and_totals()
    pi.insert(ignore_permissions=True)
    pi.submit()

    claim.db_set("status", "Credit Note Received")
    claim.db_set("supplier_credit_note", pi.name)
    create_audit_log(
        "Supplier Debit Note Created",
        reference_doctype="Pharma Supplier Claim",
        reference_name=claim.name,
        severity="Info",
        details={"purchase_invoice": pi.name}
    )
    return pi.name


@frappe.whitelist()
def get_composition_substitutes(item_code, warehouse=None, limit=10):
    """Suggest substitutes by same composition/salt before manual substitute map."""
    if not item_code:
        return []
    item = frappe.db.get_value("Item", item_code, ["pharma_composition", "item_group"], as_dict=True) or {}
    composition = item.get("pharma_composition")
    out = []
    if composition:
        rows = frappe.get_all(
            "Item",
            filters={
                "pharma_composition": composition,
                "disabled": 0,
                "name": ["!=", item_code]
            },
            fields=["name", "item_name", "stock_uom"],
            limit=int(limit)
        )
        for row in rows:
            stock_qty = flt(frappe.db.get_value("Bin", {"item_code": row.name, "warehouse": warehouse}, "actual_qty") or 0) if warehouse else 0
            out.append({
                "item_code": row.name,
                "item_name": row.item_name,
                "stock_uom": row.stock_uom,
                "substitution_type": "Same Composition",
                "stock_qty": stock_qty
            })
    manual = get_item_substitutes(item_code, warehouse)
    seen = {x["item_code"] for x in out}
    for row in manual:
        if row.get("item_code") not in seen:
            out.append(row)
    return out[:int(limit)]


@frappe.whitelist()
def create_mr_route_plan(sales_person, route_date=None, territory=None, customers=None):
    """Create MR route plan scaffold."""
    if isinstance(customers, str):
        customers = frappe.parse_json(customers)
    customers = customers or []

    doc = frappe.new_doc("Pharma MR Route Plan")
    doc.sales_person = sales_person
    doc.route_date = route_date or nowdate()
    doc.territory = territory
    doc.status = "Draft"

    for row in customers:
        doc.append("customers", {
            "customer": row.get("customer"),
            "planned_time": row.get("planned_time"),
            "notes": row.get("notes")
        })
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def get_mr_route_summary(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    filters = [["route_date", "between", [from_date, to_date]]]
    if sales_person:
        filters.append(["sales_person", "=", sales_person])
    return frappe.get_all(
        "Pharma MR Route Plan",
        filters=filters,
        fields=["name", "sales_person", "route_date", "territory", "status"],
        order_by="route_date desc"
    )

@frappe.whitelist()
def get_item_substitutes(item_code, warehouse=None):
    """Return mapped substitutes plus same-composition suggestions."""
    if not item_code:
        return []

    out = []

    # same composition/salt suggestions
    try:
        item = frappe.db.get_value("Item", item_code, ["pharma_composition"], as_dict=True) or {}
        composition = item.get("pharma_composition")
        if composition:
            rows = frappe.get_all(
                "Item",
                filters={"pharma_composition": composition, "disabled": 0, "name": ["!=", item_code]},
                fields=["name", "item_name", "stock_uom"],
                limit=10
            )
            for row in rows:
                stock_qty = flt(frappe.db.get_value("Bin", {"item_code": row.name, "warehouse": warehouse}, "actual_qty") or 0) if warehouse else 0
                out.append({
                    "item_code": row.name,
                    "item_name": row.item_name,
                    "stock_uom": row.stock_uom,
                    "substitution_type": "Same Composition",
                    "stock_qty": stock_qty
                })
    except Exception:
        pass

    seen = {x.get("item_code") for x in out}
    rows = frappe.get_all(
        "Pharma Item Substitute",
        filters={"item_code": item_code},
        fields=["substitute_item", "substitution_type", "priority"],
        order_by="priority asc"
    )

    for row in rows:
        if row.substitute_item in seen:
            continue
        item = frappe.db.get_value("Item", row.substitute_item, ["item_name", "stock_uom"], as_dict=True) or {}
        stock_qty = flt(frappe.db.get_value("Bin", {"item_code": row.substitute_item, "warehouse": warehouse}, "actual_qty") or 0) if warehouse else 0
        out.append({
            "item_code": row.substitute_item,
            "item_name": item.get("item_name"),
            "stock_uom": item.get("stock_uom"),
            "substitution_type": row.substitution_type,
            "stock_qty": stock_qty
        })
    return out


@frappe.whitelist()
def bulk_item_lookup(txt=None, warehouse=None, price_list="Standard Selling", limit=None, modified_after=None):
    try:
        default_limit = frappe.db.get_single_value("Pharma Fast Billing Profile", "search_cache_limit") or 5000
    except Exception:
        default_limit = 5000
    limit = int(limit or default_limit)
    conditions = ["i.disabled = 0"]
    values = []
    if txt:
        like = f"%{txt}%"
        cols = ["i.item_code LIKE %s", "i.item_name LIKE %s"]
        values += [like, like]
        for field in ["pharma_brand", "pharma_composition", "pharma_manufacturer"]:
            if frappe.get_meta("Item").has_field(field):
                cols.append(f"i.{field} LIKE %s")
                values.append(like)
        conditions.append("(" + " OR ".join(cols) + ")")
    if modified_after:
        conditions.append("i.modified >= %s")
        values.append(modified_after)
    values.append(limit)
    rows = frappe.db.sql(f"""
        SELECT i.item_code, i.item_name, i.stock_uom, i.item_group, i.gst_hsn_code,
               i.has_batch_no, i.has_expiry_date, i.pharma_brand, i.pharma_composition,
               i.pharma_manufacturer, i.pharma_mrp, i.pharma_ptr, i.pharma_pts, i.pharma_ptd,
               ip.price_list_rate AS rate
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip ON ip.item_code = i.item_code AND ip.price_list = %s AND ip.selling = 1
        WHERE {' AND '.join(conditions)}
        ORDER BY i.modified DESC
        LIMIT %s
    """, tuple([price_list] + values), as_dict=True)
    item_codes = [r.item_code for r in rows]
    barcode_map = {}
    if item_codes:
        for b in frappe.get_all("Item Barcode", filters={"parent": ["in", item_codes]}, fields=["parent", "barcode"]):
            barcode_map.setdefault(b.parent, []).append(b.barcode)
    stock_map = {}
    if warehouse and item_codes:
        for b in frappe.get_all("Bin", filters={"warehouse": warehouse, "item_code": ["in", item_codes]}, fields=["item_code", "actual_qty", "reserved_qty"]):
            stock_map[b.item_code] = {"actual_qty": flt(b.actual_qty), "reserved_qty": flt(b.reserved_qty)}
    out = []
    for row in rows:
        stock = stock_map.get(row.item_code, {})
        out.append({
            "item_code": row.item_code, "item_name": row.item_name, "stock_uom": row.stock_uom,
            "item_group": row.item_group, "gst_hsn_code": row.gst_hsn_code,
            "has_batch_no": row.has_batch_no, "has_expiry_date": row.has_expiry_date,
            "brand": row.get("pharma_brand"), "composition": row.get("pharma_composition"),
            "manufacturer": row.get("pharma_manufacturer"), "mrp": flt(row.get("pharma_mrp")),
            "ptr": flt(row.get("pharma_ptr")), "pts": flt(row.get("pharma_pts")),
            "ptd": flt(row.get("pharma_ptd")), "rate": flt(row.get("rate") or row.get("pharma_ptr") or 0),
            "barcodes": barcode_map.get(row.item_code, []), "actual_qty": stock.get("actual_qty", 0),
            "reserved_qty": stock.get("reserved_qty", 0)
        })
    return out

@frappe.whitelist()
def barcode_resolve(barcode, warehouse=None, price_list="Standard Selling"):
    if not barcode:
        return None
    item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")
    if not item_code and frappe.db.exists("Item", barcode):
        item_code = barcode
    if not item_code:
        return None
    items = bulk_item_lookup(txt=item_code, warehouse=warehouse, price_list=price_list, limit=5)
    exact = next((i for i in items if i.get("item_code") == item_code), None) or {"item_code": item_code, "item_name": frappe.db.get_value("Item", item_code, "item_name")}
    batches = quick_batch_allocate(item_code=item_code, warehouse=warehouse, qty=1) if warehouse else []
    return {"barcode": barcode, "item": exact, "default_qty": 1, "batch_allocations": batches}

@frappe.whitelist()
def quick_batch_allocate(item_code, warehouse, qty, include_free_qty=0):
    total_qty = flt(qty) + flt(include_free_qty)
    if total_qty <= 0:
        return []
    rows = frappe.db.sql("""
        SELECT sle.batch_no, b.expiry_date, SUM(sle.actual_qty) AS qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE sle.item_code = %s AND sle.warehouse = %s AND IFNULL(sle.batch_no, '') != ''
        GROUP BY sle.batch_no, b.expiry_date
        HAVING SUM(sle.actual_qty) > 0
        ORDER BY b.expiry_date ASC, sle.batch_no ASC
    """, (item_code, warehouse), as_dict=True)
    remaining = total_qty
    allocations = []
    for row in rows:
        if remaining <= 0:
            break
        alloc = min(flt(row.qty), remaining)
        allocations.append({"batch_no": row.batch_no, "expiry_date": row.expiry_date, "qty": alloc, "available_qty": flt(row.qty)})
        remaining -= alloc
    return allocations

@frappe.whitelist()
def async_scheme_preview(customer=None, item_code=None, qty=0, posting_date=None, bill_items=None):
    return apply_advanced_best_scheme(customer=customer, item_code=item_code, qty=qty, posting_date=posting_date, bill_items=bill_items) or {}

@frappe.whitelist()
def async_tax_preview(data):
    return get_live_sales_totals(data)

@frappe.whitelist()
def customer_credit_snapshot_fast(customer, company=None):
    return get_customer_credit_snapshot(customer, company)

@frappe.whitelist()
def held_invoice_save(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    doc = frappe.new_doc("Pharma Held Invoice")
    doc.customer = data.get("customer")
    doc.company = data.get("company")
    doc.warehouse = data.get("warehouse")
    doc.owner_user = frappe.session.user
    doc.held_datetime = now_datetime()
    doc.status = "Held"
    doc.grand_total = flt(data.get("grand_total") or 0)
    doc.payload = frappe.as_json(data, indent=2)
    doc.insert(ignore_permissions=True)
    create_audit_log("Invoice Held", reference_doctype="Pharma Held Invoice", reference_name=doc.name, severity="Info", details={"customer": doc.customer, "grand_total": doc.grand_total})
    return doc.name

@frappe.whitelist()
def held_invoice_restore(held_invoice):
    doc = frappe.get_doc("Pharma Held Invoice", held_invoice)
    doc.db_set("status", "Recalled")
    return frappe.parse_json(doc.payload)

@frappe.whitelist()
def held_invoice_list(owner_user=None, limit=20):
    return frappe.get_all("Pharma Held Invoice", filters={"owner_user": owner_user or frappe.session.user, "status": "Held"}, fields=["name", "customer", "company", "warehouse", "held_datetime", "grand_total"], order_by="held_datetime desc", limit=int(limit or 20))

@frappe.whitelist()
def held_invoice_cancel(held_invoice):
    doc = frappe.get_doc("Pharma Held Invoice", held_invoice)
    doc.db_set("status", "Cancelled")
    create_audit_log("Held Invoice Cancelled", reference_doctype="Pharma Held Invoice", reference_name=doc.name, severity="Warning")
    return doc.name

@frappe.whitelist()
def bulk_cache_sync(warehouse=None, price_list="Standard Selling", modified_after=None, limit=None):
    return {"items": bulk_item_lookup(warehouse=warehouse, price_list=price_list, modified_after=modified_after, limit=limit), "profile": {"default_cash_customer": frappe.db.get_single_value("Pharma Fast Billing Profile", "default_cash_customer"), "enable_keyboard_mode": frappe.db.get_single_value("Pharma Fast Billing Profile", "enable_keyboard_mode"), "auto_fefo_on_scan": frappe.db.get_single_value("Pharma Fast Billing Profile", "auto_fefo_on_scan"), "auto_apply_scheme_on_scan": frappe.db.get_single_value("Pharma Fast Billing Profile", "auto_apply_scheme_on_scan"), "compact_grid_mode": frappe.db.get_single_value("Pharma Fast Billing Profile", "compact_grid_mode")}}

@frappe.whitelist()
def fast_customer_search(txt=None, limit=20):
    txt = (txt or "").strip()
    if not txt:
        return []
    like = f"%{txt}%"
    conditions = ["disabled = 0"]
    values = []
    search = ["customer_name LIKE %s", "name LIKE %s"]
    values.extend([like, like])
    meta = frappe.get_meta("Customer")
    for field in ["mobile_no", "tax_id", "gstin", "pharma_drug_license_no", "pharma_whatsapp_no"]:
        if meta.has_field(field):
            search.append(f"{field} LIKE %s")
            values.append(like)
    conditions.append("(" + " OR ".join(search) + ")")
    values.append(int(limit or 20))
    return frappe.db.sql(f"""
        SELECT name, customer_name, customer_group, territory, mobile_no, pharma_drug_license_no, pharma_drug_license_expiry
        FROM `tabCustomer`
        WHERE {' AND '.join(conditions)}
        ORDER BY customer_name ASC
        LIMIT %s
    """, tuple(values), as_dict=True)

@frappe.whitelist()
def background_validation_snapshot(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    warnings, errors = [], []
    license_check = validate_party_license_for_transaction(customer=data.get("customer"), posting_date=data.get("posting_date") or nowdate())
    if not license_check.get("valid"):
        errors.extend(license_check.get("messages") or [])
    credit = get_customer_credit_snapshot(data.get("customer"), data.get("company")) if data.get("customer") else {}
    if credit.get("status") == "BLOCK":
        errors.append("Customer credit status is BLOCK.")
    elif credit.get("status") == "WARNING":
        warnings.append("Customer has overdue outstanding.")
    for row in data.get("items", []):
        if flt(row.get("qty")) <= 0:
            warnings.append(f"{row.get('item_code')}: quantity is zero or negative.")
    return {"valid": not bool(errors), "errors": errors, "warnings": warnings, "credit": credit}


@frappe.whitelist()
def bulk_customer_lookup(txt=None, limit=5000, modified_after=None):
    """Bulk customer payload for v24.1 IndexedDB cache."""
    limit = int(limit or 5000)
    meta = frappe.get_meta("Customer")
    fields = ["name", "customer_name", "customer_group", "territory", "mobile_no", "modified"]
    for field in ["tax_id", "gstin", "pharma_drug_license_no", "pharma_drug_license_expiry", "pharma_whatsapp_no"]:
        if meta.has_field(field):
            fields.append(field)

    if not txt and not modified_after:
        return frappe.get_all("Customer", filters={"disabled": 0}, fields=fields, order_by="modified desc", limit=limit)

    conditions = ["disabled = 0"]
    values = []
    if txt:
        like = f"%{txt}%"
        search = ["name LIKE %s", "customer_name LIKE %s"]
        values.extend([like, like])
        for field in ["mobile_no", "tax_id", "gstin", "pharma_drug_license_no", "pharma_whatsapp_no"]:
            if meta.has_field(field):
                search.append(f"{field} LIKE %s")
                values.append(like)
        conditions.append("(" + " OR ".join(search) + ")")
    if modified_after:
        conditions.append("modified >= %s")
        values.append(modified_after)
    values.append(limit)

    return frappe.db.sql(f"""
        SELECT {', '.join(fields)}
        FROM `tabCustomer`
        WHERE {' AND '.join(conditions)}
        ORDER BY modified DESC
        LIMIT %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def bulk_batch_lookup(warehouse=None, item_codes=None, modified_after=None, limit=50000):
    """Bulk batch/stock payload for local FEFO preview cache."""
    if isinstance(item_codes, str):
        item_codes = frappe.parse_json(item_codes)

    conditions = ["IFNULL(sle.batch_no, '') != ''"]
    values = []
    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)
    if item_codes:
        conditions.append("sle.item_code IN %s")
        values.append(tuple(item_codes))
    if modified_after:
        conditions.append("sle.modified >= %s")
        values.append(modified_after)
    values.append(int(limit or 50000))

    return frappe.db.sql(f"""
        SELECT sle.item_code, sle.warehouse, sle.batch_no, b.expiry_date,
               SUM(sle.actual_qty) AS actual_qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.item_code, sle.warehouse, sle.batch_no, b.expiry_date
        HAVING SUM(sle.actual_qty) > 0
        ORDER BY sle.item_code ASC, b.expiry_date ASC
        LIMIT %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_operator_benchmark_targets():
    return {
        "search_ms": 100,
        "scan_to_add_ms": 150,
        "line_add_ms": 150,
        "held_restore_ms": 2000,
        "invoice_50_lines_ms": 3000
    }


@frappe.whitelist()
def record_operator_benchmark(metric, elapsed_ms, context=None):
    details = {
        "metric": metric,
        "elapsed_ms": flt(elapsed_ms),
        "context": frappe.parse_json(context) if isinstance(context, str) else context
    }
    severity = "Info"
    targets = get_operator_benchmark_targets()
    if metric in targets and flt(elapsed_ms) > flt(targets[metric]):
        severity = "Warning"
    return create_audit_log("Fast Billing Benchmark", severity=severity, details=details)


@frappe.whitelist()
def fast_billing_bootstrap(warehouse=None, price_list="Standard Selling", item_limit=None, customer_limit=5000):
    return {
        "items": bulk_item_lookup(warehouse=warehouse, price_list=price_list, limit=item_limit),
        "customers": bulk_customer_lookup(limit=customer_limit),
        "batches": bulk_batch_lookup(warehouse=warehouse, limit=50000) if warehouse else [],
        "profile": {
            "default_cash_customer": frappe.db.get_single_value("Pharma Fast Billing Profile", "default_cash_customer"),
            "enable_keyboard_mode": frappe.db.get_single_value("Pharma Fast Billing Profile", "enable_keyboard_mode"),
            "auto_fefo_on_scan": frappe.db.get_single_value("Pharma Fast Billing Profile", "auto_fefo_on_scan"),
            "auto_apply_scheme_on_scan": frappe.db.get_single_value("Pharma Fast Billing Profile", "auto_apply_scheme_on_scan"),
            "compact_grid_mode": frappe.db.get_single_value("Pharma Fast Billing Profile", "compact_grid_mode")
        },
        "targets": get_operator_benchmark_targets()
    }


@frappe.whitelist()
def operator_payload_preflight(data):
    """Preflight validation for v24.2 operator billing shell."""
    if isinstance(data, str):
        data = frappe.parse_json(data)

    errors = []
    warnings = []

    if not data.get("customer"):
        warnings.append("Customer not selected. Default cash customer may be used.")
    if not data.get("company"):
        errors.append("Company is required.")
    if not data.get("warehouse"):
        errors.append("Warehouse is required.")
    if not data.get("items"):
        errors.append("At least one item is required.")

    if data.get("customer"):
        license_check = validate_party_license_for_transaction(
            customer=data.get("customer"),
            posting_date=data.get("posting_date") or nowdate()
        )
        if not license_check.get("valid"):
            errors.extend(license_check.get("messages") or [])

        credit = get_customer_credit_snapshot(data.get("customer"), data.get("company"))
        if credit.get("status") == "BLOCK":
            errors.append(credit.get("message") or "Customer credit is blocked.")
        elif credit.get("status") == "WARNING":
            warnings.append(credit.get("message") or "Customer has overdue outstanding.")

    for idx, row in enumerate(data.get("items") or [], start=1):
        if not row.get("item_code"):
            errors.append(f"Row {idx}: item_code missing.")
        if flt(row.get("qty")) <= 0:
            errors.append(f"Row {idx}: qty must be greater than zero.")
        if not row.get("batch_rows") and row.get("has_batch_no"):
            warnings.append(f"Row {idx}: batch allocation missing.")

    return {
        "valid": not bool(errors),
        "errors": errors,
        "warnings": warnings
    }


@frappe.whitelist()
def operator_save_held_invoice(data):
    """Operator shell held invoice save wrapper."""
    if isinstance(data, str):
        data = frappe.parse_json(data)
    return held_invoice_save(data)


@frappe.whitelist()
def calculate_sfa_target_achievement(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    target_filters = {"from_date": ["<=", to_date], "to_date": [">=", from_date]}
    if sales_person:
        target_filters["sales_person"] = sales_person

    targets = frappe.get_all(
        "Pharma Sales Target",
        filters=target_filters,
        fields=["name", "sales_person", "target_type", "item_code", "target_qty", "target_amount", "from_date", "to_date"]
    )

    out = []
    for t in targets:
        achieved_amount = 0
        achieved_qty = 0

        if t.target_type == "Secondary Sales":
            conditions = ["ss.docstatus = 1", "ss.period_from <= %s", "ss.period_to >= %s"]
            values = [to_date, from_date]
            if t.sales_person:
                conditions.append("ss.sales_person = %s")
                values.append(t.sales_person)
            if t.item_code:
                conditions.append("ssi.item_code = %s")
                values.append(t.item_code)
            rows = frappe.db.sql(f"""
                SELECT SUM(ssi.qty) qty, SUM(ssi.amount) amount
                FROM `tabPharma Secondary Sales Item` ssi
                INNER JOIN `tabPharma Secondary Sales` ss ON ss.name = ssi.parent
                WHERE {' AND '.join(conditions)}
            """, tuple(values), as_dict=True)
            achieved_qty = flt(rows[0].qty if rows else 0)
            achieved_amount = flt(rows[0].amount if rows else 0)

        elif t.target_type == "Doctor Visits":
            conditions = ["docstatus = 1", "dcr_date BETWEEN %s AND %s"]
            values = [from_date, to_date]
            if t.sales_person:
                conditions.append("sales_person = %s")
                values.append(t.sales_person)
            achieved_qty = frappe.db.count("Pharma DCR", filters={}) if False else flt(frappe.db.sql(f"SELECT COUNT(*) FROM `tabPharma DCR` WHERE {' AND '.join(conditions)}", tuple(values))[0][0])

        else:
            conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %s AND %s"]
            values = [from_date, to_date]
            if t.item_code:
                conditions.append("sii.item_code = %s")
                values.append(t.item_code)
            rows = frappe.db.sql(f"""
                SELECT SUM(ABS(sii.qty)) qty, SUM(sii.net_amount) amount
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE {' AND '.join(conditions)}
            """, tuple(values), as_dict=True)
            achieved_qty = flt(rows[0].qty if rows else 0)
            achieved_amount = flt(rows[0].amount if rows else 0)

        out.append({
            "target": t.name,
            "sales_person": t.sales_person,
            "target_type": t.target_type,
            "item_code": t.item_code,
            "target_qty": flt(t.target_qty),
            "achieved_qty": achieved_qty,
            "target_amount": flt(t.target_amount),
            "achieved_amount": achieved_amount,
            "achievement_percent": (achieved_amount / flt(t.target_amount) * 100) if flt(t.target_amount) else ((achieved_qty / flt(t.target_qty) * 100) if flt(t.target_qty) else 0)
        })

    return out


@frappe.whitelist()
def get_doctor_coverage_dashboard(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    doctor_filters = {"active": 1}
    if sales_person:
        doctor_filters["assigned_mr"] = sales_person

    total_doctors = frappe.db.count("Pharma Doctor", doctor_filters)

    conditions = ["dcr_date BETWEEN %s AND %s", "docstatus = 1"]
    values = [from_date, to_date]
    if sales_person:
        conditions.append("sales_person = %s")
        values.append(sales_person)

    visited = frappe.db.sql(f"""
        SELECT COUNT(DISTINCT doctor) AS count
        FROM `tabPharma DCR`
        WHERE {' AND '.join(conditions)}
    """, tuple(values), as_dict=True)[0].count or 0

    return {
        "sales_person": sales_person,
        "from_date": from_date,
        "to_date": to_date,
        "total_doctors": total_doctors,
        "visited_doctors": visited,
        "coverage_percent": (flt(visited) / flt(total_doctors) * 100) if total_doctors else 0
    }


@frappe.whitelist()
def get_mr_daily_summary(sales_person=None, date=None):
    date = date or nowdate()
    filters = {"dcr_date": date}
    if sales_person:
        filters["sales_person"] = sales_person

    dcr_count = frappe.db.count("Pharma DCR", filters)
    sample_rows = frappe.db.sql("""
        SELECT SUM(sl.qty) AS qty
        FROM `tabPharma Sample Line` sl
        INNER JOIN `tabPharma DCR` d ON d.name = sl.parent
        WHERE d.dcr_date = %s
          AND (%s IS NULL OR d.sales_person = %s)
    """, (date, sales_person, sales_person), as_dict=True)

    order_value = frappe.db.sql("""
        SELECT SUM(order_value) AS amount
        FROM `tabPharma DCR`
        WHERE dcr_date = %s
          AND (%s IS NULL OR sales_person = %s)
    """, (date, sales_person, sales_person), as_dict=True)

    return {
        "date": date,
        "sales_person": sales_person,
        "dcr_count": dcr_count,
        "samples_qty": flt(sample_rows[0].qty if sample_rows else 0),
        "order_value": flt(order_value[0].amount if order_value else 0)
    }


@frappe.whitelist()
def validate_sfa_required_links():
    """Production readiness check for SFA master-data dependencies."""
    issues = []

    required_doctypes = [
        "Pharma Doctor",
        "Pharma DCR",
        "Pharma Tour Plan",
        "Pharma Sample Issue",
        "Pharma Secondary Sales",
        "Pharma Sales Target",
        "Pharma MR Expense Claim"
    ]

    for dt in required_doctypes:
        if not frappe.db.exists("DocType", dt):
            issues.append(f"Missing DocType: {dt}")

    return {
        "valid": not bool(issues),
        "issues": issues
    }


@frappe.whitelist()
def create_dcr_from_tour_plan(tour_plan, doctor=None, visit_date=None, plan_line_idx=None):
    """Create DCR from Pharma Tour Plan.

    v25.1 fix:
    - Uses Pharma Tour Plan.plan_lines, not Pharma MR Route Plan.customers.
    - Allows explicit doctor.
    - Allows specific child-row index.
    - Falls back to first doctor in plan_lines.
    """
    plan = frappe.get_doc("Pharma Tour Plan", tour_plan)

    selected_line = None
    if plan_line_idx is not None:
        idx = int(plan_line_idx)
        if idx >= 0 and idx < len(plan.plan_lines):
            selected_line = plan.plan_lines[idx]

    if not selected_line:
        for row in plan.plan_lines:
            if row.doctor:
                selected_line = row
                break

    selected_doctor = doctor or (selected_line.doctor if selected_line else None)
    if not selected_doctor:
        frappe.throw("Doctor is required to create DCR from Tour Plan.")

    dcr = frappe.new_doc("Pharma DCR")
    dcr.dcr_date = visit_date or (selected_line.visit_date if selected_line and selected_line.visit_date else nowdate())
    dcr.sales_person = plan.sales_person
    dcr.territory = selected_line.territory if selected_line and selected_line.territory else plan.territory
    dcr.visit_type = "Planned"
    dcr.doctor = selected_doctor
    dcr.status = "Draft"
    dcr.insert(ignore_permissions=True)

    create_audit_log(
        "DCR Created From Tour Plan",
        reference_doctype="Pharma DCR",
        reference_name=dcr.name,
        severity="Info",
        details={"tour_plan": tour_plan, "doctor": selected_doctor}
    )
    return dcr.name


@frappe.whitelist()
def create_dcr_from_route(route_plan=None, doctor=None, customer=None, visit_date=None):
    """Backward-compatible DCR creation.

    If route_plan points to Pharma Tour Plan, use plan_lines.
    If it points to Pharma MR Route Plan from earlier version, use customers.
    """
    if not route_plan:
        frappe.throw("Route/Tour Plan is required.")

    if frappe.db.exists("Pharma Tour Plan", route_plan):
        return create_dcr_from_tour_plan(route_plan, doctor=doctor, visit_date=visit_date)

    if not frappe.db.exists("Pharma MR Route Plan", route_plan):
        frappe.throw("Route/Tour Plan not found.")

    route = frappe.get_doc("Pharma MR Route Plan", route_plan)
    selected_doctor = doctor

    # Earlier MR route customer table is customer-focused; doctor is optional if custom-added later.
    if not selected_doctor and hasattr(route, "customers"):
        for row in route.customers:
            if getattr(row, "doctor", None):
                selected_doctor = row.doctor
                break

    if not selected_doctor:
        frappe.throw("Doctor is required to create DCR from this route plan.")

    dcr = frappe.new_doc("Pharma DCR")
    dcr.dcr_date = visit_date or nowdate()
    dcr.sales_person = route.sales_person
    dcr.territory = route.territory
    dcr.visit_type = "Planned"
    dcr.doctor = selected_doctor
    dcr.status = "Draft"
    dcr.insert(ignore_permissions=True)

    create_audit_log(
        "DCR Created From Route Plan",
        reference_doctype="Pharma DCR",
        reference_name=dcr.name,
        severity="Info",
        details={"route_plan": route_plan, "doctor": selected_doctor, "customer": customer}
    )
    return dcr.name


@frappe.whitelist()
def submit_dcr_with_audit(pharma_dcr):
    """Submit DCR and write audit log."""
    doc = frappe.get_doc("Pharma DCR", pharma_dcr)
    if not doc.doctor:
        frappe.throw("Doctor is required.")
    if not doc.sales_person:
        frappe.throw("Sales Person is required.")
    if not doc.dcr_date:
        frappe.throw("DCR Date is required.")

    if doc.docstatus == 0:
        doc.submit()

    doc.db_set("status", "Submitted")
    create_audit_log(
        "DCR Submitted",
        reference_doctype="Pharma DCR",
        reference_name=doc.name,
        severity="Info",
        details={"doctor": doc.doctor, "sales_person": doc.sales_person}
    )
    return doc.name


@frappe.whitelist()
def approve_dcr(pharma_dcr, approve=1, notes=None):
    doc = frappe.get_doc("Pharma DCR", pharma_dcr)
    if doc.docstatus == 0:
        doc.submit()
    doc.db_set("status", "Approved" if int(approve) else "Rejected")
    create_audit_log(
        "DCR Approved" if int(approve) else "DCR Rejected",
        reference_doctype="Pharma DCR",
        reference_name=doc.name,
        severity="Info" if int(approve) else "Warning",
        details={"notes": notes, "doctor": doc.doctor, "sales_person": doc.sales_person}
    )
    return doc.name


@frappe.whitelist()
def approve_tour_plan(pharma_tour_plan, approve=1, notes=None):
    doc = frappe.get_doc("Pharma Tour Plan", pharma_tour_plan)
    if doc.docstatus == 0:
        doc.submit()
    doc.db_set("status", "Approved" if int(approve) else "Rejected")
    create_audit_log(
        "Tour Plan Approved" if int(approve) else "Tour Plan Rejected",
        reference_doctype="Pharma Tour Plan",
        reference_name=doc.name,
        severity="Info" if int(approve) else "Warning",
        details={"notes": notes, "sales_person": doc.sales_person}
    )
    return doc.name


@frappe.whitelist()
def calculate_secondary_sales_total(secondary_sales):
    doc = frappe.get_doc("Pharma Secondary Sales", secondary_sales)
    total = 0
    for row in doc.items:
        amount = flt(row.qty) * flt(row.rate)
        row.db_set("amount", amount) if row.name else None
        total += amount
    doc.db_set("total_amount", total)
    return total


@frappe.whitelist()
def create_sample_stock_entry(pharma_sample_issue):
    """Create stock issue for samples issued to MR.

    Production safeguards:
    - Requires source warehouse.
    - Requires sample items.
    - Avoids duplicate stock entry creation.
    """
    issue = frappe.get_doc("Pharma Sample Issue", pharma_sample_issue)

    if issue.stock_entry:
        return issue.stock_entry
    if not issue.source_warehouse:
        frappe.throw("Source Warehouse is required.")
    if not issue.items:
        frappe.throw("No sample items found.")

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Issue"
    se.posting_date = issue.posting_date or nowdate()

    for row in issue.items:
        if flt(row.qty) <= 0:
            frappe.throw(f"Sample qty must be greater than zero for item {row.item_code}.")
        se.append("items", {
            "item_code": row.item_code,
            "s_warehouse": issue.source_warehouse,
            "qty": flt(row.qty),
            "batch_no": row.batch_no
        })

    se.insert(ignore_permissions=True)
    se.submit()

    issue.db_set("stock_entry", se.name)
    issue.db_set("status", "Submitted")

    create_audit_log(
        "Sample Stock Entry Created",
        reference_doctype="Pharma Sample Issue",
        reference_name=issue.name,
        severity="Info",
        details={"stock_entry": se.name, "sales_person": issue.sales_person}
    )
    return se.name


@frappe.whitelist()
def get_sfa_go_live_checklist():
    return {
        "master_data": [
            "Create Sales Person hierarchy for MR / Area Manager / Regional Manager",
            "Create territories",
            "Import doctors with assigned MR",
            "Map products/items used for promotion",
            "Create distributors as Customers",
            "Create sample warehouses if sample stock is tracked separately"
        ],
        "transactions": [
            "Create Tour Plan",
            "Create DCR from Tour Plan",
            "Record products promoted",
            "Record samples given",
            "Create Sample Issue and Stock Entry",
            "Upload Secondary Sales",
            "Create Sales Targets",
            "Run Target Achievement report"
        ],
        "uat": [
            "MR submits DCR",
            "Manager approves/rejects DCR",
            "Tour Plan approval works",
            "Sample issue reduces sample warehouse stock",
            "Secondary sales dashboard matches uploaded data",
            "Target achievement report matches expected results"
        ]
    }


def _date_range_for_month(month, year):
    import calendar
    month = int(month)
    year = int(year)
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"


@frappe.whitelist()
def calculate_weighted_score(primary_sales_percent=0, doctor_coverage_percent=0, secondary_sales_percent=0, product_promotion_percent=0, performance_plan=None):
    plan = frappe.get_doc("Pharma Performance Plan", performance_plan) if performance_plan else None
    weights = {
        "primary": flt(plan.primary_sales_weight if plan else 40),
        "coverage": flt(plan.doctor_coverage_weight if plan else 30),
        "secondary": flt(plan.secondary_sales_weight if plan else 20),
        "promotion": flt(plan.product_promotion_weight if plan else 10)
    }
    score = (
        flt(primary_sales_percent) * weights["primary"] / 100 +
        flt(doctor_coverage_percent) * weights["coverage"] / 100 +
        flt(secondary_sales_percent) * weights["secondary"] / 100 +
        flt(product_promotion_percent) * weights["promotion"] / 100
    )
    return {"weighted_score": score, "weights": weights}


@frappe.whitelist()
def generate_monthly_scorecard(sales_person, month, year, performance_plan):
    from_date, to_date = _date_range_for_month(month, year)
    plan = frappe.get_doc("Pharma Performance Plan", performance_plan)

    achievement = calculate_sfa_target_achievement(sales_person, from_date, to_date)
    primary_pct = 0
    secondary_pct = 0
    promo_pct = 0
    for row in achievement:
        if row.get("target_type") == "Primary Sales":
            primary_pct = max(primary_pct, flt(row.get("achievement_percent")))
        elif row.get("target_type") == "Secondary Sales":
            secondary_pct = max(secondary_pct, flt(row.get("achievement_percent")))
        elif row.get("target_type") == "Product Promotion":
            promo_pct = max(promo_pct, flt(row.get("achievement_percent")))

    coverage = get_doctor_coverage_dashboard(sales_person, from_date, to_date)
    coverage_pct = flt(coverage.get("coverage_percent"))

    score_result = calculate_weighted_score(primary_pct, coverage_pct, secondary_pct, promo_pct, performance_plan)
    weighted_score = flt(score_result.get("weighted_score"))

    incentive_pct = 0
    fixed_amount = 0
    for slab in plan.slabs:
        if weighted_score >= flt(slab.from_score) and weighted_score <= flt(slab.to_score):
            incentive_pct = flt(slab.incentive_percentage)
            fixed_amount = flt(slab.fixed_amount)
            break

    sc = frappe.new_doc("Pharma Monthly Scorecard")
    sc.performance_plan = performance_plan
    sc.sales_person = sales_person
    sc.month = int(month)
    sc.year = int(year)
    sc.primary_sales_percent = primary_pct
    sc.doctor_coverage_percent = coverage_pct
    sc.secondary_sales_percent = secondary_pct
    sc.product_promotion_percent = promo_pct
    sc.weighted_score = weighted_score
    sc.incentive_percentage = incentive_pct
    sc.incentive_amount = fixed_amount
    sc.details = frappe.as_json({"achievement": achievement, "coverage": coverage, "weights": score_result.get("weights")}, indent=2)
    sc.insert(ignore_permissions=True)
    create_audit_log("Monthly Scorecard Generated", "Pharma Monthly Scorecard", sc.name, "Info", {"sales_person": sales_person, "score": weighted_score})
    return sc.name


@frappe.whitelist()
def get_primary_secondary_gap(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    primary_conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %s AND %s"]
    primary_values = [from_date, to_date]
    if sales_person:
        primary_conditions.append("c.pharma_salesman = %s")
        primary_values.append(sales_person)

    primary = frappe.db.sql(f"""
        SELECT SUM(si.net_total) AS amount
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        WHERE {' AND '.join(primary_conditions)}
    """, tuple(primary_values), as_dict=True)[0].amount or 0

    sec_conditions = ["ss.docstatus = 1", "ss.period_from <= %s", "ss.period_to >= %s"]
    sec_values = [to_date, from_date]
    if sales_person:
        sec_conditions.append("ss.sales_person = %s")
        sec_values.append(sales_person)
    secondary = frappe.db.sql(f"""
        SELECT SUM(ss.total_amount) AS amount
        FROM `tabPharma Secondary Sales` ss
        WHERE {' AND '.join(sec_conditions)}
    """, tuple(sec_values), as_dict=True)[0].amount or 0

    return {
        "sales_person": sales_person,
        "from_date": from_date,
        "to_date": to_date,
        "primary_sales": flt(primary),
        "secondary_sales": flt(secondary),
        "gap": flt(primary) - flt(secondary),
        "secondary_liquidation_percent": (flt(secondary) / flt(primary) * 100) if flt(primary) else 0
    }


@frappe.whitelist()
def calculate_doctor_potential_scores(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -90)
    to_date = to_date or nowdate()
    filters = {"active": 1}
    if sales_person:
        filters["assigned_mr"] = sales_person

    doctors = frappe.get_all("Pharma Doctor", filters=filters, fields=["name", "assigned_mr", "potential_value", "current_share", "target_share"])
    results = []
    for d in doctors:
        visits = frappe.db.count("Pharma DCR", {"doctor": d.name, "dcr_date": ["between", [from_date, to_date]], "docstatus": 1})
        promo_count = frappe.db.sql("""
            SELECT COUNT(*)
            FROM `tabPharma Promoted Product` pp
            INNER JOIN `tabPharma DCR` dcr ON dcr.name = pp.parent
            WHERE dcr.doctor = %s AND dcr.dcr_date BETWEEN %s AND %s AND dcr.docstatus = 1
        """, (d.name, from_date, to_date))[0][0]

        potential_score = min(flt(d.potential_value) / 10000, 40)
        visit_score = min(visits * 5, 30)
        share_gap_score = max(flt(d.target_share) - flt(d.current_share), 0) * 0.2
        promo_score = min(flt(promo_count) * 3, 20)
        score = potential_score + visit_score + share_gap_score + promo_score

        category = "C"
        if score >= 80:
            category = "A+"
        elif score >= 60:
            category = "A"
        elif score >= 40:
            category = "B"

        frappe.db.set_value("Pharma Doctor", d.name, {"influence_score": score, "potential_category": category})
        results.append({"doctor": d.name, "score": score, "potential_category": category, "visits": visits, "promotions": promo_count})

    return results


@frappe.whitelist()
def create_sample_ledger_from_issue(sample_issue):
    issue = frappe.get_doc("Pharma Sample Issue", sample_issue)
    created = []
    for row in issue.items:
        ledger = frappe.new_doc("Pharma Sample Ledger")
        ledger.posting_date = issue.posting_date or nowdate()
        ledger.sales_person = issue.sales_person
        ledger.item_code = row.item_code
        ledger.batch_no = row.batch_no
        ledger.expiry_date = frappe.db.get_value("Batch", row.batch_no, "expiry_date") if row.batch_no else None
        ledger.transaction_type = "Issued"
        ledger.qty = flt(row.qty)
        ledger.reference_doctype = "Pharma Sample Issue"
        ledger.reference_name = issue.name
        ledger.insert(ignore_permissions=True)
        created.append(ledger.name)
    return created


@frappe.whitelist()
def create_sample_ledger_from_dcr(pharma_dcr):
    dcr = frappe.get_doc("Pharma DCR", pharma_dcr)
    created = []
    for row in dcr.samples_given:
        ledger = frappe.new_doc("Pharma Sample Ledger")
        ledger.posting_date = dcr.dcr_date or nowdate()
        ledger.sales_person = dcr.sales_person
        ledger.item_code = row.item_code
        ledger.batch_no = row.batch_no
        ledger.expiry_date = frappe.db.get_value("Batch", row.batch_no, "expiry_date") if row.batch_no else None
        ledger.transaction_type = "Distributed"
        ledger.qty = -1 * flt(row.qty)
        ledger.reference_doctype = "Pharma DCR"
        ledger.reference_name = dcr.name
        ledger.insert(ignore_permissions=True)
        created.append(ledger.name)
    return created


@frappe.whitelist()
def get_sample_balance(sales_person=None, item_code=None):
    conditions = []
    values = []
    if sales_person:
        conditions.append("sales_person = %s")
        values.append(sales_person)
    if item_code:
        conditions.append("item_code = %s")
        values.append(item_code)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return frappe.db.sql(f"""
        SELECT sales_person, item_code, batch_no, expiry_date, SUM(qty) AS balance_qty
        FROM `tabPharma Sample Ledger`
        {where}
        GROUP BY sales_person, item_code, batch_no, expiry_date
        HAVING SUM(qty) != 0
        ORDER BY sales_person, item_code, expiry_date
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_sample_aging(sales_person=None):
    rows = get_sample_balance(sales_person=sales_person)
    today = getdate(nowdate())
    out = []
    for r in rows:
        days_to_expiry = None
        bucket = "No Expiry"
        if r.expiry_date:
            days_to_expiry = (getdate(r.expiry_date) - today).days
            if days_to_expiry <= 30:
                bucket = "0-30"
            elif days_to_expiry <= 60:
                bucket = "31-60"
            elif days_to_expiry <= 90:
                bucket = "61-90"
            else:
                bucket = "90+"
        r["days_to_expiry"] = days_to_expiry
        r["aging_bucket"] = bucket
        out.append(r)
    return out


@frappe.whitelist()
def calculate_territory_kpi(territory, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    doctors_assigned = frappe.db.count("Pharma Doctor", {"territory": territory, "active": 1})
    doctors_covered = frappe.db.sql("""
        SELECT COUNT(DISTINCT doctor) AS count
        FROM `tabPharma DCR`
        WHERE territory = %s AND dcr_date BETWEEN %s AND %s AND docstatus = 1
    """, (territory, from_date, to_date), as_dict=True)[0].count or 0

    primary_sales = frappe.db.sql("""
        SELECT SUM(si.net_total) AS amount
        FROM `tabSales Invoice` si
        WHERE si.territory = %s AND si.posting_date BETWEEN %s AND %s AND si.docstatus = 1
    """, (territory, from_date, to_date), as_dict=True)[0].amount or 0

    secondary_sales = frappe.db.sql("""
        SELECT SUM(total_amount) AS amount
        FROM `tabPharma Secondary Sales`
        WHERE territory = %s AND period_from <= %s AND period_to >= %s AND docstatus = 1
    """, (territory, to_date, from_date), as_dict=True)[0].amount or 0

    kpi = frappe.new_doc("Pharma Territory KPI")
    kpi.territory = territory
    kpi.from_date = from_date
    kpi.to_date = to_date
    kpi.doctors_assigned = doctors_assigned
    kpi.doctors_covered = doctors_covered
    kpi.coverage_percent = (flt(doctors_covered) / flt(doctors_assigned) * 100) if doctors_assigned else 0
    kpi.primary_sales = flt(primary_sales)
    kpi.secondary_sales = flt(secondary_sales)
    kpi.potential_percent = kpi.coverage_percent
    kpi.insert(ignore_permissions=True)
    return kpi.name


@frappe.whitelist()
def get_beat_compliance(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    planned_conditions = ["parenttype = 'Pharma Tour Plan'", "visit_date BETWEEN %s AND %s"]
    planned_values = [from_date, to_date]
    if sales_person:
        planned_conditions.append("parent IN (SELECT name FROM `tabPharma Tour Plan` WHERE sales_person = %s)")
        planned_values.append(sales_person)

    planned = frappe.db.sql(f"""
        SELECT COUNT(*) AS count FROM `tabPharma Tour Plan Line`
        WHERE {' AND '.join(planned_conditions)}
    """, tuple(planned_values), as_dict=True)[0].count or 0

    actual_filters = {"dcr_date": ["between", [from_date, to_date]], "docstatus": 1}
    if sales_person:
        actual_filters["sales_person"] = sales_person
    actual = frappe.db.count("Pharma DCR", actual_filters)

    return {
        "sales_person": sales_person,
        "from_date": from_date,
        "to_date": to_date,
        "planned_visits": planned,
        "actual_visits": actual,
        "compliance_percent": (flt(actual) / flt(planned) * 100) if planned else 0
    }


@frappe.whitelist()
def get_executive_cockpit(from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    top_mrs = frappe.db.sql("""
        SELECT sales_person, COUNT(*) AS visits, SUM(order_value) AS order_value
        FROM `tabPharma DCR`
        WHERE dcr_date BETWEEN %s AND %s AND docstatus = 1
        GROUP BY sales_person
        ORDER BY order_value DESC, visits DESC
        LIMIT 10
    """, (from_date, to_date), as_dict=True)

    gap = get_primary_secondary_gap(from_date=from_date, to_date=to_date)

    top_doctors = frappe.get_all("Pharma Doctor", fields=["name", "doctor_name", "potential_category", "influence_score"], order_by="influence_score desc", limit=10)

    return {
        "from_date": from_date,
        "to_date": to_date,
        "primary_secondary_gap": gap,
        "top_mrs": top_mrs,
        "top_doctors": top_doctors
    }


@frappe.whitelist()
def get_batch_history(item_code, warehouse=None, customer=None):
    conditions = ["sle.item_code = %s", "IFNULL(sle.batch_no, '') != ''"]
    values = [item_code]
    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)
    rows = frappe.db.sql(f"""
        SELECT sle.batch_no, b.expiry_date, sle.warehouse, SUM(sle.actual_qty) AS available_qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.batch_no, b.expiry_date, sle.warehouse
        HAVING SUM(sle.actual_qty) > 0
        ORDER BY b.expiry_date ASC, sle.batch_no ASC
    """, tuple(values), as_dict=True)
    out = []
    for row in rows:
        lp = frappe.db.sql("""
            SELECT pri.parent AS purchase_receipt, pr.supplier, pr.posting_date, pri.rate
            FROM `tabPurchase Receipt Item` pri
            INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pri.item_code = %s AND IFNULL(pri.batch_no, '') = %s AND pr.docstatus = 1
            ORDER BY pr.posting_date DESC, pr.modified DESC LIMIT 1
        """, (item_code, row.batch_no), as_dict=True)
        ls = frappe.db.sql("""
            SELECT sii.parent AS sales_invoice, si.customer, si.posting_date, sii.rate, sii.discount_percentage
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE sii.item_code = %s AND IFNULL(sii.batch_no, '') = %s AND si.docstatus = 1
            ORDER BY si.posting_date DESC, si.modified DESC LIMIT 1
        """, (item_code, row.batch_no), as_dict=True)
        p = lp[0] if lp else {}
        s = ls[0] if ls else {}
        days = (getdate(row.expiry_date) - getdate(nowdate())).days if row.expiry_date else None
        out.append({
            "batch_no": row.batch_no, "expiry_date": row.expiry_date, "warehouse": row.warehouse,
            "available_qty": flt(row.available_qty), "purchase_rate": flt(p.get("rate")),
            "supplier": p.get("supplier"), "purchase_date": p.get("posting_date"),
            "last_sale_rate": flt(s.get("rate")), "last_sale_discount": flt(s.get("discount_percentage")),
            "last_sale_customer": s.get("customer"), "last_sale_date": s.get("posting_date"),
            "days_to_expiry": days, "near_expiry": bool(days is not None and days <= 90)
        })
    return out


@frappe.whitelist()
def get_last_sale_history(item_code, customer=None, limit=5):
    conditions = ["sii.item_code = %s", "si.docstatus = 1"]
    values = [item_code]
    if customer:
        conditions.append("si.customer = %s")
        values.append(customer)
    values.append(int(limit or 5))
    return frappe.db.sql(f"""
        SELECT si.name AS sales_invoice, si.customer, si.posting_date, sii.qty, sii.rate,
               sii.discount_percentage, sii.batch_no, sii.net_amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(conditions)}
        ORDER BY si.posting_date DESC, si.modified DESC LIMIT %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_last_purchase_history(item_code, limit=5):
    return frappe.db.sql("""
        SELECT pr.name AS purchase_receipt, pr.supplier, pr.posting_date, pri.qty, pri.rate, pri.batch_no, pri.amount
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.item_code = %s AND pr.docstatus = 1
        ORDER BY pr.posting_date DESC, pr.modified DESC LIMIT %s
    """, (item_code, int(limit or 5)), as_dict=True)


@frappe.whitelist()
def get_customer_buying_pattern(customer, item_code=None):
    conditions = ["si.customer = %s", "si.docstatus = 1", "si.posting_date >= %s"]
    values = [customer, add_days(nowdate(), -365)]
    if item_code:
        conditions.append("sii.item_code = %s")
        values.append(item_code)
    rows = frappe.db.sql(f"""
        SELECT sii.item_code, SUM(ABS(sii.qty)) AS qty, SUM(sii.net_amount) AS amount, MAX(si.posting_date) AS last_sale_date
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(conditions)}
        GROUP BY sii.item_code ORDER BY amount DESC LIMIT 10
    """, tuple(values), as_dict=True)
    last_order = frappe.db.get_value("Sales Invoice", {"customer": customer, "docstatus": 1}, ["name", "posting_date", "grand_total"], order_by="posting_date desc", as_dict=True)
    return {"customer": customer, "last_order": last_order, "top_products": rows, "average_monthly_amount": sum(flt(r.amount) for r in rows) / 12 if rows else 0}


@frappe.whitelist()
def get_customer_outstanding_snapshot(customer, company=None):
    snapshot = get_customer_credit_snapshot(customer, company)
    last_payment = frappe.db.sql("""
        SELECT name, posting_date, paid_amount FROM `tabPayment Entry`
        WHERE party_type = 'Customer' AND party = %s AND docstatus = 1
        ORDER BY posting_date DESC, modified DESC LIMIT 1
    """, (customer,), as_dict=True)
    snapshot["last_payment"] = last_payment[0] if last_payment else None
    return snapshot


@frappe.whitelist()
def get_commercial_substitutes(item_code, warehouse=None):
    out = []
    if frappe.db.exists("DocType", "Pharma Product Substitute"):
        rows = frappe.get_all("Pharma Product Substitute", filters={"item_code": item_code, "active": 1}, fields=["substitute_item", "priority", "reason"], order_by="priority asc")
        for r in rows:
            stock = flt(frappe.db.get_value("Bin", {"item_code": r.substitute_item, "warehouse": warehouse}, "actual_qty") or 0) if warehouse else 0
            out.append({"item_code": r.substitute_item, "priority": r.priority, "reason": r.reason, "stock_qty": stock, "source": "Commercial Substitute"})
    try:
        for r in get_item_substitutes(item_code, warehouse) or []:
            if r.get("item_code") not in [x.get("item_code") for x in out]:
                out.append(r)
    except Exception:
        pass
    return out


@frappe.whitelist()
def get_near_expiry_intelligence(item_code=None, warehouse=None, days=90):
    conditions = ["b.expiry_date IS NOT NULL", "b.expiry_date <= %s", "IFNULL(sle.batch_no, '') != ''"]
    values = [add_days(nowdate(), int(days or 90))]
    if item_code:
        conditions.append("sle.item_code = %s")
        values.append(item_code)
    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)
    return frappe.db.sql(f"""
        SELECT sle.item_code, sle.batch_no, b.expiry_date, sle.warehouse, SUM(sle.actual_qty) AS qty
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.item_code, sle.batch_no, b.expiry_date, sle.warehouse
        HAVING SUM(sle.actual_qty) > 0 ORDER BY b.expiry_date ASC
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_dead_stock_analysis(days=90, warehouse=None):
    cutoff = add_days(nowdate(), -int(days or 90))
    conditions = ["i.disabled = 0", "i.is_stock_item = 1"]
    values = []
    if warehouse:
        conditions.append("b.warehouse = %s")
        values.append(warehouse)
    return frappe.db.sql(f"""
        SELECT i.item_code, i.item_name, b.warehouse, b.actual_qty, MAX(si.posting_date) AS last_sale_date
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON b.item_code = i.item_code
        LEFT JOIN `tabSales Invoice Item` sii ON sii.item_code = i.item_code
        LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
        WHERE {' AND '.join(conditions)}
        GROUP BY i.item_code, i.item_name, b.warehouse, b.actual_qty
        HAVING IFNULL(MAX(si.posting_date), '1900-01-01') < %s AND IFNULL(b.actual_qty, 0) > 0
        ORDER BY b.actual_qty DESC
    """, tuple(values + [cutoff]), as_dict=True)


@frappe.whitelist()
def calculate_distributor_inventory(distributor, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    primary = frappe.db.sql("""
        SELECT sii.item_code, sii.batch_no, SUM(ABS(sii.qty)) AS primary_qty
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.customer = %s AND si.posting_date BETWEEN %s AND %s AND si.docstatus = 1
        GROUP BY sii.item_code, sii.batch_no
    """, (distributor, from_date, to_date), as_dict=True)
    secondary = frappe.db.sql("""
        SELECT ssi.item_code, SUM(ssi.qty) AS secondary_qty
        FROM `tabPharma Secondary Sales Item` ssi
        INNER JOIN `tabPharma Secondary Sales` ss ON ss.name = ssi.parent
        WHERE ss.distributor = %s AND ss.period_from <= %s AND ss.period_to >= %s AND ss.docstatus = 1
        GROUP BY ssi.item_code
    """, (distributor, to_date, from_date), as_dict=True)
    sec_map = {r.item_code: flt(r.secondary_qty) for r in secondary}
    inv = frappe.new_doc("Pharma Distributor Inventory")
    inv.posting_date = to_date
    inv.distributor = distributor
    inv.territory = frappe.db.get_value("Customer", distributor, "territory")
    for p in primary:
        inv.append("items", {"item_code": p.item_code, "batch_no": p.batch_no, "opening_qty": 0, "primary_qty": p.primary_qty, "secondary_qty": sec_map.get(p.item_code, 0), "closing_qty": flt(p.primary_qty) - flt(sec_map.get(p.item_code, 0))})
    inv.insert(ignore_permissions=True)
    return inv.name


@frappe.whitelist()
def get_profitability_summary(from_date=None, to_date=None, group_by="item_code"):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    group_by = group_by if group_by in {"item_code", "customer", "territory"} else "item_code"
    return frappe.db.sql(f"""
        SELECT {group_by}, SUM(sales_amount) sales_amount, SUM(cost_amount) cost_amount,
               SUM(discount_amount) discount_amount, SUM(net_profit) net_profit,
               AVG(margin_percent) margin_percent
        FROM `tabPharma Product Profitability Snapshot`
        WHERE from_date >= %s AND to_date <= %s
        GROUP BY {group_by}
        ORDER BY net_profit DESC
    """, (from_date, to_date), as_dict=True)


def _safe_item_value(item_code, fieldname, default=None):
    """Safely read optional Item fields across ERPNext sites."""
    try:
        if frappe.get_meta("Item").has_field(fieldname):
            return frappe.db.get_value("Item", item_code, fieldname)
    except Exception:
        pass
    return default


def _sales_invoice_item_has_field(fieldname):
    try:
        return frappe.get_meta("Sales Invoice Item").has_field(fieldname)
    except Exception:
        return False


@frappe.whitelist()
def get_margin_intelligence(item_code, rate=0, qty=1, discount_percentage=0, batch_no=None):
    """Version-safe margin intelligence.

    Uses optional pharma fields when present and falls back to standard_rate / valuation_rate.
    """
    mrp = flt(_safe_item_value(item_code, "pharma_mrp", None) or frappe.db.get_value("Item", item_code, "standard_rate") or 0)
    ptr = flt(_safe_item_value(item_code, "pharma_ptr", None) or rate or frappe.db.get_value("Item", item_code, "standard_rate") or 0)
    cost = flt(frappe.db.get_value("Item", item_code, "valuation_rate") or 0)

    if batch_no:
        try:
            last_purchase = get_last_purchase_history(item_code, limit=20)
            for row in last_purchase:
                if row.get("batch_no") == batch_no and flt(row.get("rate")):
                    cost = flt(row.get("rate"))
                    break
        except Exception:
            pass

    qty = flt(qty or 1)
    gross_sales = flt(rate or ptr) * qty
    discount = gross_sales * flt(discount_percentage) / 100
    net_sales = gross_sales - discount
    cost_amount = cost * qty
    margin = net_sales - cost_amount
    margin_percent = (margin / net_sales * 100) if net_sales else 0

    return {
        "item_code": item_code,
        "mrp": mrp,
        "ptr": ptr,
        "cost": cost,
        "qty": qty,
        "gross_sales": gross_sales,
        "discount_amount": discount,
        "net_sales": net_sales,
        "cost_amount": cost_amount,
        "gross_margin": margin,
        "margin_percent": margin_percent,
        "negative_margin": bool(margin < 0)
    }


@frappe.whitelist()
def update_customer_product_stats(customer=None, item_code=None):
    """Populate Customer × Product statistics from submitted Sales Invoices."""
    conditions = ["si.docstatus = 1", "si.posting_date >= %s"]
    values = [add_days(nowdate(), -365)]

    if customer:
        conditions.append("si.customer = %s")
        values.append(customer)
    if item_code:
        conditions.append("sii.item_code = %s")
        values.append(item_code)

    rows = frappe.db.sql(f"""
        SELECT
            si.customer,
            sii.item_code,
            SUM(ABS(sii.qty)) AS twelve_month_qty,
            MAX(si.posting_date) AS last_sale_date
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(conditions)}
        GROUP BY si.customer, sii.item_code
    """, tuple(values), as_dict=True)

    created = []
    for row in rows:
        last = frappe.db.sql("""
            SELECT si.posting_date, sii.qty, sii.rate, sii.batch_no
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
            WHERE si.customer = %s
              AND sii.item_code = %s
              AND si.docstatus = 1
            ORDER BY si.posting_date DESC, si.modified DESC
            LIMIT 1
        """, (row.customer, row.item_code), as_dict=True)
        last = last[0] if last else {}

        stats_name = f"{row.customer}-{row.item_code}"
        if frappe.db.exists("Pharma Customer Product Stats", stats_name):
            doc = frappe.get_doc("Pharma Customer Product Stats", stats_name)
        else:
            doc = frappe.new_doc("Pharma Customer Product Stats")
            doc.customer = row.customer
            doc.item_code = row.item_code

        doc.last_sale_date = last.get("posting_date")
        doc.last_sale_rate = flt(last.get("rate"))
        doc.last_qty = flt(last.get("qty"))
        doc.last_batch_no = last.get("batch_no")
        doc.twelve_month_qty = flt(row.twelve_month_qty)
        doc.average_monthly_qty = flt(row.twelve_month_qty) / 12
        doc.last_updated = now_datetime()
        doc.save(ignore_permissions=True)
        created.append(doc.name)

    return created


@frappe.whitelist()
def generate_product_profitability_snapshot(from_date=None, to_date=None, item_code=None, customer=None, territory=None):
    """Generate version-safe profitability snapshots.

    ERPNext versions differ in Sales Invoice Item fields. This function uses
    incoming_rate/discount_amount only if present, otherwise falls back safely.
    """
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()

    has_incoming_rate = _sales_invoice_item_has_field("incoming_rate")
    has_discount_amount = _sales_invoice_item_has_field("discount_amount")

    cost_expr = "IFNULL(sii.incoming_rate, 0) * ABS(sii.qty)" if has_incoming_rate else "0"
    discount_expr = "IFNULL(sii.discount_amount, 0) * ABS(sii.qty)" if has_discount_amount else "(IFNULL(sii.rate,0) * ABS(sii.qty) * IFNULL(sii.discount_percentage,0) / 100)"

    conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %s AND %s"]
    values = [from_date, to_date]
    if item_code:
        conditions.append("sii.item_code = %s")
        values.append(item_code)
    if customer:
        conditions.append("si.customer = %s")
        values.append(customer)
    if territory:
        conditions.append("si.territory = %s")
        values.append(territory)

    rows = frappe.db.sql(f"""
        SELECT
            sii.item_code,
            si.customer,
            si.territory,
            SUM(sii.net_amount) AS sales_amount,
            SUM({cost_expr}) AS cost_amount,
            SUM({discount_expr}) AS discount_amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {' AND '.join(conditions)}
        GROUP BY sii.item_code, si.customer, si.territory
    """, tuple(values), as_dict=True)

    created = []
    for row in rows:
        cost_amount = flt(row.cost_amount)

        # Fallback cost if incoming_rate is absent/not populated.
        if not cost_amount:
            valuation_rate = flt(frappe.db.get_value("Item", row.item_code, "valuation_rate") or 0)
            qty_data = frappe.db.sql("""
                SELECT SUM(ABS(sii.qty)) AS qty
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE si.docstatus = 1
                  AND si.posting_date BETWEEN %s AND %s
                  AND sii.item_code = %s
                  AND si.customer = %s
            """, (from_date, to_date, row.item_code, row.customer), as_dict=True)
            cost_amount = valuation_rate * flt(qty_data[0].qty if qty_data else 0)

        doc = frappe.new_doc("Pharma Product Profitability Snapshot")
        doc.from_date = from_date
        doc.to_date = to_date
        doc.item_code = row.item_code
        doc.customer = row.customer
        doc.territory = row.territory
        doc.sales_amount = flt(row.sales_amount)
        doc.cost_amount = cost_amount
        doc.discount_amount = flt(row.discount_amount)
        doc.scheme_cost = 0
        doc.return_amount = 0
        doc.gross_profit = flt(row.sales_amount) - cost_amount
        doc.net_profit = doc.gross_profit - flt(row.discount_amount)
        doc.margin_percent = (doc.net_profit / flt(row.sales_amount) * 100) if flt(row.sales_amount) else 0
        doc.insert(ignore_permissions=True)
        created.append(doc.name)

    return created


@frappe.whitelist()
def get_operator_decision_panel(item_code, customer=None, warehouse=None, qty=1, rate=0, batch_no=None):
    """One-call operator intelligence panel payload."""
    batch_history = get_batch_history(item_code, warehouse, customer)
    last_sale = get_last_sale_history(item_code, customer, limit=3)
    last_purchase = get_last_purchase_history(item_code, limit=3)
    effective_rate = rate or (last_sale[0].rate if last_sale else 0)
    margin = get_margin_intelligence(item_code, effective_rate, qty, 0, batch_no)
    substitutes = get_commercial_substitutes(item_code, warehouse)
    near_expiry = get_near_expiry_intelligence(item_code, warehouse, 90)
    customer_pattern = get_customer_buying_pattern(customer, item_code) if customer else {}
    outstanding = get_customer_outstanding_snapshot(customer) if customer else {}

    return {
        "item_code": item_code,
        "batch_history": batch_history,
        "last_sale": last_sale,
        "last_purchase": last_purchase,
        "margin": margin,
        "substitutes": substitutes,
        "near_expiry": near_expiry,
        "customer_pattern": customer_pattern,
        "outstanding": outstanding,
        "decision_summary": {
            "available_batches": len(batch_history),
            "substitute_count": len(substitutes),
            "near_expiry_count": len(near_expiry),
            "negative_margin": margin.get("negative_margin"),
            "last_sale_rate": last_sale[0].rate if last_sale else None,
            "last_purchase_rate": last_purchase[0].rate if last_purchase else None,
            "mrp": margin.get("mrp"),
            "ptr": margin.get("ptr"),
            "margin_percent": margin.get("margin_percent")
        }
    }


@frappe.whitelist()
def scheduled_update_customer_product_stats():
    """Scheduler-safe customer product stats refresh."""
    return update_customer_product_stats()


def _scheme_item_qty_amount(items, item_code):
    qty = 0
    amount = 0
    for row in items or []:
        if row.get("item_code") == item_code:
            qty += flt(row.get("qty"))
            amount += flt(row.get("amount") or (flt(row.get("qty")) * flt(row.get("rate"))))
    return qty, amount


@frappe.whitelist()
def evaluate_advanced_scheme(scheme, items=None, customer=None, posting_date=None):
    """Evaluate one advanced scheme against invoice/cart items."""
    if isinstance(items, str):
        items = frappe.parse_json(items)
    items = items or []

    doc = frappe.get_doc("Pharma Advanced Scheme", scheme)
    total_qty = sum(flt(r.get("qty")) for r in items)
    total_amount = sum(flt(r.get("amount") or (flt(r.get("qty")) * flt(r.get("rate")))) for r in items)

    result = {
        "scheme": doc.name,
        "scheme_name": doc.scheme_name,
        "scheme_type": doc.scheme_type,
        "eligible": False,
        "benefit_amount": 0,
        "free_items": [],
        "discount_percentage": 0,
        "discount_amount": 0,
        "reason": "",
        "details": {}
    }

    if not doc.enabled:
        result["reason"] = "Scheme disabled"
        return result
    pdate = getdate(posting_date or nowdate())
    if doc.from_date and getdate(doc.from_date) > pdate:
        result["reason"] = "Scheme not started"
        return result
    if doc.to_date and getdate(doc.to_date) < pdate:
        result["reason"] = "Scheme expired"
        return result

    # budget guard
    if flt(doc.budget_amount) and flt(doc.consumed_amount) >= flt(doc.budget_amount):
        result["reason"] = "Scheme budget consumed"
        return result

    if doc.scheme_type in ["Buy X Get Y", "Cross Product"]:
        trigger_ok = True
        trigger_details = []
        for trig in doc.trigger_items:
            qty, amt = _scheme_item_qty_amount(items, trig.item_code)
            ok = qty >= flt(trig.qty or 0) and (not flt(trig.amount) or amt >= flt(trig.amount))
            trigger_ok = trigger_ok and ok
            trigger_details.append({"item_code": trig.item_code, "required_qty": flt(trig.qty), "actual_qty": qty, "ok": ok})
        if trigger_ok and doc.trigger_items:
            result["eligible"] = True
            result["free_items"] = [{"item_code": b.item_code, "qty": flt(b.qty), "discount_percentage": flt(b.discount_percentage), "discount_amount": flt(b.discount_amount)} for b in doc.benefit_items]
            result["benefit_amount"] = sum(flt(b.discount_amount) for b in doc.benefit_items)
            result["details"]["trigger_details"] = trigger_details
        else:
            result["reason"] = "Trigger item requirement not met"
            result["details"]["trigger_details"] = trigger_details

    elif doc.scheme_type in ["Value Based", "Invoice Discount"]:
        if total_amount >= flt(doc.min_amount or 0) and total_qty >= flt(doc.min_qty or 0):
            result["eligible"] = True
            result["discount_percentage"] = flt(doc.discount_percentage)
            result["discount_amount"] = flt(doc.discount_amount)
            percent_benefit = total_amount * flt(doc.discount_percentage) / 100
            result["benefit_amount"] = percent_benefit + flt(doc.discount_amount)
            result["details"] = {"total_qty": total_qty, "total_amount": total_amount}
        else:
            result["reason"] = "Minimum quantity/amount not met"

    elif doc.scheme_type == "Quarterly Target":
        # Progress is based on customer secondary sales / invoices depending available data.
        progress = get_quarterly_scheme_progress(doc.name, customer=customer)
        achieved_qty = flt(progress.get("achieved_qty"))
        achieved_amount = flt(progress.get("achieved_amount"))
        if (flt(doc.target_qty) and achieved_qty >= flt(doc.target_qty)) or (flt(doc.target_amount) and achieved_amount >= flt(doc.target_amount)):
            result["eligible"] = True
            result["benefit_amount"] = flt(doc.reward_amount)
            result["discount_amount"] = flt(doc.reward_amount)
            result["details"] = progress
        else:
            result["reason"] = "Quarterly target not achieved"
            result["details"] = progress

    return result


@frappe.whitelist()
def evaluate_advanced_schemes(items=None, customer=None, posting_date=None, territory=None):
    """Evaluate all active advanced schemes and return eligible/ineligible details."""
    if isinstance(items, str):
        items = frappe.parse_json(items)
    schemes = get_active_advanced_schemes(customer=customer, posting_date=posting_date, territory=territory, include_draft=0)
    results = []
    for s in schemes:
        results.append(evaluate_advanced_scheme(s.name, items=items, customer=customer, posting_date=posting_date))
    eligible = [r for r in results if r.get("eligible")]
    eligible = sorted(eligible, key=lambda x: flt(x.get("benefit_amount")), reverse=True)
    return {"eligible": eligible, "all": results}


@frappe.whitelist()
def apply_best_advanced_scheme(items=None, customer=None, posting_date=None, territory=None):
    """Return best scheme payload for billing UI. Does not mutate invoice."""
    evaluated = evaluate_advanced_schemes(items=items, customer=customer, posting_date=posting_date, territory=territory)
    best = evaluated.get("eligible")[0] if evaluated.get("eligible") else None
    return {"best": best, "evaluated": evaluated}


@frappe.whitelist()
def log_advanced_scheme_application(scheme, customer=None, sales_invoice=None, benefit_type=None, benefit_amount=0, free_item_code=None, free_qty=0, details=None):
    if isinstance(details, str):
        details = frappe.parse_json(details)
    doc = frappe.new_doc("Pharma Scheme Application Log")
    doc.posting_date = nowdate()
    doc.scheme = scheme
    doc.customer = customer
    doc.sales_invoice = sales_invoice
    doc.benefit_type = benefit_type or "Discount"
    doc.benefit_amount = flt(benefit_amount)
    doc.free_item_code = free_item_code
    doc.free_qty = flt(free_qty)
    doc.details = frappe.as_json(details or {}, indent=2)
    doc.insert(ignore_permissions=True)
    update_scheme_budget_consumption(scheme)
    return doc.name


@frappe.whitelist()
def update_scheme_budget_consumption(scheme):
    total = frappe.db.sql("""
        SELECT SUM(benefit_amount) AS amount
        FROM `tabPharma Scheme Application Log`
        WHERE scheme = %s
    """, (scheme,), as_dict=True)[0].amount or 0
    doc = frappe.get_doc("Pharma Advanced Scheme", scheme)
    doc.db_set("consumed_amount", flt(total))
    doc.db_set("remaining_budget", flt(doc.budget_amount) - flt(total) if flt(doc.budget_amount) else 0)
    return {"scheme": scheme, "consumed_amount": flt(total), "remaining_budget": flt(doc.budget_amount) - flt(total) if flt(doc.budget_amount) else 0}


@frappe.whitelist()
def get_scheme_profitability(scheme, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -90)
    to_date = to_date or nowdate()
    logs = frappe.db.sql("""
        SELECT SUM(benefit_amount) AS scheme_cost, COUNT(*) AS applications
        FROM `tabPharma Scheme Application Log`
        WHERE scheme = %s AND posting_date BETWEEN %s AND %s
    """, (scheme, from_date, to_date), as_dict=True)[0]
    # Revenue lift is approximated from invoices where scheme was logged.
    revenue = frappe.db.sql("""
        SELECT SUM(si.net_total) AS revenue
        FROM `tabSales Invoice` si
        INNER JOIN `tabPharma Scheme Application Log` l ON l.sales_invoice = si.name
        WHERE l.scheme = %s AND si.docstatus = 1 AND si.posting_date BETWEEN %s AND %s
    """, (scheme, from_date, to_date), as_dict=True)[0].revenue or 0
    return {
        "scheme": scheme,
        "from_date": from_date,
        "to_date": to_date,
        "applications": int(logs.applications or 0),
        "scheme_cost": flt(logs.scheme_cost),
        "revenue": flt(revenue),
        "scheme_cost_percent": (flt(logs.scheme_cost) / flt(revenue) * 100) if flt(revenue) else 0
    }


@frappe.whitelist()
def get_quarterly_scheme_progress(scheme, customer=None):
    doc = frappe.get_doc("Pharma Advanced Scheme", scheme)
    conditions = ["ss.docstatus = 1", "ss.period_from >= %s", "ss.period_to <= %s"]
    values = [doc.from_date, doc.to_date]
    if customer:
        conditions.append("ss.distributor = %s")
        values.append(customer)
    rows = frappe.db.sql(f"""
        SELECT SUM(ssi.qty) AS qty, SUM(ssi.amount) AS amount
        FROM `tabPharma Secondary Sales Item` ssi
        INNER JOIN `tabPharma Secondary Sales` ss ON ss.name = ssi.parent
        WHERE {' AND '.join(conditions)}
    """, tuple(values), as_dict=True)
    qty = flt(rows[0].qty if rows else 0)
    amount = flt(rows[0].amount if rows else 0)
    return {
        "scheme": scheme,
        "customer": customer,
        "target_qty": flt(doc.target_qty),
        "achieved_qty": qty,
        "target_amount": flt(doc.target_amount),
        "achieved_amount": amount,
        "qty_percent": (qty / flt(doc.target_qty) * 100) if flt(doc.target_qty) else 0,
        "amount_percent": (amount / flt(doc.target_amount) * 100) if flt(doc.target_amount) else 0
    }


@frappe.whitelist()
def create_demo_advanced_schemes():
    """Create demonstration advanced schemes. Safe to re-run."""
    created = []
    today = nowdate()
    end = add_days(today, 90)
    schemes = [
        ("PQS Buy 10 Get 2 CardioPlus", "Buy X Get Y", "PQS-CARD-10", "PQS-CARD-10", 10, 2),
        ("PQS Buy Cardio Get VitaD3", "Cross Product", "PQS-CARD-20", "PQS-VITD", 10, 1),
    ]
    for name, stype, trigger, benefit, qty, free_qty in schemes:
        if frappe.db.exists("Pharma Advanced Scheme", name):
            continue
        s = frappe.new_doc("Pharma Advanced Scheme")
        s.scheme_name = name
        s.scheme_type = stype
        s.enabled = 1
        s.from_date = today
        s.to_date = end
        s.priority = 10
        s.stacking_rule = "Best Benefit Only"
        s.budget_amount = 100000
        s.append("trigger_items", {"item_code": trigger, "qty": qty})
        s.append("benefit_items", {"item_code": benefit, "qty": free_qty})
        s.insert(ignore_permissions=True)
        created.append(s.name)

    if not frappe.db.exists("Pharma Advanced Scheme", "PQS Value Scheme 10000"):
        s = frappe.new_doc("Pharma Advanced Scheme")
        s.scheme_name = "PQS Value Scheme 10000"
        s.scheme_type = "Value Based"
        s.enabled = 1
        s.from_date = today
        s.to_date = end
        s.priority = 20
        s.min_amount = 10000
        s.discount_percentage = 2
        s.budget_amount = 100000
        s.insert(ignore_permissions=True)
        created.append(s.name)

    if not frappe.db.exists("Pharma Advanced Scheme", "PQS Quarterly Secondary Reward"):
        s = frappe.new_doc("Pharma Advanced Scheme")
        s.scheme_name = "PQS Quarterly Secondary Reward"
        s.scheme_type = "Quarterly Target"
        s.enabled = 1
        s.from_date = today
        s.to_date = end
        s.priority = 30
        s.target_qty = 1000
        s.reward_amount = 25000
        s.budget_amount = 250000
        s.insert(ignore_permissions=True)
        created.append(s.name)
    return created


@frappe.whitelist()
def get_active_advanced_schemes(customer=None, posting_date=None, territory=None, include_draft=0):
    """Production-hardened active scheme lookup.

    Default behavior uses submitted schemes only. Draft schemes can be included
    only by explicit include_draft=1 for controlled demo/testing.
    """
    posting_date = posting_date or nowdate()
    filters = {
        "enabled": 1,
        "from_date": ["<=", posting_date],
        "to_date": [">=", posting_date],
    }
    if int(include_draft or 0):
        filters["docstatus"] = ["<", 2]
    else:
        filters["docstatus"] = 1

    schemes = frappe.get_all(
        "Pharma Advanced Scheme",
        filters=filters,
        fields=[
            "name", "scheme_name", "scheme_type", "priority", "stacking_rule",
            "customer", "customer_group", "territory", "min_qty", "min_amount",
            "discount_percentage", "discount_amount", "target_qty",
            "target_amount", "reward_amount", "budget_amount", "consumed_amount"
        ],
        order_by="priority asc, modified desc"
    )

    if not customer:
        return schemes

    customer_group = frappe.db.get_value("Customer", customer, "customer_group")
    customer_territory = frappe.db.get_value("Customer", customer, "territory")
    out = []
    for s in schemes:
        if s.customer and s.customer != customer:
            continue
        if s.customer_group and s.customer_group != customer_group:
            continue
        if s.territory and s.territory != (territory or customer_territory):
            continue
        out.append(s)
    return out


@frappe.whitelist()
def validate_advanced_scheme_application(scheme, customer=None, posting_date=None, benefit_amount=0):
    posting_date = posting_date or nowdate()
    if not frappe.db.exists("Pharma Advanced Scheme", scheme):
        return {"valid": False, "errors": ["Scheme not found."]}

    doc = frappe.get_doc("Pharma Advanced Scheme", scheme)
    errors = []

    if doc.docstatus != 1:
        errors.append("Scheme must be submitted before application.")
    if not doc.enabled:
        errors.append("Scheme is disabled.")
    if doc.from_date and getdate(doc.from_date) > getdate(posting_date):
        errors.append("Scheme has not started.")
    if doc.to_date and getdate(doc.to_date) < getdate(posting_date):
        errors.append("Scheme has expired.")

    if customer:
        customer_group = frappe.db.get_value("Customer", customer, "customer_group")
        customer_territory = frappe.db.get_value("Customer", customer, "territory")
        if doc.customer and doc.customer != customer:
            errors.append("Scheme is not valid for this customer.")
        if doc.customer_group and doc.customer_group != customer_group:
            errors.append("Scheme is not valid for this customer group.")
        if doc.territory and doc.territory != customer_territory:
            errors.append("Scheme is not valid for this territory.")

    if flt(doc.budget_amount):
        remaining = flt(doc.budget_amount) - flt(doc.consumed_amount)
        if remaining <= 0:
            errors.append("Scheme budget is fully consumed.")
        elif flt(benefit_amount) and flt(benefit_amount) > remaining:
            errors.append("Scheme benefit exceeds remaining budget.")

    return {"valid": not bool(errors), "errors": errors}


@frappe.whitelist()
def build_advanced_scheme_invoice_payload(scheme_result, items=None):
    if isinstance(scheme_result, str):
        scheme_result = frappe.parse_json(scheme_result)
    if isinstance(items, str):
        items = frappe.parse_json(items)
    items = items or []
    scheme_result = scheme_result or {}

    payload = {
        "scheme": scheme_result.get("scheme"),
        "scheme_name": scheme_result.get("scheme_name"),
        "scheme_type": scheme_result.get("scheme_type"),
        "eligible": bool(scheme_result.get("eligible")),
        "invoice_discount_amount": flt(scheme_result.get("discount_amount")),
        "invoice_discount_percentage": flt(scheme_result.get("discount_percentage")),
        "free_item_rows": [],
        "line_adjustments": [],
        "benefit_amount": flt(scheme_result.get("benefit_amount")),
    }

    for row in scheme_result.get("free_items") or []:
        item_code = row.get("item_code")
        if not item_code:
            continue
        payload["free_item_rows"].append({
            "item_code": item_code,
            "qty": flt(row.get("qty")),
            "rate": 0,
            "is_free_item": 1,
            "discount_percentage": 100,
            "scheme": scheme_result.get("scheme")
        })
    return payload


@frappe.whitelist()
def hardened_apply_best_advanced_scheme(items=None, customer=None, posting_date=None, territory=None):
    if isinstance(items, str):
        items = frappe.parse_json(items)
    evaluated = evaluate_advanced_schemes(items=items, customer=customer, posting_date=posting_date, territory=territory)
    best = evaluated.get("eligible")[0] if evaluated.get("eligible") else None

    if not best:
        return {"best": None, "payload": None, "evaluated": evaluated, "valid": True, "errors": []}

    validation = validate_advanced_scheme_application(
        best.get("scheme"),
        customer=customer,
        posting_date=posting_date,
        benefit_amount=best.get("benefit_amount")
    )
    if not validation.get("valid"):
        return {"best": best, "payload": None, "evaluated": evaluated, "valid": False, "errors": validation.get("errors")}

    payload = build_advanced_scheme_invoice_payload(best, items=items)
    return {"best": best, "payload": payload, "evaluated": evaluated, "valid": True, "errors": []}


@frappe.whitelist()
def apply_advanced_scheme_to_operator_payload(data, customer=None, posting_date=None, territory=None):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    items = data.get("items") or []
    customer = customer or data.get("customer")
    result = hardened_apply_best_advanced_scheme(items=items, customer=customer, posting_date=posting_date or data.get("posting_date"), territory=territory)

    if not result.get("valid") or not result.get("payload"):
        data["advanced_scheme_result"] = result
        return data

    payload = result.get("payload") or {}
    existing_free = {(r.get("item_code"), r.get("scheme")) for r in data.get("items", []) if r.get("is_free_item")}
    for free_row in payload.get("free_item_rows") or []:
        key = (free_row.get("item_code"), free_row.get("scheme"))
        if key not in existing_free:
            data.setdefault("items", []).append(free_row)

    data["advanced_scheme"] = payload.get("scheme")
    data["advanced_scheme_name"] = payload.get("scheme_name")
    data["advanced_scheme_benefit_amount"] = payload.get("benefit_amount")
    data["advanced_scheme_invoice_discount_amount"] = payload.get("invoice_discount_amount")
    data["advanced_scheme_invoice_discount_percentage"] = payload.get("invoice_discount_percentage")
    data["advanced_scheme_result"] = result
    return data


def normalize_advanced_scheme_item_rows(data):
    """Normalize free rows so downstream invoice creation can consume them safely."""
    data = data or {}
    for row in data.get("items") or []:
        if row.get("is_free_item"):
            row["rate"] = 0
            row["discount_percentage"] = 100
            row["amount"] = 0
            row["net_amount"] = 0
            row["free_qty"] = flt(row.get("free_qty") or row.get("qty") or 0)
    return data


@frappe.whitelist()
def validate_advanced_scheme_payload_integrity(data):
    """Validate applied advanced scheme payload before invoice submission."""
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}

    errors = []
    scheme = data.get("advanced_scheme")
    if not scheme:
        return {"valid": True, "errors": []}

    validation = validate_advanced_scheme_application(
        scheme,
        customer=data.get("customer"),
        posting_date=data.get("posting_date") or nowdate(),
        benefit_amount=data.get("advanced_scheme_benefit_amount")
    )
    if not validation.get("valid"):
        errors.extend(validation.get("errors") or [])

    # Ensure free rows in payload are safe.
    for idx, row in enumerate(data.get("items") or [], start=1):
        if row.get("scheme") == scheme and row.get("is_free_item"):
            if flt(row.get("rate")) != 0:
                errors.append(f"Free scheme row {idx} must have zero rate.")
            if flt(row.get("qty")) <= 0:
                errors.append(f"Free scheme row {idx} must have positive qty.")

    return {"valid": not bool(errors), "errors": errors}


@frappe.whitelist()
def apply_advanced_scheme_for_invoice_submission(data):
    """Apply submitted advanced scheme to payload before invoice creation.

    This is the server-side production path. It ensures the scheme is applied even
    if the browser preview was not used.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}

    # Do not double-apply if already present.
    if data.get("advanced_scheme"):
        integrity = validate_advanced_scheme_payload_integrity(data)
        if not integrity.get("valid"):
            frappe.throw("<br>".join(integrity.get("errors") or ["Advanced scheme payload failed validation."]))
        return normalize_advanced_scheme_item_rows(data)

    updated = apply_advanced_scheme_to_operator_payload(data)
    if updated.get("advanced_scheme_result") and not updated.get("advanced_scheme_result", {}).get("valid", True):
        frappe.throw("<br>".join(updated.get("advanced_scheme_result", {}).get("errors") or ["Advanced scheme validation failed."]))

    integrity = validate_advanced_scheme_payload_integrity(updated)
    if not integrity.get("valid"):
        frappe.throw("<br>".join(integrity.get("errors") or ["Advanced scheme payload failed validation."]))

    return normalize_advanced_scheme_item_rows(updated)

@frappe.whitelist()
def create_quick_sale(data, action="invoice"):
    """Create Pharma Quick Sale and downstream invoice/order.

    v28.3 production patch:
    - Preserves advanced scheme metadata on Quick Sale item rows when fields exist.
    - Preserves free-item semantics where the target DocType supports it.
    - Applies invoice-level advanced scheme discount into bill_discount_amount.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)

    data = normalize_advanced_scheme_item_rows(data)

    doc = frappe.new_doc("Pharma Quick Sale")
    doc.customer = data.get("customer")
    doc.company = data.get("company")
    doc.warehouse = data.get("warehouse")
    tax_category = data.get("tax_category")
    doc.posting_date = data.get("posting_date") or nowdate()
    doc.price_list = data.get("price_list") or "Standard Selling"

    scheme_discount_amount = flt(data.get("advanced_scheme_invoice_discount_amount"))
    scheme_discount_percent = flt(data.get("advanced_scheme_invoice_discount_percentage"))
    doc.bill_discount_amount = flt(data.get("bill_discount_amount")) + scheme_discount_amount

    qsi_meta = frappe.get_meta("Pharma Quick Sale Item") if frappe.db.exists("DocType", "Pharma Quick Sale Item") else None

    for item in data.get("items", []):
        row_payload = {
            "row_id": item.get("row_id"),
            "item_code": item.get("item_code"),
            "item_name": item.get("item_name"),
            "packing": item.get("packing"),
            "uom": item.get("uom"),
            "conversion_factor": flt(item.get("conversion_factor")) or 1,
            "rate": flt(item.get("rate")),
            "discount_percentage": flt(item.get("discount_percentage"))
        }

        if qsi_meta:
            optional_map = {
                "qty": item.get("qty"),
                "free_qty": item.get("free_qty"),
                "is_free_item": item.get("is_free_item"),
                "scheme": item.get("scheme"),
                "advanced_scheme": item.get("scheme") or data.get("advanced_scheme"),
                "scheme_name": data.get("advanced_scheme_name"),
            }
            for field, value in optional_map.items():
                if qsi_meta.has_field(field) and value is not None:
                    row_payload[field] = value

        doc.append("items", row_payload)

    for alloc in data.get("batch_allocations", []):
        doc.append("batch_allocations", {
            "item_row_id": alloc.get("item_row_id"),
            "item_code": alloc.get("item_code"),
            "batch_no": alloc.get("batch_no"),
            "expiry_date": alloc.get("expiry_date"),
            "available_qty": flt(alloc.get("available_qty")),
            "qty": flt(alloc.get("qty")),
            "free_qty": flt(alloc.get("free_qty"))
        })

    doc.insert(ignore_permissions=True)
    doc.submit()

    result = {"quick_sale": doc.name, "sales_invoice": None, "sales_order": None}

    if action == "invoice":
        si = doc.create_sales_invoice()
        persist_advanced_scheme_metadata_on_invoice(si.name, data)
        result["sales_invoice"] = si.name
    elif action == "sales_order":
        so = doc.create_sales_order()
        result["sales_order"] = so.name
    else:
        frappe.throw("Invalid action. Use invoice or sales_order.")

    return result


@frappe.whitelist()
def persist_advanced_scheme_metadata_on_invoice(sales_invoice, data):
    """Persist advanced scheme effects on Sales Invoice where target fields exist.

    This makes the implementation complete enough for audit/UAT even if the
    Quick Sale child table lacks custom fields.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}

    if not sales_invoice or not data.get("advanced_scheme"):
        return None

    si = frappe.get_doc("Sales Invoice", sales_invoice)
    si_meta = frappe.get_meta("Sales Invoice")
    sii_meta = frappe.get_meta("Sales Invoice Item")

    updates = {}
    for field, value in {
        "advanced_scheme": data.get("advanced_scheme"),
        "advanced_scheme_name": data.get("advanced_scheme_name"),
        "advanced_scheme_benefit_amount": data.get("advanced_scheme_benefit_amount"),
    }.items():
        if si_meta.has_field(field):
            updates[field] = value

    if flt(data.get("advanced_scheme_invoice_discount_amount")):
        # Only set if ERPNext fields exist; most ERPNext Sales Invoices support these.
        if si_meta.has_field("additional_discount_account"):
            pass
        if si_meta.has_field("discount_amount"):
            updates["discount_amount"] = flt(si.get("discount_amount")) + flt(data.get("advanced_scheme_invoice_discount_amount"))
        if si_meta.has_field("apply_discount_on"):
            updates["apply_discount_on"] = si.get("apply_discount_on") or "Net Total"

    if updates:
        si.db_set(updates)

    # Mark free rows / scheme rows where ERPNext supports fields.
    free_rows = [r for r in data.get("items", []) if r.get("is_free_item") or r.get("scheme")]
    if free_rows:
        free_item_counts = {}
        for r in free_rows:
            free_item_counts[r.get("item_code")] = free_item_counts.get(r.get("item_code"), 0) + 1

        changed = False
        for row in si.items:
            # Best effort matching by item_code for free item rows.
            if row.item_code in free_item_counts and free_item_counts[row.item_code] > 0:
                if sii_meta.has_field("is_free_item"):
                    row.is_free_item = 1
                if sii_meta.has_field("rate"):
                    row.rate = 0 if any(r.get("is_free_item") and r.get("item_code") == row.item_code for r in free_rows) else row.rate
                if sii_meta.has_field("discount_percentage") and any(r.get("is_free_item") and r.get("item_code") == row.item_code for r in free_rows):
                    row.discount_percentage = 100
                if sii_meta.has_field("advanced_scheme"):
                    row.advanced_scheme = data.get("advanced_scheme")
                if sii_meta.has_field("scheme"):
                    row.scheme = data.get("advanced_scheme")
                free_item_counts[row.item_code] -= 1
                changed = True

        if changed and si.docstatus == 0:
            si.save(ignore_permissions=True)

    return sales_invoice


@frappe.whitelist()
def log_advanced_scheme_from_invoice_result(data, result):
    """Log applied advanced scheme after invoice creation/submission."""
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    result = result or {}

    scheme = data.get("advanced_scheme")
    if not scheme:
        return None

    sales_invoice = result.get("sales_invoice") or result.get("invoice") or result.get("name")
    if not sales_invoice and result.get("quick_sale"):
        # Recover invoice from quick sale link if result payload is incomplete.
        sales_invoice = frappe.db.get_value("Sales Invoice", {"pharma_quick_sale": result.get("quick_sale")}, "name") if frappe.get_meta("Sales Invoice").has_field("pharma_quick_sale") else None

    logs = []

    if flt(data.get("advanced_scheme_benefit_amount")):
        logs.append(log_advanced_scheme_application(
            scheme=scheme,
            customer=data.get("customer"),
            sales_invoice=sales_invoice,
            benefit_type="Discount",
            benefit_amount=flt(data.get("advanced_scheme_benefit_amount")),
            details=data.get("advanced_scheme_result")
        ))

    for row in data.get("items") or []:
        if row.get("scheme") == scheme and row.get("is_free_item"):
            logs.append(log_advanced_scheme_application(
                scheme=scheme,
                customer=data.get("customer"),
                sales_invoice=sales_invoice,
                benefit_type="Free Item",
                benefit_amount=0,
                free_item_code=row.get("item_code"),
                free_qty=flt(row.get("qty") or row.get("free_qty")),
                details={"row": row, "advanced_scheme_result": data.get("advanced_scheme_result")}
            ))

    return logs


@frappe.whitelist()
def get_sample_utilization(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    conditions = ["posting_date BETWEEN %s AND %s"]
    values = [from_date, to_date]
    if sales_person:
        conditions.append("sales_person=%s")
        values.append(sales_person)
    rows = frappe.db.sql(f"""
        SELECT sales_person,
            SUM(CASE WHEN transaction_type='Issued' THEN qty ELSE 0 END) issued_qty,
            SUM(CASE WHEN transaction_type='Distributed' THEN ABS(qty) ELSE 0 END) distributed_qty,
            SUM(CASE WHEN transaction_type='Returned' THEN qty ELSE 0 END) returned_qty
        FROM `tabPharma Sample Ledger`
        WHERE {' AND '.join(conditions)}
        GROUP BY sales_person
    """, tuple(values), as_dict=True)
    for r in rows:
        r["efficiency_percent"] = (flt(r.distributed_qty) / flt(r.issued_qty) * 100) if flt(r.issued_qty) else 0
    return rows


@frappe.whitelist()
def get_doctor_sample_history(doctor=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -365)
    to_date = to_date or nowdate()
    conditions = ["st.transaction_type='Distribution to Doctor'", "st.posting_date BETWEEN %s AND %s"]
    values = [from_date, to_date]
    if doctor:
        conditions.append("st.doctor=%s")
        values.append(doctor)
    return frappe.db.sql(f"""
        SELECT st.posting_date, st.sales_person, st.doctor, sti.item_code, sti.batch_no, sti.qty
        FROM `tabPharma Sample Transaction Item` sti
        INNER JOIN `tabPharma Sample Transaction` st ON st.name=sti.parent
        WHERE {' AND '.join(conditions)}
        ORDER BY st.posting_date DESC
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def create_sample_reconciliation(sales_person, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    inv = get_sample_balance(sales_person=sales_person)
    rec = frappe.new_doc("Pharma Sample Reconciliation V29")
    rec.from_date = from_date
    rec.to_date = to_date
    rec.sales_person = sales_person
    total_var = 0
    for r in inv:
        expected = flt(r.get("balance_qty"))
        rec.append("items", {
            "item_code": r.get("item_code"),
            "batch_no": r.get("batch_no"),
            "expected_balance": expected,
            "physical_balance": expected,
            "variance_qty": 0
        })
    rec.total_variance = total_var
    rec.insert(ignore_permissions=True)
    return rec.name


@frappe.whitelist()
def get_beat_compliance_v29(sales_person=None, from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    filters = {"visit_date": ["between", [from_date, to_date]]}
    if sales_person:
        filters["sales_person"] = sales_person
    planned = frappe.db.count("Pharma Visit Log", filters)
    completed_filters = dict(filters)
    completed_filters["visit_status"] = "Completed"
    completed = frappe.db.count("Pharma Visit Log", completed_filters)
    missed = planned - completed
    return {"sales_person": sales_person, "from_date": from_date, "to_date": to_date, "planned": planned, "completed": completed, "missed": missed, "compliance_percent": (completed/planned*100) if planned else 0}


@frappe.whitelist()
def get_mr_dashboard_v29(sales_person, date=None):
    date = date or nowdate()
    scheduled = frappe.db.count("Pharma Visit Log", {"sales_person": sales_person, "visit_date": date})
    completed = frappe.db.count("Pharma Visit Log", {"sales_person": sales_person, "visit_date": date, "visit_status": "Completed"})
    samples = frappe.db.sql("""
        SELECT SUM(samples_given) qty, SUM(order_value) orders
        FROM `tabPharma Visit Log`
        WHERE sales_person=%s AND visit_date=%s
    """, (sales_person, date), as_dict=True)[0]
    return {"sales_person": sales_person, "date": date, "scheduled": scheduled, "completed": completed, "pending": scheduled-completed, "samples_given": flt(samples.qty), "orders_booked": flt(samples.orders)}


@frappe.whitelist()
def get_manager_dashboard_v29(from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    rows = frappe.db.sql("""
        SELECT sales_person, COUNT(*) planned,
               SUM(CASE WHEN visit_status='Completed' THEN 1 ELSE 0 END) completed,
               SUM(samples_given) samples_given,
               SUM(order_value) order_value
        FROM `tabPharma Visit Log`
        WHERE visit_date BETWEEN %s AND %s
        GROUP BY sales_person
        ORDER BY completed DESC
    """, (from_date, to_date), as_dict=True)
    for r in rows:
        r["compliance_percent"] = (flt(r.completed)/flt(r.planned)*100) if flt(r.planned) else 0
    return rows


@frappe.whitelist()
def generate_incentive_payouts(from_date=None, to_date=None):
    from_date = from_date or add_days(nowdate(), -30)
    to_date = to_date or nowdate()
    rules = frappe.get_all("Pharma Incentive Rule", filters={"enabled": 1, "docstatus": 1, "from_date": ["<=", to_date], "to_date": [">=", from_date]}, fields=["name", "sales_person", "distributor"])
    created = []
    for r in rules:
        calc = calculate_incentive_rule(r.name)
        existing = frappe.db.get_value("Pharma Incentive Payout", {"rule": r.name, "from_date": from_date, "to_date": to_date}, "name")
        if existing:
            continue
        p = frappe.new_doc("Pharma Incentive Payout")
        p.from_date = from_date
        p.to_date = to_date
        p.sales_person = r.sales_person
        p.distributor = r.distributor
        p.rule = r.name
        p.achievement_amount = calc.get("achievement_amount")
        p.achievement_qty = calc.get("achievement_qty")
        p.achievement_percent = calc.get("achievement_percent")
        p.incentive_amount = calc.get("incentive_amount")
        p.status = "Draft"
        p.details = frappe.as_json(calc, indent=2)
        p.insert(ignore_permissions=True)
        created.append(p.name)
    return created


@frappe.whitelist()
def approve_incentive_payout(payout, status="Approved"):
    doc = frappe.get_doc("Pharma Incentive Payout", payout)
    if status not in ["Approved", "Rejected", "Paid"]:
        frappe.throw("Invalid status")
    doc.db_set("status", status)
    return doc.name


@frappe.whitelist()
def create_sample_stock_entry_from_transaction(sample_transaction):
    doc = frappe.get_doc("Pharma Sample Transaction", sample_transaction)
    if doc.stock_entry:
        return doc.stock_entry
    if doc.transaction_type not in ["Issue to MR", "Return from MR", "Expiry Write-off", "Adjustment"]:
        return None
    if doc.transaction_type in ["Issue to MR", "Expiry Write-off"] and not doc.source_warehouse:
        frappe.throw("Source Warehouse is required.")
    if doc.transaction_type == "Return from MR" and not doc.target_warehouse:
        frappe.throw("Target Warehouse is required.")

    se = frappe.new_doc("Stock Entry")
    se.posting_date = doc.posting_date or nowdate()
    se.stock_entry_type = "Material Issue" if doc.transaction_type in ["Issue to MR", "Expiry Write-off"] else "Material Receipt"

    for row in doc.items:
        if flt(row.qty) <= 0:
            frappe.throw(f"Qty must be positive for {row.item_code}.")
        item_row = {
            "item_code": row.item_code,
            "qty": flt(row.qty),
            "batch_no": row.batch_no,
            "basic_rate": flt(row.rate) or flt(frappe.db.get_value("Item", row.item_code, "valuation_rate") or 0),
        }
        if se.stock_entry_type == "Material Issue":
            item_row["s_warehouse"] = doc.source_warehouse
        else:
            item_row["t_warehouse"] = doc.target_warehouse
        se.append("items", item_row)

    se.insert(ignore_permissions=True)
    se.submit()
    doc.db_set("stock_entry", se.name)
    return se.name


@frappe.whitelist()
def post_sample_transaction(sample_transaction):
    doc = frappe.get_doc("Pharma Sample Transaction", sample_transaction)
    if doc.docstatus != 1:
        frappe.throw("Sample Transaction must be submitted before posting.")

    existing = frappe.db.exists("Pharma Sample Ledger", {
        "reference_doctype": "Pharma Sample Transaction",
        "reference_name": doc.name
    })
    if existing:
        return {"status": "already_posted", "sample_transaction": doc.name, "stock_entry": doc.stock_entry}

    stock_entry = create_sample_stock_entry_from_transaction(doc.name)
    created = []
    for row in doc.items:
        if flt(row.qty) <= 0:
            frappe.throw(f"Qty must be positive for {row.item_code}")
        sign = -1 if doc.transaction_type in ["Distribution to Doctor", "Return from MR", "Expiry Write-off"] else 1
        ledger = frappe.new_doc("Pharma Sample Ledger")
        ledger.posting_date = doc.posting_date
        ledger.sales_person = doc.sales_person
        ledger.item_code = row.item_code
        ledger.batch_no = row.batch_no
        ledger.expiry_date = row.expiry_date or (frappe.db.get_value("Batch", row.batch_no, "expiry_date") if row.batch_no else None)
        if doc.transaction_type == "Issue to MR":
            ledger.transaction_type = "Issued"
        elif doc.transaction_type == "Distribution to Doctor":
            ledger.transaction_type = "Distributed"
        elif doc.transaction_type in ["Return from MR", "Return from Doctor"]:
            ledger.transaction_type = "Returned"
        elif doc.transaction_type == "Expiry Write-off":
            ledger.transaction_type = "Expired"
        elif doc.transaction_type == "Opening":
            ledger.transaction_type = "Opening"
        else:
            ledger.transaction_type = "Adjustment"
        ledger.qty = sign * flt(row.qty)
        ledger.reference_doctype = "Pharma Sample Transaction"
        ledger.reference_name = doc.name
        ledger.insert(ignore_permissions=True)
        created.append(ledger.name)
    rebuild_sample_inventory(doc.sales_person)
    return {"status": "posted", "sample_transaction": doc.name, "stock_entry": stock_entry, "ledger_entries": created}


@frappe.whitelist()
def rebuild_sample_inventory(sales_person=None):
    conditions = ["IFNULL(batch_no, '') != ''"]
    values = []
    if sales_person:
        conditions.append("sales_person=%s")
        values.append(sales_person)
    rows = frappe.db.sql(f"""
        SELECT sales_person, item_code, batch_no, expiry_date,
            SUM(CASE WHEN transaction_type='Opening' THEN qty ELSE 0 END) opening_qty,
            SUM(CASE WHEN transaction_type='Issued' THEN qty ELSE 0 END) received_qty,
            SUM(CASE WHEN transaction_type='Distributed' THEN ABS(qty) ELSE 0 END) distributed_qty,
            SUM(CASE WHEN transaction_type='Returned' THEN qty ELSE 0 END) returned_qty,
            SUM(CASE WHEN transaction_type='Expired' THEN ABS(qty) ELSE 0 END) expired_qty,
            SUM(CASE WHEN transaction_type='Adjustment' THEN qty ELSE 0 END) adjustment_qty,
            SUM(qty) balance_qty
        FROM `tabPharma Sample Ledger`
        WHERE {' AND '.join(conditions)}
        GROUP BY sales_person, item_code, batch_no, expiry_date
    """, tuple(values), as_dict=True)
    updated = []
    for r in rows:
        if not r.batch_no:
            continue
        name = f"{r.sales_person}-{r.item_code}-{r.batch_no}"
        doc = frappe.get_doc("Pharma Sample Inventory", name) if frappe.db.exists("Pharma Sample Inventory", name) else frappe.new_doc("Pharma Sample Inventory")
        doc.sales_person = r.sales_person
        doc.item_code = r.item_code
        doc.batch_no = r.batch_no
        doc.expiry_date = r.expiry_date
        doc.opening_qty = flt(r.opening_qty)
        doc.received_qty = flt(r.received_qty)
        doc.distributed_qty = flt(r.distributed_qty)
        doc.returned_qty = flt(r.returned_qty)
        doc.expired_qty = flt(r.expired_qty)
        doc.adjustment_qty = flt(r.adjustment_qty)
        doc.balance_qty = flt(r.balance_qty)
        doc.last_updated = now_datetime()
        doc.save(ignore_permissions=True)
        updated.append(doc.name)
    return updated


@frappe.whitelist()
def generate_visit_logs_from_beat_plan(beat_plan):
    plan = frappe.get_doc("Pharma Beat Plan", beat_plan)
    created = []
    for line in plan.lines:
        filters = {"beat_plan": plan.name, "visit_date": line.visit_date, "sales_person": plan.sales_person}
        if line.doctor:
            filters["doctor"] = line.doctor
        if line.chemist or line.distributor:
            filters["customer"] = line.chemist or line.distributor
        if frappe.db.get_value("Pharma Visit Log", filters, "name"):
            continue
        v = frappe.new_doc("Pharma Visit Log")
        v.visit_date = line.visit_date
        v.sales_person = plan.sales_person
        v.beat_plan = plan.name
        v.doctor = line.doctor
        v.customer = line.chemist or line.distributor
        v.visit_status = "Scheduled"
        v.remarks = line.remarks
        v.insert(ignore_permissions=True)
        created.append(v.name)
    return created


@frappe.whitelist()
def check_in_visit(visit_log, latitude=None, longitude=None):
    doc = frappe.get_doc("Pharma Visit Log", visit_log)
    doc.db_set("check_in_time", now_datetime())
    if latitude is not None:
        doc.db_set("latitude", flt(latitude))
    if longitude is not None:
        doc.db_set("longitude", flt(longitude))
    doc.db_set("visit_status", "Scheduled")
    return doc.name


@frappe.whitelist()
def check_out_visit(visit_log, remarks=None, samples_given=0, order_value=0):
    doc = frappe.get_doc("Pharma Visit Log", visit_log)
    if not doc.check_in_time:
        doc.db_set("check_in_time", now_datetime())
    doc.db_set("check_out_time", now_datetime())
    doc.db_set("remarks", remarks or doc.remarks)
    doc.db_set("samples_given", flt(samples_given))
    doc.db_set("order_value", flt(order_value))
    doc.db_set("visit_status", "Completed")
    return doc.name


@frappe.whitelist()
def calculate_incentive_rule(rule):
    doc = frappe.get_doc("Pharma Incentive Rule", rule)
    amount = 0
    qty = 0

    if doc.rule_type == "MR Sales":
        conditions = ["si.docstatus=1", "si.posting_date BETWEEN %s AND %s"]
        values = [doc.from_date, doc.to_date]
        if doc.sales_person:
            conditions.append("st.sales_person=%s")
            values.append(doc.sales_person)
        rows = frappe.db.sql(f"""
            SELECT SUM(si.net_total) amount
            FROM `tabSales Invoice` si
            LEFT JOIN `tabSales Team` st ON st.parent=si.name
            WHERE {' AND '.join(conditions)}
        """, tuple(values), as_dict=True)
        amount = flt(rows[0].amount if rows else 0)

    elif doc.rule_type == "MR Collection":
        conditions = ["pe.docstatus=1", "pe.party_type='Customer'", "pe.posting_date BETWEEN %s AND %s"]
        values = [doc.from_date, doc.to_date]
        if doc.sales_person:
            conditions.append("""pe.party IN (
                SELECT DISTINCT si.customer
                FROM `tabSales Invoice` si
                INNER JOIN `tabSales Team` st ON st.parent=si.name
                WHERE st.sales_person=%s
            )""")
            values.append(doc.sales_person)
        rows = frappe.db.sql(f"SELECT SUM(pe.paid_amount) amount FROM `tabPayment Entry` pe WHERE {' AND '.join(conditions)}", tuple(values), as_dict=True)
        amount = flt(rows[0].amount if rows else 0)

    elif doc.rule_type == "MR Doctor Coverage":
        dash = get_doctor_coverage_dashboard(doc.sales_person, doc.from_date, doc.to_date)
        qty = flt(dash.get("visited_doctors"))
        amount = qty

    elif doc.rule_type == "MR Secondary Sales":
        rows = frappe.db.sql("""
            SELECT SUM(total_amount) amount
            FROM `tabPharma Secondary Sales`
            WHERE docstatus=1 AND period_from >= %s AND period_to <= %s
              AND (%s IS NULL OR sales_person=%s)
        """, (doc.from_date, doc.to_date, doc.sales_person, doc.sales_person), as_dict=True)
        amount = flt(rows[0].amount if rows else 0)

    elif doc.rule_type == "Distributor Growth":
        rows = frappe.db.sql("""
            SELECT SUM(total_amount) amount
            FROM `tabPharma Secondary Sales`
            WHERE docstatus=1 AND period_from >= %s AND period_to <= %s
              AND (%s IS NULL OR distributor=%s)
        """, (doc.from_date, doc.to_date, doc.distributor, doc.distributor), as_dict=True)
        amount = flt(rows[0].amount if rows else 0)

    elif doc.rule_type == "Scheme Performance":
        scheme = doc.get("advanced_scheme") if frappe.get_meta("Pharma Incentive Rule").has_field("advanced_scheme") else None
        if not scheme and frappe.db.exists("Pharma Advanced Scheme", doc.rule_name):
            scheme = doc.rule_name
        prof = get_scheme_profitability(scheme, doc.from_date, doc.to_date) if scheme else {}
        amount = flt(prof.get("revenue"))

    target = flt(doc.target_amount or doc.target_qty)
    achieved = amount or qty
    pct = (achieved / target * 100) if target else 0
    incentive = 0
    for slab in doc.slabs:
        if pct >= flt(slab.from_percent) and pct <= flt(slab.to_percent):
            incentive = flt(slab.fixed_amount) + (amount * flt(slab.incentive_percentage) / 100)
            break
    return {"rule": rule, "achievement_amount": amount, "achievement_qty": qty, "achievement_percent": pct, "incentive_amount": incentive}


@frappe.whitelist()
def get_operator_hotkey_map(profile=None):
    if profile and frappe.db.exists("Pharma Operator Hotkey Profile", profile):
        doc = frappe.get_doc("Pharma Operator Hotkey Profile", profile)
        return {k.replace("_action","").upper(): doc.get(k) for k in ["f2_action","f3_action","f4_action","f5_action","f6_action","f7_action","f8_action","f9_action","f10_action"]}
    return {"F2":"Search Item","F3":"Batch","F4":"Apply Scheme","F5":"Customer","F6":"Outstanding","F7":"Substitute","F8":"Hold","F9":"Invoice","F10":"Intelligence"}


@frappe.whitelist()
def get_fast_billing_context(customer=None, item_code=None, warehouse=None):
    return {
        "customer": get_customer_outstanding_snapshot(customer) if customer else {},
        "item": get_operator_decision_panel(item_code, customer=customer, warehouse=warehouse) if item_code else {},
        "hotkeys": get_operator_hotkey_map()
    }


@frappe.whitelist()
def get_billing_defaults_v30(company=None):
    company = company or frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value("Company", {}, "name")
    warehouse = None
    if company:
        warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")
    return {
        "company": company,
        "warehouse": warehouse,
        "price_list": frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling",
        "tax_category": None
    }


@frappe.whitelist()
def validate_billing_party_v30(customer=None, warehouse=None, company=None):
    errors = []
    if customer and not frappe.db.exists("Customer", customer):
        found = frappe.db.get_value("Customer", {"customer_name": customer}, "name")
        if found:
            customer = found
        else:
            errors.append(f"Customer not found: {customer}")
    if warehouse and not frappe.db.exists("Warehouse", warehouse):
        errors.append(f"Warehouse not found: {warehouse}")
    if company and not frappe.db.exists("Company", company):
        errors.append(f"Company not found: {company}")
    return {"valid": not bool(errors), "errors": errors, "customer": customer, "warehouse": warehouse, "company": company}


@frappe.whitelist()
def fast_item_search_v30(query=None, warehouse=None, limit=50):
    query = (query or "").strip()
    if not query:
        return []
    like = f"%{query}%"
    item_meta = frappe.get_meta("Item")
    fields = ["i.item_code", "i.item_name", "i.stock_uom", "i.standard_rate"]
    optional_fields = {
        "pharma_composition": "composition",
        "pharma_brand": "brand",
        "pharma_manufacturer": "manufacturer",
        "pharma_mrp": "mrp",
        "pharma_ptr": "ptr",
        "barcode": "barcode"
    }
    for field, alias in optional_fields.items():
        if item_meta.has_field(field):
            fields.append(f"i.{field} AS {alias}")
    barcode_join = ""
    barcode_where = ""
    barcode_exists = frappe.db.exists("DocType", "Item Barcode")
    if barcode_exists:
        barcode_join = "LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name"
        barcode_where = " OR ib.barcode LIKE %s"
    values = [like, like]
    if item_meta.has_field("barcode"):
        values.append(like)
    if item_meta.has_field("pharma_composition"):
        values.append(like)
    if item_meta.has_field("pharma_brand"):
        values.append(like)
    if barcode_exists:
        values.append(like)
    values += [f"{query}%", int(limit or 50)]
    rows = frappe.db.sql(f"""
        SELECT DISTINCT {', '.join(fields)}
        FROM `tabItem` i
        {barcode_join}
        WHERE i.disabled=0
          AND (
            i.item_code LIKE %s
            OR i.item_name LIKE %s
            {"OR i.barcode LIKE %s" if item_meta.has_field("barcode") else ""}
            {"OR i.pharma_composition LIKE %s" if item_meta.has_field("pharma_composition") else ""}
            {"OR i.pharma_brand LIKE %s" if item_meta.has_field("pharma_brand") else ""}
            {barcode_where}
          )
        ORDER BY CASE WHEN i.item_code LIKE %s THEN 0 ELSE 1 END, i.item_code
        LIMIT %s
    """, tuple(values), as_dict=True)
    for r in rows:
        r["mrp"] = r.get("mrp") or r.get("standard_rate")
        r["ptr"] = r.get("ptr") or r.get("standard_rate")
        r["stock_qty"] = flt(frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": warehouse}, "actual_qty") or 0) if warehouse else 0
    return rows


@frappe.whitelist()
def get_item_cache_v30(warehouse=None, limit=25000, offset=0, modified_after=None):
    item_meta = frappe.get_meta("Item")
    fields = ["i.item_code", "i.item_name", "i.stock_uom", "i.standard_rate", "i.modified"]
    optional_fields = {
        "pharma_composition": "composition",
        "pharma_brand": "brand",
        "pharma_manufacturer": "manufacturer",
        "pharma_mrp": "mrp",
        "pharma_ptr": "ptr",
        "barcode": "barcode"
    }
    for field, alias in optional_fields.items():
        if item_meta.has_field(field):
            fields.append(f"i.{field} AS {alias}")
    conditions = ["i.disabled=0"]
    values = []
    if modified_after:
        conditions.append("i.modified >= %s")
        values.append(modified_after)
    values.extend([int(limit or 25000), int(offset or 0)])
    rows = frappe.db.sql(f"""
        SELECT {', '.join(fields)}
        FROM `tabItem` i
        WHERE {' AND '.join(conditions)}
        ORDER BY i.modified DESC, i.item_code
        LIMIT %s OFFSET %s
    """, tuple(values), as_dict=True)
    if frappe.db.exists("DocType", "Item Barcode") and rows:
        item_codes = [r.item_code for r in rows]
        barcodes = frappe.db.sql("""
            SELECT parent AS item_code, MIN(barcode) AS barcode
            FROM `tabItem Barcode`
            WHERE parent IN %(items)s
            GROUP BY parent
        """, {"items": item_codes}, as_dict=True)
        barcode_map = {b.item_code: b.barcode for b in barcodes}
        for r in rows:
            r["barcode"] = r.get("barcode") or barcode_map.get(r.item_code)
    for r in rows:
        r["mrp"] = r.get("mrp") or r.get("standard_rate")
        r["ptr"] = r.get("ptr") or r.get("standard_rate")
        r["stock_qty"] = flt(frappe.db.get_value("Bin", {"item_code": r.item_code, "warehouse": warehouse}, "actual_qty") or 0) if warehouse else 0
    return rows


@frappe.whitelist()
def get_customer_cache_v30(limit=25000, offset=0, modified_after=None):
    conditions = []
    values = []
    meta = frappe.get_meta("Customer")
    if meta.has_field("disabled"):
        conditions.append("IFNULL(disabled,0)=0")
    if modified_after:
        conditions.append("modified >= %s")
        values.append(modified_after)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    values.extend([int(limit or 25000), int(offset or 0)])
    return frappe.db.sql(f"""
        SELECT name, customer_name, customer_group, territory, modified
        FROM `tabCustomer`
        {where}
        ORDER BY modified DESC, name
        LIMIT %s OFFSET %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_batch_cache_v30(warehouse=None, limit=100000, offset=0, modified_after=None):
    conditions = ["IFNULL(sle.batch_no,'') != ''"]
    values = []
    if warehouse:
        conditions.append("sle.warehouse=%s")
        values.append(warehouse)
    if modified_after:
        conditions.append("sle.modified >= %s")
        values.append(modified_after)
    values.extend([int(limit or 100000), int(offset or 0)])
    return frappe.db.sql(f"""
        SELECT CONCAT(sle.item_code, '::', sle.batch_no, '::', sle.warehouse) AS `key`,
               sle.item_code, sle.batch_no, sle.warehouse, b.expiry_date,
               SUM(sle.actual_qty) AS available_qty,
               MAX(sle.modified) AS modified
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name=sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.item_code, sle.batch_no, sle.warehouse, b.expiry_date
        HAVING SUM(sle.actual_qty) > 0
        ORDER BY b.expiry_date ASC
        LIMIT %s OFFSET %s
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_billing_cache_v30(warehouse=None, company=None, item_limit=25000, batch_limit=100000, customer_limit=25000):
    return {
        "defaults": get_billing_defaults_v30(company=company),
        "items": get_item_cache_v30(warehouse=warehouse, limit=item_limit),
        "customers": get_customer_cache_v30(limit=customer_limit),
        "batches": get_batch_cache_v30(warehouse=warehouse, limit=batch_limit)
    }


@frappe.whitelist()
def get_reserved_qty_v31(item_code, batch_no=None, warehouse=None, customer=None):
    conditions = ["docstatus=1", "status IN ('Active','Partially Consumed')", "item_code=%s"]
    values = [item_code]
    if batch_no:
        conditions.append("batch_no=%s")
        values.append(batch_no)
    if warehouse:
        conditions.append("warehouse=%s")
        values.append(warehouse)
    if customer:
        conditions.append("customer=%s")
        values.append(customer)
    row = frappe.db.sql(f"""
        SELECT SUM(reserved_qty - IFNULL(consumed_qty,0) - IFNULL(released_qty,0)) qty
        FROM `tabPharma Batch Reservation`
        WHERE {' AND '.join(conditions)}
          AND (reserved_until IS NULL OR reserved_until >= %s)
    """, tuple(values + [nowdate()]), as_dict=True)
    return flt(row[0].qty if row else 0)


@frappe.whitelist()
def get_available_batch_stock_v31(item_code, warehouse=None, customer=None, respect_reservations=1):
    conditions = ["sle.item_code=%s", "IFNULL(sle.batch_no,'') != ''"]
    values = [item_code]
    if warehouse:
        conditions.append("sle.warehouse=%s")
        values.append(warehouse)

    rows = frappe.db.sql(f"""
        SELECT sle.item_code, sle.batch_no, sle.warehouse, b.expiry_date,
               SUM(sle.actual_qty) AS actual_qty
        FROM `tabStock Ledger Entry` sle
        LEFT JOIN `tabBatch` b ON b.name=sle.batch_no
        WHERE {' AND '.join(conditions)}
        GROUP BY sle.item_code, sle.batch_no, sle.warehouse, b.expiry_date
        HAVING SUM(sle.actual_qty) > 0
        ORDER BY b.expiry_date ASC, sle.batch_no ASC
    """, tuple(values), as_dict=True)

    for r in rows:
        reserved_for_others = 0
        if int(respect_reservations or 0):
            total_reserved = get_reserved_qty_v31(item_code, r.batch_no, r.warehouse)
            own_reserved = get_reserved_qty_v31(item_code, r.batch_no, r.warehouse, customer) if customer else 0
            reserved_for_others = max(flt(total_reserved) - flt(own_reserved), 0)
        r["reserved_qty"] = reserved_for_others
        r["free_qty"] = max(flt(r.actual_qty) - flt(reserved_for_others), 0)
    return rows


@frappe.whitelist()
def auto_allocate_batches_v31(item_code, qty, warehouse=None, customer=None, policy="Reserved First", allow_partial=0):
    """Auto split requested qty across available batches using reservation-aware FEFO logic."""
    requested = flt(qty)
    if requested <= 0:
        frappe.throw("Requested qty must be positive.")

    batches = get_available_batch_stock_v31(item_code, warehouse=warehouse, customer=customer, respect_reservations=1)

    # Reserved-first: move customer's own reservations to top.
    for b in batches:
        b["own_reserved_qty"] = get_reserved_qty_v31(item_code, b.batch_no, b.warehouse, customer) if customer else 0

    if policy == "Reserved First":
        batches = sorted(batches, key=lambda x: (-flt(x.get("own_reserved_qty")), str(x.get("expiry_date") or "9999-12-31"), x.get("batch_no") or ""))
    elif policy == "FIFO":
        batches = sorted(batches, key=lambda x: (x.get("batch_no") or ""))
    else:
        batches = sorted(batches, key=lambda x: (str(x.get("expiry_date") or "9999-12-31"), x.get("batch_no") or ""))

    remaining = requested
    allocations = []
    for b in batches:
        available = flt(b.get("free_qty"))
        if customer and flt(b.get("own_reserved_qty")):
            available += flt(b.get("own_reserved_qty"))
        if available <= 0:
            continue
        alloc = min(remaining, available)
        if alloc <= 0:
            continue
        allocations.append({
            "item_code": item_code,
            "batch_no": b.batch_no,
            "warehouse": b.warehouse,
            "expiry_date": b.expiry_date,
            "qty": alloc,
            "available_qty": available,
            "reserved_qty": flt(b.get("reserved_qty")),
            "own_reserved_qty": flt(b.get("own_reserved_qty"))
        })
        remaining -= alloc
        if remaining <= 0:
            break

    allocated = requested - remaining
    status = "Allocated" if remaining <= 0 else ("Partial" if allocated > 0 else "Shortage")
    if remaining > 0 and not int(allow_partial or 0):
        # Still return preview instead of throw so billing page can warn.
        pass

    audit = frappe.new_doc("Pharma Batch Allocation Audit")
    audit.customer = customer
    audit.warehouse = warehouse
    audit.item_code = item_code
    audit.requested_qty = requested
    audit.allocated_qty = allocated
    audit.shortage_qty = max(remaining, 0)
    audit.allocation_policy = policy
    audit.status = status
    audit.details = frappe.as_json({"allocations": allocations}, indent=2)
    audit.insert(ignore_permissions=True)

    return {
        "item_code": item_code,
        "requested_qty": requested,
        "allocated_qty": allocated,
        "shortage_qty": max(remaining, 0),
        "status": status,
        "policy": policy,
        "allocations": allocations,
        "audit": audit.name
    }


@frappe.whitelist()
def get_batch_allocation_preview_v31(item_code, qty, warehouse=None, customer=None):
    return auto_allocate_batches_v31(item_code=item_code, qty=qty, warehouse=warehouse, customer=customer, policy="Reserved First", allow_partial=1)


@frappe.whitelist()
def apply_auto_batch_allocation_to_payload_v31(data):
    """Apply auto split-batch allocation to billing payload before submit."""
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    customer = data.get("customer")
    warehouse = data.get("warehouse")
    batch_allocations = []
    errors = []

    for row in data.get("items") or []:
        if row.get("is_free_item"):
            continue
        qty = flt(row.get("qty"))
        if not row.get("item_code") or qty <= 0:
            continue
        result = auto_allocate_batches_v31(row.get("item_code"), qty, warehouse=warehouse, customer=customer, allow_partial=0)
        if flt(result.get("shortage_qty")) > 0:
            errors.append(f"{row.get('item_code')}: shortage {result.get('shortage_qty')}")
        allocs = result.get("allocations") or []
        row["batch_allocations"] = allocs
        if allocs:
            row["batch_no"] = allocs[0].get("batch_no")
            row["expiry_date"] = allocs[0].get("expiry_date")
        for a in allocs:
            batch_allocations.append({
                "item_row_id": row.get("row_id"),
                "item_code": row.get("item_code"),
                "batch_no": a.get("batch_no"),
                "expiry_date": a.get("expiry_date"),
                "qty": a.get("qty")
            })

    data["batch_allocations"] = batch_allocations
    data["batch_allocation_errors"] = errors
    return data


@frappe.whitelist()
def reserve_batch_stock_v31(customer, item_code, batch_no, warehouse, reserved_qty, reserved_until=None, company=None, reference_doctype=None, reference_name=None, remarks=None):
    available_rows = get_available_batch_stock_v31(item_code, warehouse=warehouse, customer=customer, respect_reservations=1)
    match = next((r for r in available_rows if r.batch_no == batch_no and r.warehouse == warehouse), None)
    free_qty = flt(match.free_qty if match else 0)
    if flt(reserved_qty) <= 0:
        frappe.throw("Reserved qty must be positive.")
    if flt(reserved_qty) > free_qty:
        frappe.throw(f"Cannot reserve {reserved_qty}; only {free_qty} free qty available.")

    doc = frappe.new_doc("Pharma Batch Reservation")
    doc.posting_date = nowdate()
    doc.company = company
    doc.customer = customer
    doc.warehouse = warehouse
    doc.item_code = item_code
    doc.batch_no = batch_no
    doc.reserved_qty = flt(reserved_qty)
    doc.consumed_qty = 0
    doc.released_qty = 0
    doc.available_reserved_qty = flt(reserved_qty)
    doc.reserved_until = reserved_until
    doc.status = "Active"
    doc.reference_doctype = reference_doctype
    doc.reference_name = reference_name
    doc.remarks = remarks
    doc.insert(ignore_permissions=True)
    doc.submit()
    return doc.name


@frappe.whitelist()
def release_batch_reservation_v31(reservation, qty=None):
    doc = frappe.get_doc("Pharma Batch Reservation", reservation)
    remaining = flt(doc.reserved_qty) - flt(doc.consumed_qty) - flt(doc.released_qty)
    release_qty = flt(qty) if qty else remaining
    if release_qty <= 0:
        frappe.throw("Release qty must be positive.")
    if release_qty > remaining:
        frappe.throw("Release qty exceeds available reserved qty.")
    doc.db_set("released_qty", flt(doc.released_qty) + release_qty)
    new_remaining = flt(doc.reserved_qty) - flt(doc.consumed_qty) - flt(doc.released_qty)
    doc.db_set("available_reserved_qty", new_remaining)
    doc.db_set("status", "Released" if new_remaining <= 0 else "Partially Consumed")
    return doc.name


@frappe.whitelist()
def consume_batch_reservation_v31(customer, item_code, batch_no, warehouse, qty):
    reservations = frappe.get_all("Pharma Batch Reservation",
        filters={"docstatus": 1, "status": ["in", ["Active", "Partially Consumed"]], "customer": customer, "item_code": item_code, "batch_no": batch_no, "warehouse": warehouse},
        fields=["name", "reserved_qty", "consumed_qty", "released_qty"],
        order_by="reserved_until asc, creation asc")
    remaining = flt(qty)
    consumed = []
    for r in reservations:
        available = flt(r.reserved_qty) - flt(r.consumed_qty) - flt(r.released_qty)
        take = min(remaining, available)
        if take <= 0:
            continue
        doc = frappe.get_doc("Pharma Batch Reservation", r.name)
        doc.db_set("consumed_qty", flt(doc.consumed_qty) + take)
        new_remaining = flt(doc.reserved_qty) - flt(doc.consumed_qty) - flt(doc.released_qty)
        doc.db_set("available_reserved_qty", new_remaining)
        doc.db_set("status", "Consumed" if new_remaining <= 0 else "Partially Consumed")
        consumed.append({"reservation": doc.name, "qty": take})
        remaining -= take
        if remaining <= 0:
            break
    return {"requested_qty": flt(qty), "consumed": consumed, "unconsumed_qty": max(remaining, 0)}


@frappe.whitelist()
def get_reserved_batch_report_v31(customer=None, item_code=None, warehouse=None):
    filters = {"docstatus": 1}
    if customer:
        filters["customer"] = customer
    if item_code:
        filters["item_code"] = item_code
    if warehouse:
        filters["warehouse"] = warehouse
    return frappe.get_all("Pharma Batch Reservation", filters=filters, fields=["name", "customer", "warehouse", "item_code", "batch_no", "reserved_qty", "consumed_qty", "released_qty", "available_reserved_qty", "reserved_until", "status"], order_by="reserved_until asc, creation desc")


@frappe.whitelist()
def consume_reservations_from_payload_v31(data):
    """Consume customer-owned reservations from an invoiced payload.

    Called after successful invoice creation. It consumes only reservation-backed
    quantities for the same customer/item/batch/warehouse. Non-reserved stock
    allocations remain unaffected.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}

    customer = data.get("customer")
    warehouse = data.get("warehouse")
    consumed = []

    if not customer:
        return consumed

    for row in data.get("items") or []:
        item_code = row.get("item_code")
        for alloc in row.get("batch_allocations") or []:
            batch_no = alloc.get("batch_no")
            qty = flt(alloc.get("qty"))
            wh = alloc.get("warehouse") or warehouse
            if item_code and batch_no and wh and qty > 0:
                result = consume_batch_reservation_v31(
                    customer=customer,
                    item_code=item_code,
                    batch_no=batch_no,
                    warehouse=wh,
                    qty=qty
                )
                if result.get("consumed"):
                    consumed.append({
                        "item_code": item_code,
                        "batch_no": batch_no,
                        "warehouse": wh,
                        "requested_qty": qty,
                        "reservation_consumption": result
                    })
    return consumed


@frappe.whitelist()
def get_batch_quality_documents_v31(batch_no, item_code=None):
    """Fetch Quality Inspection/QC documents linked to batch where available."""
    docs = []
    if not frappe.db.exists("DocType", "Quality Inspection"):
        return docs

    qi_meta = frappe.get_meta("Quality Inspection")
    conditions = ["docstatus < 2"]
    values = []

    if qi_meta.has_field("batch_no"):
        conditions.append("batch_no=%s")
        values.append(batch_no)
    elif qi_meta.has_field("reference_name"):
        # Fallback through reference_name is weak but useful where QC links to PR/PI.
        return docs
    else:
        return docs

    if item_code and qi_meta.has_field("item_code"):
        conditions.append("item_code=%s")
        values.append(item_code)

    fields = ["name", "inspection_type", "status", "reference_type", "reference_name", "creation"]
    if qi_meta.has_field("item_code"):
        fields.append("item_code")
    if qi_meta.has_field("batch_no"):
        fields.append("batch_no")

    return frappe.get_all(
        "Quality Inspection",
        filters={},
        fields=fields,
        order_by="creation desc"
    ) if False else frappe.db.sql(f"""
        SELECT {', '.join(fields)}
        FROM `tabQuality Inspection`
        WHERE {' AND '.join(conditions)}
        ORDER BY creation DESC
    """, tuple(values), as_dict=True)


@frappe.whitelist()
def get_batch_return_documents_v31(batch_no, item_code=None):
    """Return documents involving a batch: Sales Returns, Purchase Returns, Delivery Note returns."""
    returns = {}

    returns["sales_returns"] = frappe.db.sql("""
        SELECT si.name, si.customer, si.posting_date, sii.item_code, sii.qty, sii.rate, sii.net_amount, si.return_against
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name=sii.parent
        WHERE IFNULL(sii.batch_no,'')=%s
          AND (%s IS NULL OR sii.item_code=%s)
          AND si.docstatus=1
          AND (si.is_return=1 OR sii.qty < 0)
        ORDER BY si.posting_date DESC
    """, (batch_no, item_code, item_code), as_dict=True)

    returns["purchase_returns"] = frappe.db.sql("""
        SELECT pr.name, pr.supplier, pr.posting_date, pri.item_code, pri.qty, pri.rate, pri.amount, pr.return_against
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name=pri.parent
        WHERE IFNULL(pri.batch_no,'')=%s
          AND (%s IS NULL OR pri.item_code=%s)
          AND pr.docstatus=1
          AND (pr.is_return=1 OR pri.qty < 0)
        ORDER BY pr.posting_date DESC
    """, (batch_no, item_code, item_code), as_dict=True)

    returns["delivery_note_returns"] = frappe.db.sql("""
        SELECT dn.name, dn.customer, dn.posting_date, dni.item_code, dni.qty, dn.return_against
        FROM `tabDelivery Note Item` dni
        INNER JOIN `tabDelivery Note` dn ON dn.name=dni.parent
        WHERE IFNULL(dni.batch_no,'')=%s
          AND (%s IS NULL OR dni.item_code=%s)
          AND dn.docstatus=1
          AND (dn.is_return=1 OR dni.qty < 0)
        ORDER BY dn.posting_date DESC
    """, (batch_no, item_code, item_code), as_dict=True) if frappe.db.exists("DocType", "Delivery Note") else []

    return returns


@frappe.whitelist()
def get_batch_genealogy_v31(batch_no, item_code=None):
    """Production-hardened pharma genealogy view for one batch.

    Includes purchase, sales, stock ledger, reservations, QC/Quality Inspection,
    and explicit return documents.
    """
    batch = frappe.db.get_value("Batch", batch_no, ["name", "item", "expiry_date", "manufacturing_date"], as_dict=True) if frappe.db.exists("Batch", batch_no) else {}
    item_code = item_code or (batch.get("item") if batch else None)

    purchase_receipts = frappe.db.sql("""
        SELECT pr.name, pr.supplier, pr.posting_date, pri.item_code, pri.qty, pri.rate, pri.amount
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name=pri.parent
        WHERE IFNULL(pri.batch_no,'')=%s
          AND (%s IS NULL OR pri.item_code=%s)
          AND pr.docstatus=1
          AND IFNULL(pr.is_return,0)=0
        ORDER BY pr.posting_date DESC
    """, (batch_no, item_code, item_code), as_dict=True)

    sales_invoices = frappe.db.sql("""
        SELECT si.name, si.customer, si.posting_date, sii.item_code, sii.qty, sii.rate, sii.net_amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name=sii.parent
        WHERE IFNULL(sii.batch_no,'')=%s
          AND (%s IS NULL OR sii.item_code=%s)
          AND si.docstatus=1
          AND IFNULL(si.is_return,0)=0
        ORDER BY si.posting_date DESC
    """, (batch_no, item_code, item_code), as_dict=True)

    stock_ledger = frappe.db.sql("""
        SELECT posting_date, voucher_type, voucher_no, warehouse, actual_qty, qty_after_transaction
        FROM `tabStock Ledger Entry`
        WHERE batch_no=%s
          AND (%s IS NULL OR item_code=%s)
        ORDER BY posting_date DESC, creation DESC
        LIMIT 500
    """, (batch_no, item_code, item_code), as_dict=True)

    reservations = frappe.get_all(
        "Pharma Batch Reservation",
        filters={"batch_no": batch_no},
        fields=["name", "customer", "warehouse", "item_code", "reserved_qty", "consumed_qty", "released_qty", "status", "reserved_until"],
        order_by="creation desc"
    ) if frappe.db.exists("DocType", "Pharma Batch Reservation") else []

    returns = get_batch_return_documents_v31(batch_no, item_code)
    quality_documents = get_batch_quality_documents_v31(batch_no, item_code)

    return {
        "batch": batch,
        "item_code": item_code,
        "purchase_receipts": purchase_receipts,
        "sales_invoices": sales_invoices,
        "returns": returns,
        "quality_documents": quality_documents,
        "stock_ledger": stock_ledger,
        "reservations": reservations,
        "summary": {
            "purchased_qty": sum(flt(x.qty) for x in purchase_receipts),
            "sold_qty": sum(abs(flt(x.qty)) for x in sales_invoices if flt(x.qty) > 0),
            "sales_return_qty": sum(abs(flt(x.qty)) for x in returns.get("sales_returns", [])),
            "purchase_return_qty": sum(abs(flt(x.qty)) for x in returns.get("purchase_returns", [])),
            "reserved_qty": sum(flt(x.reserved_qty) - flt(x.consumed_qty) - flt(x.released_qty) for x in reservations),
            "qc_count": len(quality_documents)
        }
    }


@frappe.whitelist()
def get_customer_pricing_memory_v31_2(customer, item_code):
    name = f"{customer}-{item_code}"
    if frappe.db.exists("Pharma Pricing Memory", name):
        doc = frappe.get_doc("Pharma Pricing Memory", name)
        return doc.as_dict()
    update_pricing_memory_v31_2(customer=customer, item_code=item_code)
    if frappe.db.exists("Pharma Pricing Memory", name):
        return frappe.get_doc("Pharma Pricing Memory", name).as_dict()
    return {}


@frappe.whitelist()
def get_repeat_order_v31_2(customer, mode="last_invoice", limit=20):
    """Return lines for one-key repeat order."""
    if not customer:
        return {"items": [], "source": None}

    if mode == "favorites":
        rows = frappe.db.sql("""
            SELECT sii.item_code, MAX(sii.item_name) item_name, AVG(ABS(sii.qty)) qty, AVG(sii.rate) rate,
                   AVG(IFNULL(sii.discount_percentage,0)) discount_percentage, COUNT(*) frequency
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name=sii.parent
            WHERE si.customer=%s AND si.docstatus=1 AND si.posting_date >= %s
            GROUP BY sii.item_code
            ORDER BY frequency DESC
            LIMIT %s
        """, (customer, add_days(nowdate(), -180), int(limit or 20)), as_dict=True)
        return {"source": "favorites", "items": rows}

    invoice = frappe.db.sql("""
        SELECT name FROM `tabSales Invoice`
        WHERE customer=%s AND docstatus=1 AND IFNULL(is_return,0)=0
        ORDER BY posting_date DESC, creation DESC
        LIMIT 1
    """, (customer,), as_dict=True)
    if not invoice:
        return {"items": [], "source": None}
    inv = invoice[0].name
    rows = frappe.db.sql("""
        SELECT item_code, item_name, ABS(qty) qty, rate, IFNULL(discount_percentage,0) discount_percentage
        FROM `tabSales Invoice Item`
        WHERE parent=%s AND IFNULL(qty,0) > 0
        LIMIT %s
    """, (inv, int(limit or 20)), as_dict=True)
    return {"source": inv, "items": rows}


@frappe.whitelist()
def log_billing_intelligence_exceptions_v31_2(data, result=None):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    result = result or {}
    customer = data.get("customer")
    sales_invoice = result.get("sales_invoice") or result.get("invoice") or result.get("name")
    created = []

    for row in data.get("items") or []:
        item_code = row.get("item_code")
        if not item_code:
            continue
        profit = get_profit_warning_v31_2(item_code=item_code, rate=flt(row.get("rate")), qty=flt(row.get("qty") or 1), discount_percentage=flt(row.get("discount_percentage")), batch_no=row.get("batch_no"), customer=customer)
        if profit.get("severity") == "BLOCK":
            doc = frappe.new_doc("Pharma Loss Sale Exception")
            doc.customer = customer
            doc.item_code = item_code
            doc.batch_no = row.get("batch_no")
            doc.selling_rate = flt(row.get("rate"))
            doc.cost_rate = flt(profit.get("margin", {}).get("cost"))
            doc.loss_amount = abs(flt(profit.get("margin", {}).get("gross_margin")))
            doc.sales_invoice = sales_invoice
            doc.details = frappe.as_json(profit, indent=2)
            doc.insert(ignore_permissions=True)
            created.append(doc.name)

        if customer:
            discount = get_discount_anomaly_v31_2(customer, item_code, flt(row.get("discount_percentage")))
            if discount.get("severity") in ["WARNING", "BLOCK"]:
                doc = frappe.new_doc("Pharma Discount Exception")
                doc.customer = customer
                doc.item_code = item_code
                doc.entered_discount = flt(discount.get("entered_discount"))
                doc.typical_discount = flt(discount.get("typical_discount"))
                doc.variance = flt(discount.get("variance"))
                doc.severity = discount.get("severity")
                doc.sales_invoice = sales_invoice
                doc.details = frappe.as_json(discount, indent=2)
                doc.insert(ignore_permissions=True)
                created.append(doc.name)

    # Update memory after invoice.
    if customer:
        for row in data.get("items") or []:
            if row.get("item_code"):
                update_pricing_memory_v31_2(customer=customer, item_code=row.get("item_code"))
    return created


@frappe.whitelist()
def get_billing_intelligence_settings_v31_2_1():
    defaults = {
        "pricing_memory_days": 90,
        "discount_warning_variance": 7,
        "discount_block_variance": 15,
        "low_margin_warning_percent": 5,
        "block_loss_sale_without_approval": 1,
        "require_manager_for_loss_sale": 1
    }
    if frappe.db.exists("DocType", "Pharma Billing Intelligence Settings"):
        for k in defaults:
            val = frappe.db.get_single_value("Pharma Billing Intelligence Settings", k)
            if val is not None:
                defaults[k] = val
    return defaults


def safe_row_id_v31_2_1():
    if hasattr(frappe, "generate_hash"):
        return frappe.generate_hash(length=8)
    return frappe.utils.random_string(8)


@frappe.whitelist()
def update_pricing_memory_v31_2(customer=None, item_code=None):
    settings = get_billing_intelligence_settings_v31_2_1()
    days = cint(settings.get("pricing_memory_days") or 90)
    from_date = add_days(nowdate(), -days)
    conditions = ["si.docstatus=1", "IFNULL(si.is_return,0)=0", "IFNULL(sii.qty,0)>0", "si.posting_date >= %s"]
    values = [from_date]
    if customer:
        conditions.append("si.customer=%s")
        values.append(customer)
    if item_code:
        conditions.append("sii.item_code=%s")
        values.append(item_code)

    rows = frappe.db.sql(f"""
        SELECT si.customer, sii.item_code,
               MAX(si.posting_date) AS last_sale_date,
               AVG(sii.rate) AS avg_rate_90d,
               AVG(IFNULL(sii.discount_percentage,0)) AS avg_discount_90d,
               AVG(ABS(sii.qty)) AS typical_qty
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name=sii.parent
        WHERE {' AND '.join(conditions)}
        GROUP BY si.customer, sii.item_code
    """, tuple(values), as_dict=True)

    updated = []
    for r in rows:
        last = frappe.db.sql("""
            SELECT si.name, si.posting_date, sii.rate, IFNULL(sii.discount_percentage,0) discount_percentage,
                   sii.qty, sii.item_code
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON si.name=sii.parent
            WHERE si.docstatus=1 AND IFNULL(si.is_return,0)=0 AND IFNULL(sii.qty,0)>0
              AND si.customer=%s AND sii.item_code=%s
            ORDER BY si.posting_date DESC, si.creation DESC
            LIMIT 1
        """, (r.customer, r.item_code), as_dict=True)
        last = last[0] if last else {}
        margin = get_margin_intelligence(
            item_code=r.item_code,
            rate=flt(last.get("rate")),
            qty=abs(flt(last.get("qty") or 1)),
            discount_percentage=flt(last.get("discount_percentage"))
        )
        name = f"{r.customer}-{r.item_code}"
        doc = frappe.get_doc("Pharma Pricing Memory", name) if frappe.db.exists("Pharma Pricing Memory", name) else frappe.new_doc("Pharma Pricing Memory")
        doc.customer = r.customer
        doc.item_code = r.item_code
        doc.last_rate = flt(last.get("rate"))
        doc.last_discount_percentage = flt(last.get("discount_percentage"))
        doc.last_margin_percent = flt(margin.get("margin_percent"))
        doc.last_sale_date = last.get("posting_date")
        doc.last_invoice = last.get("name")
        doc.avg_rate_90d = flt(r.avg_rate_90d)
        doc.avg_discount_90d = flt(r.avg_discount_90d)
        doc.typical_qty = flt(r.typical_qty)
        doc.last_updated = now_datetime()
        doc.save(ignore_permissions=True)
        updated.append(doc.name)
    return updated


@frappe.whitelist()
def get_profit_warning_v31_2(item_code, rate, qty=1, discount_percentage=0, batch_no=None, customer=None):
    settings = get_billing_intelligence_settings_v31_2_1()
    low_margin = flt(settings.get("low_margin_warning_percent") or 5)
    margin = get_margin_intelligence(item_code=item_code, rate=rate, qty=qty, discount_percentage=discount_percentage, batch_no=batch_no)
    severity = "OK"
    message = "Margin OK"
    valuation_status = "OK"
    if margin.get("cost") is None or flt(margin.get("cost")) <= 0:
        valuation_status = "MISSING_OR_ZERO_COST"
        severity = "WARNING"
        message = "Cost valuation unavailable or zero; verify stock valuation."
    if flt(margin.get("gross_margin")) < 0:
        severity = "BLOCK"
        message = "LOSS SALE: selling below cost."
    elif flt(margin.get("margin_percent")) < low_margin:
        severity = "WARNING"
        message = "Low margin sale."
    return {"severity": severity, "message": message, "valuation_status": valuation_status, "margin": margin}


@frappe.whitelist()
def get_discount_anomaly_v31_2(customer, item_code, entered_discount):
    settings = get_billing_intelligence_settings_v31_2_1()
    warning_var = flt(settings.get("discount_warning_variance") or 7)
    block_var = flt(settings.get("discount_block_variance") or 15)
    mem = get_customer_pricing_memory_v31_2(customer, item_code) if customer and item_code else {}
    typical = flt(mem.get("avg_discount_90d") or mem.get("last_discount_percentage") or 0)
    variance = flt(entered_discount) - typical
    severity = "OK"
    if variance >= block_var:
        severity = "BLOCK"
    elif variance >= warning_var:
        severity = "WARNING"
    return {"severity": severity, "entered_discount": flt(entered_discount), "typical_discount": typical, "variance": variance, "warning_threshold": warning_var, "block_threshold": block_var, "pricing_memory": mem}


@frappe.whitelist()
def analyze_billing_payload_v31_2(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    customer = data.get("customer")
    warnings = []
    rows = []
    for row in data.get("items") or []:
        item_code = row.get("item_code")
        if not item_code:
            continue
        pricing = get_customer_pricing_memory_v31_2(customer, item_code) if customer else {}
        profit = get_profit_warning_v31_2(item_code=item_code, rate=flt(row.get("rate")), qty=flt(row.get("qty") or 1), discount_percentage=flt(row.get("discount_percentage")), batch_no=row.get("batch_no"), customer=customer)
        discount = get_discount_anomaly_v31_2(customer, item_code, flt(row.get("discount_percentage"))) if customer else {"severity": "OK"}
        rows.append({"item_code": item_code, "pricing_memory": pricing, "profit_warning": profit, "discount_anomaly": discount})
        if profit.get("severity") in ["WARNING", "BLOCK"]:
            warnings.append({"type": "Profit", "severity": profit.get("severity"), "item_code": item_code, "message": profit.get("message")})
        if discount.get("severity") in ["WARNING", "BLOCK"]:
            warnings.append({"type": "Discount", "severity": discount.get("severity"), "item_code": item_code, "message": f"Discount variance {discount.get('variance')}%"})
    return {"rows": rows, "warnings": warnings, "has_block": any(w.get("severity") == "BLOCK" for w in warnings)}


@frappe.whitelist()
def apply_repeat_order_to_payload_v31_2(data, mode="last_invoice"):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    customer = data.get("customer")
    repeat = get_repeat_order_v31_2(customer, mode=mode)
    existing = {r.get("item_code") for r in data.get("items", [])}
    for r in repeat.get("items") or []:
        if r.item_code in existing:
            continue
        qty = flt(r.get("qty") or 1)
        rate = flt(r.get("rate"))
        disc = flt(r.get("discount_percentage"))
        data.setdefault("items", []).append({"row_id": safe_row_id_v31_2_1(), "item_code": r.item_code, "item_name": r.get("item_name"), "qty": qty, "rate": rate, "discount_percentage": disc, "amount": qty * rate * (1 - disc / 100)})
    data["repeat_order_source"] = repeat.get("source")
    return data


@frappe.whitelist()
def smart_barcode_add_v31_2(barcode, customer=None, warehouse=None):
    item_code = None
    if frappe.db.exists("DocType", "Item Barcode"):
        item_code = frappe.db.get_value("Item Barcode", {"barcode": barcode}, "parent")
    if not item_code and frappe.get_meta("Item").has_field("barcode"):
        item_code = frappe.db.get_value("Item", {"barcode": barcode}, "item_code")
    if not item_code and frappe.db.exists("Item", barcode):
        item_code = barcode
    if not item_code:
        return {"found": False, "message": f"Barcode not found: {barcode}"}
    item = frappe.db.get_value("Item", item_code, ["item_code", "item_name", "standard_rate"], as_dict=True)
    rate = flt(_safe_item_value(item_code, "pharma_ptr", None) or item.standard_rate or 0)
    row = {"row_id": safe_row_id_v31_2_1(), "item_code": item.item_code, "item_name": item.item_name, "qty": 1, "rate": rate, "discount_percentage": 0, "amount": rate}
    alloc = auto_allocate_batches_v31(item_code=item_code, qty=1, warehouse=warehouse, customer=customer, allow_partial=1)
    if alloc.get("allocations"):
        row["batch_allocations"] = alloc.get("allocations")
        row["batch_no"] = alloc.get("allocations")[0].get("batch_no")
        row["expiry_date"] = alloc.get("allocations")[0].get("expiry_date")
    return {"found": True, "row": row, "allocation": alloc}


def _enforce_loss_sale_approval_v31_2_1(data, intelligence):
    settings = get_billing_intelligence_settings_v31_2_1()
    if not intelligence.get("has_block") or not cint(settings.get("block_loss_sale_without_approval")):
        return
    validation = validate_loss_sale_approval_v31_2_1(data)
    if not validation.get("valid"):
        frappe.throw(validation.get("message"))


@frappe.whitelist()
def get_loss_sale_approval_queue_v31_2_2(status=None, customer=None, limit=100):
    """Manager approval queue for loss-sale approvals."""
    filters = {}
    if status:
        filters["status"] = status
    else:
        filters["status"] = ["in", ["Draft", "Approved"]]
    if customer:
        filters["customer"] = customer

    approvals = frappe.get_all(
        "Pharma Loss Sale Approval",
        filters=filters,
        fields=["name", "posting_datetime", "customer", "company", "status", "valid_until", "approved_by", "approved_on", "reason", "docstatus", "approved_loss_amount", "used_sales_invoice", "used_by", "used_on", "expired_on"],
        order_by="creation desc",
        limit=int(limit or 100)
    )

    for a in approvals:
        a["items"] = frappe.get_all(
            "Pharma Loss Sale Approval Item",
            filters={"parent": a.name},
            fields=["item_code", "batch_no", "qty", "selling_rate", "cost_rate", "loss_amount", "margin_percent"],
            order_by="idx asc"
        )
    return approvals


@frappe.whitelist()
def quick_invoice_submit(data, action="invoice"):
    if isinstance(data, str):
        data = frappe.parse_json(data)

    intelligence = analyze_billing_payload_v31_2(data)
    _enforce_loss_sale_approval_v31_2_1(data, intelligence)

    data = apply_auto_batch_allocation_to_payload_v31(data)
    if data.get("batch_allocation_errors"):
        frappe.throw("<br>".join(data.get("batch_allocation_errors")))

    data = apply_advanced_scheme_for_invoice_submission(data)

    preflight = validate_pharma_transaction_preflight(
        customer=data.get("customer"),
        company=data.get("company"),
        posting_date=data.get("posting_date") or nowdate(),
        projected_grand_total=data.get("grand_total") or 0
    )
    if not preflight.get("valid"):
        messages = []
        if preflight.get("license", {}).get("messages"):
            messages += preflight.get("license", {}).get("messages")
        if preflight.get("credit", {}).get("message"):
            messages.append(preflight.get("credit", {}).get("message"))
        frappe.throw("<br>".join(messages or ["Transaction preflight failed."]))

    result = create_quick_sale(data, action)
    result_payload = result if isinstance(result, dict) else {"sales_invoice": result}

    log_advanced_scheme_from_invoice_result(data, result_payload)
    log_billing_intelligence_exceptions_v31_2(data, result_payload)

    if action == "invoice":
        consumed = consume_reservations_from_payload_v31(data)
        mark_loss_sale_approval_used_v31_2_2(data, result_payload)
        if isinstance(result, dict):
            result["reservation_consumption"] = consumed
            result["loss_sale_approval"] = data.get("loss_sale_approval")

    return result


@frappe.whitelist()
def operator_submit_invoice(data, action="invoice"):
    if isinstance(data, str):
        data = frappe.parse_json(data)

    intelligence = analyze_billing_payload_v31_2(data)
    _enforce_loss_sale_approval_v31_2_1(data, intelligence)

    data = apply_auto_batch_allocation_to_payload_v31(data)
    if data.get("batch_allocation_errors"):
        frappe.throw("<br>".join(data.get("batch_allocation_errors")))

    data = apply_advanced_scheme_for_invoice_submission(data)

    preflight = operator_payload_preflight(data)
    if not preflight.get("valid"):
        frappe.throw("<br>".join(preflight.get("errors") or ["Preflight failed."]))

    result = create_quick_sale(data, action)
    result_payload = result if isinstance(result, dict) else {"sales_invoice": result}

    log_advanced_scheme_from_invoice_result(data, result_payload)
    log_billing_intelligence_exceptions_v31_2(data, result_payload)

    if action == "invoice":
        consumed = consume_reservations_from_payload_v31(data)
        mark_loss_sale_approval_used_v31_2_2(data, result_payload)
        if isinstance(result, dict):
            result["reservation_consumption"] = consumed
            result["loss_sale_approval"] = data.get("loss_sale_approval")

    return result


def calculate_loss_sale_amount_v31_3(data):
    """Calculate total loss amount for BLOCK-level loss-sale rows."""
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    analysis = analyze_billing_payload_v31_2(data)
    total = 0
    rows = []
    for r in analysis.get("rows", []):
        if r.get("profit_warning", {}).get("severity") == "BLOCK":
            m = r.get("profit_warning", {}).get("margin", {})
            loss = abs(flt(m.get("gross_margin")))
            total += loss
            rows.append({"item_code": r.get("item_code"), "loss_amount": loss})
    return {"total_loss_amount": total, "rows": rows}


@frappe.whitelist()
def expire_loss_sale_approvals_v31_3():
    """Expire stale loss-sale approvals. Intended for scheduler and manual admin runs."""
    expired = []
    rows = frappe.get_all(
        "Pharma Loss Sale Approval",
        filters={"docstatus": 1, "status": "Approved", "valid_until": ["<", now_datetime()]},
        fields=["name"]
    )
    for r in rows:
        doc = frappe.get_doc("Pharma Loss Sale Approval", r.name)
        doc.db_set("status", "Expired")
        if frappe.get_meta("Pharma Loss Sale Approval").has_field("expired_on"):
            doc.db_set("expired_on", now_datetime())
        doc.add_comment("Info", "Approval expired automatically.")
        expired.append(doc.name)
    return expired


@frappe.whitelist()
def create_loss_sale_approval_v31_2_1(data, reason=None):
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    analysis = analyze_billing_payload_v31_2(data)
    block_rows = [r for r in analysis.get("rows", []) if r.get("profit_warning", {}).get("severity") == "BLOCK"]
    if not block_rows:
        frappe.throw("No loss-sale rows found for approval.")

    doc = frappe.new_doc("Pharma Loss Sale Approval")
    doc.customer = data.get("customer")
    doc.company = data.get("company")
    doc.status = "Draft"
    doc.valid_until = add_to_date(now_datetime(), hours=2)
    doc.reason = reason

    approved_loss_amount = 0
    for r in block_rows:
        m = r.get("profit_warning", {}).get("margin", {})
        src = next((x for x in data.get("items", []) if x.get("item_code") == r.get("item_code")), {})
        loss_amount = abs(flt(m.get("gross_margin")))
        approved_loss_amount += loss_amount
        doc.append("items", {
            "item_code": r.get("item_code"),
            "batch_no": src.get("batch_no"),
            "qty": flt(src.get("qty") or 1),
            "selling_rate": flt(src.get("rate")),
            "cost_rate": flt(m.get("cost")),
            "loss_amount": loss_amount,
            "margin_percent": flt(m.get("margin_percent"))
        })

    if frappe.get_meta("Pharma Loss Sale Approval").has_field("approved_loss_amount"):
        doc.approved_loss_amount = approved_loss_amount

    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def approve_loss_sale_approval_v31_2_1(approval, approve=1):
    """Approve or reject loss-sale approval.

    Production GA hardening:
    - Used approvals are immutable.
    - Expired approvals cannot be approved.
    - Approval/rejection is stamped with user and timestamp.
    """
    doc = frappe.get_doc("Pharma Loss Sale Approval", approval)

    if doc.status == "Used":
        frappe.throw("Used loss-sale approvals are locked and cannot be changed.")
    if doc.status == "Expired":
        frappe.throw("Expired loss-sale approvals cannot be approved or rejected.")
    if doc.valid_until and get_datetime(doc.valid_until) < now_datetime():
        doc.db_set("status", "Expired")
        if frappe.get_meta("Pharma Loss Sale Approval").has_field("expired_on"):
            doc.db_set("expired_on", now_datetime())
        frappe.throw("Loss-sale approval has expired.")

    doc.status = "Approved" if cint(approve) else "Rejected"
    doc.approved_by = frappe.session.user
    doc.approved_on = now_datetime()
    doc.save(ignore_permissions=True)

    if doc.docstatus == 0 and cint(approve):
        doc.submit()

    return doc.name


@frappe.whitelist()
def validate_loss_sale_approval_v31_2_1(data):
    """Validate loss-sale approval before invoice.

    Production GA hardening:
    - Used approvals cannot be reused.
    - Company is validated.
    - Current loss cannot exceed approved loss.
    - Expired approvals are marked Expired immediately.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}

    approval = data.get("loss_sale_approval")
    if not approval:
        return {"valid": False, "message": "Loss sale approval is required."}
    if not frappe.db.exists("Pharma Loss Sale Approval", approval):
        return {"valid": False, "message": "Loss sale approval not found."}

    doc = frappe.get_doc("Pharma Loss Sale Approval", approval)

    if doc.status == "Used":
        return {"valid": False, "message": "Loss sale approval has already been used and cannot be reused."}
    if doc.status == "Expired":
        return {"valid": False, "message": "Loss sale approval has expired."}
    if doc.status == "Rejected":
        return {"valid": False, "message": "Loss sale approval was rejected."}
    if doc.docstatus != 1 or doc.status != "Approved":
        return {"valid": False, "message": "Loss sale approval is not approved/submitted."}

    if doc.valid_until and get_datetime(doc.valid_until) < now_datetime():
        doc.db_set("status", "Expired")
        if frappe.get_meta("Pharma Loss Sale Approval").has_field("expired_on"):
            doc.db_set("expired_on", now_datetime())
        return {"valid": False, "message": "Loss sale approval has expired."}

    if doc.customer and doc.customer != data.get("customer"):
        return {"valid": False, "message": "Loss sale approval customer mismatch."}
    if doc.company and data.get("company") and doc.company != data.get("company"):
        return {"valid": False, "message": "Loss sale approval company mismatch."}

    approved_items = {r.item_code for r in doc.items}
    analysis = analyze_billing_payload_v31_2(data)
    block_items = {r.get("item_code") for r in analysis.get("rows", []) if r.get("profit_warning", {}).get("severity") == "BLOCK"}

    if not block_items.issubset(approved_items):
        return {"valid": False, "message": "Approval does not cover all loss-sale items."}

    current_loss = calculate_loss_sale_amount_v31_3(data).get("total_loss_amount")
    approved_loss = flt(doc.get("approved_loss_amount")) if hasattr(doc, "approved_loss_amount") else sum(flt(r.loss_amount) for r in doc.items)
    if flt(current_loss) > flt(approved_loss) + 0.01:
        return {"valid": False, "message": f"Current loss amount {current_loss} exceeds approved loss amount {approved_loss}."}

    return {"valid": True, "message": "Approved."}


@frappe.whitelist()
def mark_loss_sale_approval_used_v31_2_2(data, result=None):
    """Mark approved loss-sale approval as Used after invoice creation.

    Production GA hardening:
    - Does not use dict-style db_set.
    - Explicitly stamps each audit field.
    - Refuses to mutate approvals already Used.
    """
    if isinstance(data, str):
        data = frappe.parse_json(data)
    data = data or {}
    result = result or {}

    approval = data.get("loss_sale_approval")
    if not approval or not frappe.db.exists("Pharma Loss Sale Approval", approval):
        return None

    doc = frappe.get_doc("Pharma Loss Sale Approval", approval)

    if doc.status == "Used":
        frappe.throw("Loss-sale approval has already been used and cannot be reused.")
    if doc.status != "Approved":
        return None

    sales_invoice = result.get("sales_invoice") or result.get("invoice") or result.get("name")
    meta = frappe.get_meta("Pharma Loss Sale Approval")

    doc.db_set("status", "Used")

    if meta.has_field("used_sales_invoice") and sales_invoice:
        doc.db_set("used_sales_invoice", sales_invoice)
    if meta.has_field("used_by"):
        doc.db_set("used_by", frappe.session.user)
    if meta.has_field("used_on"):
        doc.db_set("used_on", now_datetime())

    if sales_invoice:
        doc.add_comment("Info", f"Used for Sales Invoice {sales_invoice}")

    return approval
