from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_profitability_summary
def execute(filters=None):
    filters=filters or {}
    group_by=filters.get("group_by") or "item_code"
    data=get_profitability_summary(filters.get("from_date"), filters.get("to_date"), group_by)
    cols=[{"label":"Group","fieldname":group_by,"fieldtype":"Data","width":200},{"label":"Sales","fieldname":"sales_amount","fieldtype":"Currency","width":130},{"label":"Cost","fieldname":"cost_amount","fieldtype":"Currency","width":130},{"label":"Discount","fieldname":"discount_amount","fieldtype":"Currency","width":130},{"label":"Net Profit","fieldname":"net_profit","fieldtype":"Currency","width":130},{"label":"Margin %","fieldname":"margin_percent","fieldtype":"Percent","width":120}]
    return cols,data
