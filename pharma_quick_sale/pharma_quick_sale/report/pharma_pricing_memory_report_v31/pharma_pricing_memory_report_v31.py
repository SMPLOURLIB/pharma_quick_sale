import frappe
def execute(filters=None):
    data = frappe.get_all("Pharma Pricing Memory", fields=["customer","item_code","last_rate","last_discount_percentage","last_margin_percent","last_sale_date","last_invoice","avg_rate_90d","avg_discount_90d","typical_qty"], order_by="last_updated desc", limit=1000)
    cols = [
        {"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Last Rate","fieldname":"last_rate","fieldtype":"Currency","width":100},
        {"label":"Last Disc %","fieldname":"last_discount_percentage","fieldtype":"Percent","width":110},
        {"label":"Last Margin %","fieldname":"last_margin_percent","fieldtype":"Percent","width":120},
        {"label":"Last Sale","fieldname":"last_sale_date","fieldtype":"Date","width":110},
        {"label":"Last Invoice","fieldname":"last_invoice","fieldtype":"Link","options":"Sales Invoice","width":160},
        {"label":"Avg Rate 90D","fieldname":"avg_rate_90d","fieldtype":"Currency","width":120},
        {"label":"Avg Disc 90D","fieldname":"avg_discount_90d","fieldtype":"Percent","width":120},
        {"label":"Typical Qty","fieldname":"typical_qty","fieldtype":"Float","width":100}
    ]
    return cols, data
