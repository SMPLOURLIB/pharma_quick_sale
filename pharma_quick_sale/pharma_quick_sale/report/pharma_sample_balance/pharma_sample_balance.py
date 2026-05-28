from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_sample_balance
def execute(filters=None):
    filters=filters or {}
    rows=get_sample_balance(filters.get("sales_person"), filters.get("item_code"))
    columns=[
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":170},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Batch","fieldname":"batch_no","fieldtype":"Link","options":"Batch","width":140},
        {"label":"Expiry","fieldname":"expiry_date","fieldtype":"Date","width":110},
        {"label":"Balance Qty","fieldname":"balance_qty","fieldtype":"Float","width":120}
    ]
    return columns, rows
