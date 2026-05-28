frappe.ui.form.on('Pharma Sample Issue', {
    refresh(frm) {
        if (!frm.is_new() && !frm.doc.stock_entry) {
            frm.add_custom_button(__('Create Sample Stock Entry'), () => {
                frappe.call({
                    method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_sample_stock_entry',
                    args:{pharma_sample_issue: frm.doc.name},
                    callback(r){ if (r.message) frappe.set_route('Form', 'Stock Entry', r.message); }
                });
            });
        }
    }
});
