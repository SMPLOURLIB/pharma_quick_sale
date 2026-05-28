frappe.query_reports["Pharma Audit Log Report"] = {
    filters: [
        {fieldname:"severity", label:"Severity", fieldtype:"Select", options:"\nInfo\nWarning\nCritical"},
        {fieldname:"action", label:"Action Contains", fieldtype:"Data"}
    ]
};
