from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_beat_compliance
def execute(filters=None):
    filters=filters or {}
    row=get_beat_compliance(filters.get("sales_person"),filters.get("from_date"),filters.get("to_date"))
    columns=[
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":170},
        {"label":"Planned","fieldname":"planned_visits","fieldtype":"Int","width":100},
        {"label":"Actual","fieldname":"actual_visits","fieldtype":"Int","width":100},
        {"label":"Compliance %","fieldname":"compliance_percent","fieldtype":"Percent","width":130}
    ]
    return columns,[row]
