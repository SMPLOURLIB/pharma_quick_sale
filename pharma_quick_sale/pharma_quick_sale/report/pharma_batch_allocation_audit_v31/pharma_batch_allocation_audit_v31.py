import frappe

def execute(filters=None):
    data = frappe.get_all("Pharma Batch Allocation Audit", fields=["posting_datetime","customer","warehouse","item_code","requested_qty","allocated_qty","shortage_qty","allocation_policy","status"], order_by="posting_datetime desc", limit=500)
    cols = [
        {"label":"Datetime","fieldname":"posting_datetime","fieldtype":"Datetime","width":160},
        {"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Warehouse","fieldname":"warehouse","fieldtype":"Link","options":"Warehouse","width":180},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Requested","fieldname":"requested_qty","fieldtype":"Float","width":100},
        {"label":"Allocated","fieldname":"allocated_qty","fieldtype":"Float","width":100},
        {"label":"Shortage","fieldname":"shortage_qty","fieldtype":"Float","width":100},
        {"label":"Policy","fieldname":"allocation_policy","fieldtype":"Data","width":120},
        {"label":"Status","fieldname":"status","fieldtype":"Data","width":100}
    ]
    return cols, data
