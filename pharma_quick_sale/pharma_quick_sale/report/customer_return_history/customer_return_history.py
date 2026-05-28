import frappe

def execute(filters=None):
    filters = filters or {}
    customer = filters.get("customer")

    columns = [
        {"label": "Return", "fieldname": "name", "fieldtype": "Link", "options": "Pharma Return", "width": 160},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
        {"label": "Type", "fieldname": "return_type", "fieldtype": "Data", "width": 140},
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 120},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 140},
        {"label": "Credit Note", "fieldname": "sales_return_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
        {"label": "Supplier Claim", "fieldname": "supplier_claim", "fieldtype": "Link", "options": "Pharma Supplier Claim", "width": 160}
    ]

    filters_sql = {}
    if customer:
        filters_sql["customer"] = customer

    data = frappe.get_all(
        "Pharma Return",
        filters=filters_sql,
        fields=["name", "customer", "return_type", "posting_date", "status", "sales_return_invoice", "supplier_claim"],
        order_by="posting_date desc, modified desc"
    )

    return columns, data
