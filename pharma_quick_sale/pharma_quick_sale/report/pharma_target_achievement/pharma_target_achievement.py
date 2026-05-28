from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import calculate_sfa_target_achievement

def execute(filters=None):
    filters = filters or {}
    data = calculate_sfa_target_achievement(filters.get("sales_person"), filters.get("from_date"), filters.get("to_date"))
    columns = [
        {"label":"Target","fieldname":"target","fieldtype":"Link","options":"Pharma Sales Target","width":170},
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":170},
        {"label":"Type","fieldname":"target_type","fieldtype":"Data","width":140},
        {"label":"Product","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Target Qty","fieldname":"target_qty","fieldtype":"Float","width":110},
        {"label":"Achieved Qty","fieldname":"achieved_qty","fieldtype":"Float","width":120},
        {"label":"Target Amount","fieldname":"target_amount","fieldtype":"Currency","width":130},
        {"label":"Achieved Amount","fieldname":"achieved_amount","fieldtype":"Currency","width":140},
        {"label":"Achievement %","fieldname":"achievement_percent","fieldtype":"Percent","width":130}
    ]
    return columns, data
