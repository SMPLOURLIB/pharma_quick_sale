frappe.query_reports["Pharma Returns Claims UAT Helper"] = {
    filters: [
        {fieldname:"original_sales_invoice", label:"Original Sales Invoice", fieldtype:"Link", options:"Sales Invoice"},
        {fieldname:"pharma_supplier_claim", label:"Supplier Claim", fieldtype:"Link", options:"Pharma Supplier Claim"},
        {fieldname:"target_warehouse", label:"Target Warehouse", fieldtype:"Link", options:"Warehouse"},
        {fieldname:"replacement_batches", label:"Replacement Batches JSON", fieldtype:"Code"}
    ]
};
