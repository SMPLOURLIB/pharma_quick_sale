import frappe
def execute(filters=None):
    columns = [
        {"label":"Scheme","fieldname":"scheme_name","fieldtype":"Data","width":180},
        {"label":"Supplier","fieldname":"supplier","fieldtype":"Link","options":"Supplier","width":180},
        {"label":"Type","fieldname":"scheme_type","fieldtype":"Data","width":120},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Min Qty","fieldname":"min_qty","fieldtype":"Float","width":100},
        {"label":"Free Qty","fieldname":"free_qty","fieldtype":"Float","width":100},
        {"label":"Discount %","fieldname":"discount_percentage","fieldtype":"Percent","width":100}
    ]
    data = frappe.get_all("Pharma Purchase Scheme", fields=["scheme_name","supplier","scheme_type","item_code","min_qty","free_qty","discount_percentage"], order_by="modified desc")
    return columns, data
