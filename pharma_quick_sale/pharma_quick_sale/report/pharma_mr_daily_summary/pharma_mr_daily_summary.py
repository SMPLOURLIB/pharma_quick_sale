from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_mr_daily_summary

def execute(filters=None):
    filters = filters or {}
    data = get_mr_daily_summary(filters.get("sales_person"), filters.get("date"))
    columns = [
        {"label":"Date","fieldname":"date","fieldtype":"Date","width":120},
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":170},
        {"label":"DCR Count","fieldname":"dcr_count","fieldtype":"Int","width":110},
        {"label":"Samples Qty","fieldname":"samples_qty","fieldtype":"Float","width":120},
        {"label":"Order Value","fieldname":"order_value","fieldtype":"Currency","width":130}
    ]
    return columns, [data]
