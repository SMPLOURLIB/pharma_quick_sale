from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_sample_utilization
def execute(filters=None):
    filters=filters or {}
    data=get_sample_utilization(filters.get("sales_person"), filters.get("from_date"), filters.get("to_date"))
    cols=[
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":180},
        {"label":"Issued","fieldname":"issued_qty","fieldtype":"Float","width":100},
        {"label":"Distributed","fieldname":"distributed_qty","fieldtype":"Float","width":120},
        {"label":"Returned","fieldname":"returned_qty","fieldtype":"Float","width":100},
        {"label":"Efficiency %","fieldname":"efficiency_percent","fieldtype":"Percent","width":120}
    ]
    return cols,data
