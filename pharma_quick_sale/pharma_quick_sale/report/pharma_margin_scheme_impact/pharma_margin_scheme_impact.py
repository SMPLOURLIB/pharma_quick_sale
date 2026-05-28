from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_margin_scheme_impact

def execute(filters=None):
    filters = filters or {}
    rows = get_margin_scheme_impact(filters.get("from_date"), filters.get("to_date"))

    columns = [
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 220},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 100},
        {"label": "Net Sales", "fieldname": "net_sales", "fieldtype": "Currency", "width": 120},
        {"label": "Discount Amount", "fieldname": "discount_amount", "fieldtype": "Currency", "width": 140},
        {"label": "Gross Margin", "fieldname": "gross_margin", "fieldtype": "Currency", "width": 130}
    ]
    return columns, rows
