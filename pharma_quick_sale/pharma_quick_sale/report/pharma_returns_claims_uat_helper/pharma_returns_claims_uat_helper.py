from pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale import run_returns_claims_uat_checks

def execute(filters=None):
    filters = filters or {}
    result = run_returns_claims_uat_checks(
        original_sales_invoice=filters.get("original_sales_invoice"),
        pharma_supplier_claim=filters.get("pharma_supplier_claim"),
        replacement_batches=filters.get("replacement_batches"),
        target_warehouse=filters.get("target_warehouse")
    )

    columns = [
        {"label": "Check", "fieldname": "check", "fieldtype": "Data", "width": 220},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": "Details", "fieldname": "details", "fieldtype": "Data", "width": 500}
    ]

    data = []

    sim = result.get("return_credit_note_simulation")
    if sim:
        data.append({
            "check": "Return Credit Note GST/Tax Simulation",
            "status": "OK" if sim.get("ready") else "FAIL",
            "details": f"Return Grand Total: {sim.get('simulated_return_grand_total')} | Taxes: {len(sim.get('taxes') or [])}"
        })

    pf = result.get("replacement_pr_preflight")
    if pf:
        data.append({
            "check": "Replacement PR Batch Preflight",
            "status": "OK" if pf.get("valid") else "FAIL",
            "details": "; ".join(pf.get("errors") or pf.get("warnings") or ["No issues"])
        })

    return columns, data
