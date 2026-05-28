import frappe

def execute(filters=None):
    filters = filters or {}
    conditions = []
    values = []
    if filters.get("distributor"):
        conditions.append("ss.distributor = %s")
        values.append(filters.get("distributor"))
    if filters.get("sales_person"):
        conditions.append("ss.sales_person = %s")
        values.append(filters.get("sales_person"))
    where = " AND " + " AND ".join(conditions) if conditions else ""
    data = frappe.db.sql(f'''
        SELECT ss.name, ss.distributor, ss.sales_person, ss.period_from, ss.period_to, ssi.item_code, ssi.qty, ssi.amount
        FROM `tabPharma Secondary Sales Item` ssi
        INNER JOIN `tabPharma Secondary Sales` ss ON ss.name = ssi.parent
        WHERE ss.docstatus < 2 {where}
        ORDER BY ss.period_to DESC
    ''', tuple(values), as_dict=True)
    columns = [
        {"label":"Secondary Sale","fieldname":"name","fieldtype":"Link","options":"Pharma Secondary Sales","width":170},
        {"label":"Distributor","fieldname":"distributor","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":160},
        {"label":"Product","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Qty","fieldname":"qty","fieldtype":"Float","width":100},
        {"label":"Amount","fieldname":"amount","fieldtype":"Currency","width":120}
    ]
    return columns, data
