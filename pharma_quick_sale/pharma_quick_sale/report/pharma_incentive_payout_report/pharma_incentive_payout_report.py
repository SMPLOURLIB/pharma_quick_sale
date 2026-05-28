import frappe
def execute(filters=None):
    filters=filters or {}
    data=frappe.get_all("Pharma Incentive Payout", fields=["name","sales_person","distributor","rule","achievement_percent","incentive_amount","status"], order_by="modified desc")
    cols=[{"label":"Payout","fieldname":"name","fieldtype":"Link","options":"Pharma Incentive Payout","width":180},{"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":180},{"label":"Distributor","fieldname":"distributor","fieldtype":"Link","options":"Customer","width":180},{"label":"Rule","fieldname":"rule","fieldtype":"Link","options":"Pharma Incentive Rule","width":180},{"label":"Achievement %","fieldname":"achievement_percent","fieldtype":"Percent","width":120},{"label":"Incentive","fieldname":"incentive_amount","fieldtype":"Currency","width":120},{"label":"Status","fieldname":"status","fieldtype":"Data","width":100}]
    return cols,data
