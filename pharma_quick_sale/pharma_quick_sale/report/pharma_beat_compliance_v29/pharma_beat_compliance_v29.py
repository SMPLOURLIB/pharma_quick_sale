from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_beat_compliance_v29
def execute(filters=None):
    filters=filters or {}
    row=get_beat_compliance_v29(filters.get("sales_person"), filters.get("from_date"), filters.get("to_date"))
    cols=[{"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":180},{"label":"Planned","fieldname":"planned","fieldtype":"Int","width":100},{"label":"Completed","fieldname":"completed","fieldtype":"Int","width":100},{"label":"Missed","fieldname":"missed","fieldtype":"Int","width":100},{"label":"Compliance %","fieldname":"compliance_percent","fieldtype":"Percent","width":120}]
    return cols,[row]
