frappe.query_reports["Pharma Slow Moving Stock"] = {
    filters: [
        {
            fieldname: "warehouse",
            label: "Warehouse",
            fieldtype: "Link",
            options: "Warehouse"
        },
        {
            fieldname: "days",
            label: "No Sale Since Days",
            fieldtype: "Int",
            default: 90
        }
    ]
};
