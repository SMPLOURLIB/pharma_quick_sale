import frappe
def execute(filters=None):
    data = frappe.get_all("Pharma Discount Exception", fields=["posting_datetime","customer","item_code","entered_discount","typical_discount","variance","severity","sales_invoice"], order_by="posting_datetime desc", limit=500)
    cols = [
        {"label":"Datetime","fieldname":"posting_datetime","fieldtype":"Datetime","width":160},
        {"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Entered %","fieldname":"entered_discount","fieldtype":"Percent","width":100},
        {"label":"Typical %","fieldname":"typical_discount","fieldtype":"Percent","width":100},
        {"label":"Variance","fieldname":"variance","fieldtype":"Percent","width":100},
        {"label":"Severity","fieldname":"severity","fieldtype":"Data","width":100},
        {"label":"Invoice","fieldname":"sales_invoice","fieldtype":"Link","options":"Sales Invoice","width":160}
    ]
    return cols, data
