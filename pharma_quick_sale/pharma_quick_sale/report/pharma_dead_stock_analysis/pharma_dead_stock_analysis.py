from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_dead_stock_analysis
def execute(filters=None):
    filters=filters or {}
    data=get_dead_stock_analysis(filters.get("days") or 90, filters.get("warehouse"))
    cols=[{"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},{"label":"Item Name","fieldname":"item_name","fieldtype":"Data","width":220},{"label":"Warehouse","fieldname":"warehouse","fieldtype":"Link","options":"Warehouse","width":180},{"label":"Qty","fieldname":"actual_qty","fieldtype":"Float","width":100},{"label":"Last Sale","fieldname":"last_sale_date","fieldtype":"Date","width":120}]
    return cols,data
