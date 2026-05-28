from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import validate_gst_stock_for_invoice

def execute(filters=None):
    filters = filters or {}
    invoice = filters.get("sales_invoice")

    columns = [
        {"label": "Sales Invoice", "fieldname": "sales_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 180},
        {"label": "Valid", "fieldname": "valid", "fieldtype": "Check", "width": 80},
        {"label": "Issue", "fieldname": "issue", "fieldtype": "Data", "width": 500}
    ]

    if not invoice:
        return columns, []

    result = validate_gst_stock_for_invoice(invoice)
    if result.get("valid"):
        return columns, [{"sales_invoice": invoice, "valid": 1, "issue": "No issues found"}]

    return columns, [
        {"sales_invoice": invoice, "valid": 0, "issue": issue}
        for issue in result.get("issues", [])
    ]
