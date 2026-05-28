from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_doctor_coverage_dashboard

def execute(filters=None):
    filters = filters or {}
    d = get_doctor_coverage_dashboard(filters.get("sales_person"), filters.get("from_date"), filters.get("to_date"))
    columns = [
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":180},
        {"label":"Total Doctors","fieldname":"total_doctors","fieldtype":"Int","width":120},
        {"label":"Visited Doctors","fieldname":"visited_doctors","fieldtype":"Int","width":130},
        {"label":"Coverage %","fieldname":"coverage_percent","fieldtype":"Percent","width":120}
    ]
    return columns, [d]
