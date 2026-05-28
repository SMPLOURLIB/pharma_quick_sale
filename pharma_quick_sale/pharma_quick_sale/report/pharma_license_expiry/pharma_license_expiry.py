from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_license_expiry_dashboard

def execute(filters=None):
    filters=filters or {}
    rows=get_license_expiry_dashboard(days=filters.get("days") or 90)
    columns=[{"label":"Party Type","fieldname":"party_type","fieldtype":"Data","width":110},{"label":"Party","fieldname":"name","fieldtype":"Dynamic Link","options":"party_type","width":180},{"label":"License No","fieldname":"license_no","fieldtype":"Data","width":150},{"label":"Expiry Date","fieldname":"expiry_date","fieldtype":"Date","width":120},{"label":"Days","fieldname":"days_to_expiry","fieldtype":"Int","width":80}]
    return columns,rows
