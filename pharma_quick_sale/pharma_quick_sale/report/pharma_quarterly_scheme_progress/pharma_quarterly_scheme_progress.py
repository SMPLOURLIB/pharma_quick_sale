from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_quarterly_scheme_progress
import frappe

def execute(filters=None):
    filters = filters or {}
    schemes = [filters.get("scheme")] if filters.get("scheme") else [x.name for x in frappe.get_all("Pharma Advanced Scheme", filters={"scheme_type":"Quarterly Target"}, fields=["name"])]
    data = [get_quarterly_scheme_progress(s, filters.get("customer")) for s in schemes]
    cols = [
        {"label":"Scheme","fieldname":"scheme","fieldtype":"Link","options":"Pharma Advanced Scheme","width":220},
        {"label":"Customer","fieldname":"customer","fieldtype":"Link","options":"Customer","width":180},
        {"label":"Target Qty","fieldname":"target_qty","fieldtype":"Float","width":110},
        {"label":"Achieved Qty","fieldname":"achieved_qty","fieldtype":"Float","width":120},
        {"label":"Qty %","fieldname":"qty_percent","fieldtype":"Percent","width":100},
        {"label":"Target Amount","fieldname":"target_amount","fieldtype":"Currency","width":130},
        {"label":"Achieved Amount","fieldname":"achieved_amount","fieldtype":"Currency","width":140},
        {"label":"Amount %","fieldname":"amount_percent","fieldtype":"Percent","width":100}
    ]
    return cols, data
