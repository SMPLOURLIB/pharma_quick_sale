import frappe

def execute(filters=None):
    filters=filters or {}
    conditions={}
    if filters.get("owner_user"): conditions["owner_user"]=filters.get("owner_user")
    if filters.get("status"): conditions["status"]=filters.get("status")
    columns=[{"label":"Held Invoice","fieldname":"name","fieldtype":"Link","options":"Pharma Held Invoice","width":180},{"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},{"label":"User","fieldname":"owner_user","fieldtype":"Link","options":"User","width":160},{"label":"Held Datetime","fieldname":"held_datetime","fieldtype":"Datetime","width":160},{"label":"Status","fieldname":"status","fieldtype":"Data","width":100},{"label":"Grand Total","fieldname":"grand_total","fieldtype":"Currency","width":120}]
    data=frappe.get_all("Pharma Held Invoice",filters=conditions,fields=["name","customer","owner_user","held_datetime","status","grand_total"],order_by="held_datetime desc")
    return columns,data
