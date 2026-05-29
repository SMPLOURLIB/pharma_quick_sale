frappe.ui.form.on('Pharma DCR', {
    refresh(frm) {
        if (!frm.is_new()) {
            if (frm.doc.status !== 'Submitted' && frm.doc.status !== 'Approved') {
                frm.add_custom_button(__('Submit DCR'), () => {
                    frappe.call({
                        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.submit_dcr_with_audit',
                        args:{pharma_dcr: frm.doc.name},
                        callback(){ frm.reload_doc(); }
                    });
                });
            }
            if (frm.doc.status !== 'Approved') {
                frm.add_custom_button(__('Approve DCR'), () => {
                    frappe.call({
                        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.approve_dcr',
                        args:{pharma_dcr: frm.doc.name, approve: 1},
                        callback(){ frm.reload_doc(); }
                    });
                });
            }
        }
    }
});
