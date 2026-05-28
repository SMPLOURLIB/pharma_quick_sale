from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import bulk_item_lookup

def execute(filters=None):
    filters=filters or {}
    items=bulk_item_lookup(warehouse=filters.get("warehouse"),limit=filters.get("limit") or 100)
    columns=[{"label":"Item","fieldname":"item_code","fieldtype":"Link","options":"Item","width":160},{"label":"Item Name","fieldname":"item_name","fieldtype":"Data","width":220},{"label":"Brand","fieldname":"brand","fieldtype":"Data","width":120},{"label":"Composition","fieldname":"composition","fieldtype":"Data","width":200},{"label":"Stock","fieldname":"actual_qty","fieldtype":"Float","width":100},{"label":"Rate","fieldname":"rate","fieldtype":"Currency","width":100},{"label":"MRP","fieldname":"mrp","fieldtype":"Currency","width":100}]
    return columns,items
