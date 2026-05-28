import frappe
def execute(filters=None):
    columns = [
        {"label":"Scorecard","fieldname":"name","fieldtype":"Link","options":"Pharma Monthly Scorecard","width":170},
        {"label":"Sales Person","fieldname":"sales_person","fieldtype":"Link","options":"Sales Person","width":170},
        {"label":"Month","fieldname":"month","fieldtype":"Int","width":80},
        {"label":"Year","fieldname":"year","fieldtype":"Int","width":80},
        {"label":"Weighted Score","fieldname":"weighted_score","fieldtype":"Float","width":130},
        {"label":"Incentive %","fieldname":"incentive_percentage","fieldtype":"Percent","width":120},
        {"label":"Incentive Amount","fieldname":"incentive_amount","fieldtype":"Currency","width":140}
    ]
    return columns, frappe.get_all("Pharma Monthly Scorecard", fields=["name","sales_person","month","year","weighted_score","incentive_percentage","incentive_amount"], order_by="year desc, month desc, weighted_score desc")
