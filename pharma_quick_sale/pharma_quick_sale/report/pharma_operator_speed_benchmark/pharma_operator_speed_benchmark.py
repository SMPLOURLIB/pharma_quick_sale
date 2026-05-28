import frappe

def execute(filters=None):
    columns = [
        {"label":"Datetime","fieldname":"posting_datetime","fieldtype":"Datetime","width":160},
        {"label":"User","fieldname":"user","fieldtype":"Link","options":"User","width":150},
        {"label":"Severity","fieldname":"severity","fieldtype":"Data","width":100},
        {"label":"Details","fieldname":"details","fieldtype":"Data","width":600}
    ]
    data = frappe.get_all("Pharma Audit Log", filters={"action":"Fast Billing Benchmark"}, fields=["posting_datetime","user","severity","details"], order_by="posting_datetime desc", limit=500)
    return columns, data
