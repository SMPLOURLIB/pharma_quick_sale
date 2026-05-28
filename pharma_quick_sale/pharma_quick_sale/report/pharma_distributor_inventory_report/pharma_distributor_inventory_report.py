import frappe
def execute(filters=None):
    filters=filters or {}
    cond=[]; vals=[]
    if filters.get("distributor"):
        cond.append("di.distributor=%s"); vals.append(filters.get("distributor"))
    where="WHERE "+" AND ".join(cond) if cond else ""
    data=frappe.db.sql(f'''SELECT di.name,di.posting_date,di.distributor,di.territory,dii.item_code,dii.batch_no,dii.primary_qty,dii.secondary_qty,dii.closing_qty FROM `tabPharma Distributor Inventory Item` dii INNER JOIN `tabPharma Distributor Inventory` di ON di.name=dii.parent {where} ORDER BY di.posting_date DESC''', tuple(vals), as_dict=True)
    cols=[{"label":"Distributor","fieldname":"distributor","fieldtype":"Link","options":"Customer","width":180},{"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},{"label":"Batch","fieldname":"batch_no","fieldtype":"Link","options":"Batch","width":130},{"label":"Primary","fieldname":"primary_qty","fieldtype":"Float","width":100},{"label":"Secondary","fieldname":"secondary_qty","fieldtype":"Float","width":100},{"label":"Closing","fieldname":"closing_qty","fieldtype":"Float","width":100}]
    return cols,data
