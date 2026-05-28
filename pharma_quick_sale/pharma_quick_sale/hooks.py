app_name = "pharma_quick_sale"
app_title = "Pharma Quick Sale"
app_publisher = "Your Company"
app_description = "Production-ready pharma quick sale, price lookup, FEFO, barcode, expiry dashboard, and fast GRN app for ERPNext v14"
app_email = "support@example.com"
app_license = "MIT"


fixtures = ["Custom Field", "Role"]

doc_events = {
    "Sales Invoice": {
        "validate": "pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.copy_pharma_fields_to_sales_invoice",
        "on_submit": "pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.consume_reservations_for_sales_invoice",
        "on_cancel": "pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.release_reservations_for_sales_invoice"
    },
    "Sales Order": {
        "on_cancel": "pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.release_reservations_for_sales_order"
    }
}


try:
    app_include_js
except NameError:
    app_include_js = []
app_include_js.append("/assets/pharma_quick_sale/js/pharma_fast_billing_v24.js")

app_include_js = app_include_js if "app_include_js" in globals() else []
app_include_js.append("/assets/pharma_quick_sale/js/pharma_fast_billing_v24_1.js")

app_include_css = app_include_css if "app_include_css" in globals() else []
app_include_css.append("/assets/pharma_quick_sale/css/pharma_fast_billing_v24_1.css")

app_include_css = app_include_css if "app_include_css" in globals() else []
app_include_css.append("/assets/pharma_quick_sale/css/pharma_operator_billing_v24_2.css")

app_include_js = app_include_js if "app_include_js" in globals() else []
app_include_js.append("/assets/pharma_quick_sale/js/pharma_operator_intelligence_v27.js")

app_include_css = app_include_css if "app_include_css" in globals() else []
app_include_css.append("/assets/pharma_quick_sale/css/pharma_operator_intelligence_v27.css")

app_include_js = app_include_js if "app_include_js" in globals() else []
app_include_js.append("/assets/pharma_quick_sale/js/pharma_advanced_scheme_v28.js")

app_include_css = app_include_css if "app_include_css" in globals() else []
app_include_css.append("/assets/pharma_quick_sale/css/pharma_advanced_scheme_v28.css")

scheduler_events = {
    "daily": [
        "pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.scheduled_update_customer_product_stats"
    ]
}

app_include_js = app_include_js if "app_include_js" in globals() else []
app_include_js.append("/assets/pharma_quick_sale/js/pharma_fast_operator_v29.js")

app_include_css = app_include_css if "app_include_css" in globals() else []
app_include_css.append("/assets/pharma_quick_sale/css/pharma_fast_operator_v29.css")

app_include_css = app_include_css if "app_include_css" in globals() else []
app_include_css.append("/assets/pharma_quick_sale/css/pharma_billing_global_v30.css")


# v31.3 GA scheduler
scheduler_events = scheduler_events if "scheduler_events" in globals() else {}
scheduler_events.setdefault("daily", [])
if "pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.expire_loss_sale_approvals_v31_3" not in scheduler_events["daily"]:
    scheduler_events["daily"].append("pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.expire_loss_sale_approvals_v31_3")
