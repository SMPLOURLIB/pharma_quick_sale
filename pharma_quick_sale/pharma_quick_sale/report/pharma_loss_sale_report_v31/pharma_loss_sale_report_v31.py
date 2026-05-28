import frappe
def execute(filters=None):
    data = frappe.get_all("Pharma Loss Sale Exception", fields=["posting_datetime","customer","item_code","batch_no","selling_rate","cost_rate","loss_amount","sales_invoice"], order_by="posting_datetime desc", limit=500)
    cols = [
        {"label":"Datetime","fieldname":"posting_datetime","fieldtype":"Datetime","width":160},
        {"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Batch","fieldname":"batch_no","fieldtype":"Link","options":"Batch","width":120},
        {"label":"Selling Rate","fieldname":"selling_rate","fieldtype":"Currency","width":120},
        {"label":"Cost Rate","fieldname":"cost_rate","fieldtype":"Currency","width":120},
        {"label":"Loss","fieldname":"loss_amount","fieldtype":"Currency","width":120},
        {"label":"Invoice","fieldname":"sales_invoice","fieldtype":"Link","options":"Sales Invoice","width":160}
    ]
    return cols, data
