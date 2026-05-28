frappe.ui.form.on('Pharma Return', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.docstatus === 1 && !frm.doc.supplier_claim) {
            frm.add_custom_button(__('Create Supplier Claim'), () => {
                frappe.prompt([
                    {fieldname: 'supplier', label: 'Supplier', fieldtype: 'Link', options: 'Supplier'}
                ], (values) => {
                    frappe.call({
                        method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_supplier_claim_from_return',
                        args: {
                            pharma_return: frm.doc.name,
                            supplier: values.supplier
                        },
                        callback(r) {
                            if (r.message) {
                                frappe.set_route('Form', 'Pharma Supplier Claim', r.message);
                            }
                        }
                    });
                });
            });
        }
    }
});
