import frappe

def execute(filters=None):
    columns=[{"label":"Claim","fieldname":"name","fieldtype":"Link","options":"Pharma Supplier Claim","width":160},{"label":"Supplier","fieldname":"supplier","fieldtype":"Link","options":"Supplier","width":180},{"label":"Type","fieldname":"claim_type","fieldtype":"Data","width":130},{"label":"Status","fieldname":"status","fieldtype":"Data","width":130},{"label":"Claim Amount","fieldname":"claim_amount","fieldtype":"Currency","width":130},{"label":"Posting Date","fieldname":"posting_date","fieldtype":"Date","width":120}]
    data=frappe.get_all("Pharma Supplier Claim", fields=["name","supplier","claim_type","status","claim_amount","posting_date"], order_by="posting_date desc")
    return columns,data
