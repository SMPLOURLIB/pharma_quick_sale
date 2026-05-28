from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import compare_return_credit_note_to_original

def execute(filters=None):
    filters = filters or {}
    pharma_return = filters.get("pharma_return")

    columns = [
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": "Batch", "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 140},
        {"label": "Rate Match", "fieldname": "rate_match", "fieldtype": "Check", "width": 100},
        {"label": "Discount Match", "fieldname": "discount_match", "fieldtype": "Check", "width": 120},
        {"label": "Tax Template Match", "fieldname": "tax_template_match", "fieldtype": "Check", "width": 140},
        {"label": "Return Rate", "fieldname": "return_rate", "fieldtype": "Currency", "width": 110},
        {"label": "Original Rate", "fieldname": "original_rate", "fieldtype": "Currency", "width": 110}
    ]

    if not pharma_return:
        return columns, []

    result = compare_return_credit_note_to_original(pharma_return=pharma_return)
    return columns, result.get("items", [])
