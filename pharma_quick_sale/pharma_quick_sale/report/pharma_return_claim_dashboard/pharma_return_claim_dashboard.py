from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_return_claim_dashboard

def execute(filters=None):
    filters = filters or {}
    dashboard = get_return_claim_dashboard(days=filters.get("days") or 90)

    columns = [
        {"label": "Section", "fieldname": "section", "fieldtype": "Data", "width": 120},
        {"label": "Type", "fieldname": "type", "fieldtype": "Data", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 160},
        {"label": "Count", "fieldname": "count", "fieldtype": "Int", "width": 100},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 140}
    ]

    data = []
    for row in dashboard.get("returns", []):
        data.append({
            "section": "Returns",
            "type": row.get("return_type"),
            "status": row.get("status"),
            "count": row.get("count"),
            "amount": 0
        })

    for row in dashboard.get("claims", []):
        data.append({
            "section": "Claims",
            "type": row.get("claim_type"),
            "status": row.get("status"),
            "count": row.get("count"),
            "amount": row.get("amount")
        })

    return columns, data
