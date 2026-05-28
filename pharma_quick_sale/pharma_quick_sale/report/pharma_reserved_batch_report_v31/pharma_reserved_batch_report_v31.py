from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_reserved_batch_report_v31

def execute(filters=None):
    filters = filters or {}
    data = get_reserved_batch_report_v31(filters.get("customer"), filters.get("item_code"), filters.get("warehouse"))
    cols = [
        {"label":"Reservation","fieldname":"name","fieldtype":"Link","options":"Pharma Batch Reservation","width":180},
        {"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Warehouse","fieldname":"warehouse","fieldtype":"Link","options":"Warehouse","width":180},
        {"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":150},
        {"label":"Batch","fieldname":"batch_no","fieldtype":"Link","options":"Batch","width":130},
        {"label":"Reserved","fieldname":"reserved_qty","fieldtype":"Float","width":100},
        {"label":"Consumed","fieldname":"consumed_qty","fieldtype":"Float","width":100},
        {"label":"Released","fieldname":"released_qty","fieldtype":"Float","width":100},
        {"label":"Available","fieldname":"available_reserved_qty","fieldtype":"Float","width":100},
        {"label":"Status","fieldname":"status","fieldtype":"Data","width":110}
    ]
    return cols, data
