import frappe

def execute(filters=None):
    filters = filters or {}
    warehouse = filters.get("warehouse")
    days = int(filters.get("days") or 90)

    conditions = ["b.actual_qty > 0"]
    values = []

    if warehouse:
        conditions.append("b.warehouse = %s")
        values.append(warehouse)

    values.append(days)

    columns = [
        {"label": "Item", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 220},
        {"label": "Warehouse", "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
        {"label": "Stock Qty", "fieldname": "actual_qty", "fieldtype": "Float", "width": 100},
        {"label": "Last Sale Date", "fieldname": "last_sale_date", "fieldtype": "Date", "width": 120},
        {"label": "Days Since Sale", "fieldname": "days_since_sale", "fieldtype": "Int", "width": 120},
        {"label": "Stock Value", "fieldname": "stock_value", "fieldtype": "Currency", "width": 120}
    ]

    data = frappe.db.sql(f"""
        SELECT
            b.item_code,
            i.item_name,
            b.warehouse,
            b.actual_qty,
            b.stock_value,
            MAX(si.posting_date) AS last_sale_date,
            DATEDIFF(CURDATE(), MAX(si.posting_date)) AS days_since_sale
        FROM `tabBin` b
        INNER JOIN `tabItem` i ON i.name = b.item_code
        LEFT JOIN `tabSales Invoice Item` sii ON sii.item_code = b.item_code
        LEFT JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
        WHERE {' AND '.join(conditions)}
        GROUP BY b.item_code, i.item_name, b.warehouse, b.actual_qty, b.stock_value
        HAVING last_sale_date IS NULL OR days_since_sale >= %s
        ORDER BY days_since_sale DESC, b.actual_qty DESC
    """, tuple(values), as_dict=True)

    return columns, data
