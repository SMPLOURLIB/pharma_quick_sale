from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_batch_genealogy_v31

def execute(filters=None):
    filters = filters or {}
    if not filters.get("batch_no"):
        return [], []
    data = get_batch_genealogy_v31(filters.get("batch_no"), filters.get("item_code"))
    rows = []

    for r in data.get("purchase_receipts", []):
        rows.append({"section": "Purchase", "document": r.get("name"), "party": r.get("supplier"), "item_code": r.get("item_code"), "qty": r.get("qty"), "date": r.get("posting_date")})

    for r in data.get("sales_invoices", []):
        rows.append({"section": "Sales", "document": r.get("name"), "party": r.get("customer"), "item_code": r.get("item_code"), "qty": r.get("qty"), "date": r.get("posting_date")})

    for section_key, label in [("sales_returns", "Sales Return"), ("purchase_returns", "Purchase Return"), ("delivery_note_returns", "Delivery Return")]:
        for r in (data.get("returns", {}) or {}).get(section_key, []):
            rows.append({"section": label, "document": r.get("name"), "party": r.get("customer") or r.get("supplier"), "item_code": r.get("item_code"), "qty": r.get("qty"), "date": r.get("posting_date")})

    for r in data.get("quality_documents", []):
        rows.append({"section": "Quality", "document": r.get("name"), "party": r.get("status"), "item_code": r.get("item_code"), "qty": None, "date": r.get("creation")})

    for r in data.get("reservations", []):
        rows.append({"section": "Reservation", "document": r.get("name"), "party": r.get("customer") or r.get("warehouse"), "item_code": r.get("item_code"), "qty": r.get("reserved_qty"), "date": r.get("reserved_until")})

    for r in data.get("stock_ledger", []):
        rows.append({"section": "Stock Ledger", "document": r.get("voucher_no"), "party": r.get("warehouse"), "item_code": None, "qty": r.get("actual_qty"), "date": r.get("posting_date")})

    cols = [
        {"label":"Section","fieldname":"section","fieldtype":"Data","width":120},
        {"label":"Document","fieldname":"document","fieldtype":"Data","width":180},
        {"label":"Party/Warehouse/Status","fieldname":"party","fieldtype":"Data","width":220},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Qty","fieldname":"qty","fieldtype":"Float","width":100},
        {"label":"Date","fieldname":"date","fieldtype":"Date","width":130}
    ]
    return cols, rows
