import frappe

def execute(filters=None):
    filters = filters or {}
    conditions = {}
    if filters.get("severity"):
        conditions["severity"] = filters.get("severity")
    if filters.get("action"):
        conditions["action"] = ["like", f"%{filters.get('action')}%"]

    columns = [
        {"label": "Datetime", "fieldname": "posting_datetime", "fieldtype": "Datetime", "width": 160},
        {"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "width": 160},
        {"label": "Action", "fieldname": "action", "fieldtype": "Data", "width": 220},
        {"label": "Severity", "fieldname": "severity", "fieldtype": "Data", "width": 100},
        {"label": "Reference", "fieldname": "reference_name", "fieldtype": "Data", "width": 180},
        {"label": "Details", "fieldname": "details", "fieldtype": "Data", "width": 400}
    ]

    data = frappe.get_all(
        "Pharma Audit Log",
        filters=conditions,
        fields=["posting_datetime", "user", "action", "severity", "reference_name", "details"],
        order_by="posting_datetime desc",
        limit=500
    )
    return columns, data
