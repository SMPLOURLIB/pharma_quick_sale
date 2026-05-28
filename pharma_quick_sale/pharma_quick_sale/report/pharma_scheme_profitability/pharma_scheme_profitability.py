from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import get_scheme_profitability
import frappe

def execute(filters=None):
    filters = filters or {}
    schemes = [filters.get("scheme")] if filters.get("scheme") else [x.name for x in frappe.get_all("Pharma Advanced Scheme", fields=["name"])]
    data = [get_scheme_profitability(s, filters.get("from_date"), filters.get("to_date")) for s in schemes]
    cols = [
        {"label":"Scheme","fieldname":"scheme","fieldtype":"Link","options":"Pharma Advanced Scheme","width":220},
        {"label":"Applications","fieldname":"applications","fieldtype":"Int","width":110},
        {"label":"Scheme Cost","fieldname":"scheme_cost","fieldtype":"Currency","width":130},
        {"label":"Revenue","fieldname":"revenue","fieldtype":"Currency","width":130},
        {"label":"Cost %","fieldname":"scheme_cost_percent","fieldtype":"Percent","width":110}
    ]
    return cols, data
