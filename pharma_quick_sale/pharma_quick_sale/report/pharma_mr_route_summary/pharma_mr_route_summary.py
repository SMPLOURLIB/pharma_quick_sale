from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_mr_route_summary
def execute(filters=None):
    filters = filters or {}
    rows = get_mr_route_summary(filters.get("sales_person"), filters.get("from_date"), filters.get("to_date"))
    columns = [
        {"label":"Route","fieldname":"name","fieldtype":"Link","options":"Pharma MR Route Plan","width":180},
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":180},
        {"label":"Date","fieldname":"route_date","fieldtype":"Date","width":120},
        {"label":"Territory","fieldname":"territory","fieldtype":"Link","options":"Territory","width":160},
        {"label":"Status","fieldname":"status","fieldtype":"Data","width":120}
    ]
    return columns, rows
