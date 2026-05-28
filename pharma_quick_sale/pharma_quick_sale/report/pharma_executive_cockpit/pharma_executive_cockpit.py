from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_executive_cockpit

def execute(filters=None):
    filters = filters or {}
    c = get_executive_cockpit(filters.get("from_date"), filters.get("to_date"))
    columns = [
        {"label":"Metric","fieldname":"metric","fieldtype":"Data","width":220},
        {"label":"Value","fieldname":"value","fieldtype":"Data","width":300}
    ]
    gap = c.get("primary_secondary_gap") or {}
    data = [
        {"metric":"Primary Sales","value":gap.get("primary_sales")},
        {"metric":"Secondary Sales","value":gap.get("secondary_sales")},
        {"metric":"Gap","value":gap.get("gap")},
        {"metric":"Secondary Liquidation %","value":gap.get("secondary_liquidation_percent")}
    ]
    return columns, data
