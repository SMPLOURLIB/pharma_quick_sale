frappe.query_reports["Pharma GST Stock Validation"] = {
    filters: [
        {fieldname:"sales_invoice", label:"Sales Invoice", fieldtype:"Link", options:"Sales Invoice", reqd:1}
    ]
};
