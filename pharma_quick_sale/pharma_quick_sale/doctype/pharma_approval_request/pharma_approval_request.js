frappe.ui.form.on('Pharma Approval Request', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status === 'Pending') {
            frm.add_custom_button(__('Approve'), () => {
                frappe.prompt([{fieldname:'notes', label:'Notes', fieldtype:'Small Text'}], (v) => {
                    frappe.call({
                        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.approve_pharma_request',
                        args:{approval_request: frm.doc.name, notes: v.notes},
                        callback(){ frm.reload_doc(); }
                    });
                });
            });

            frm.add_custom_button(__('Reject'), () => {
                frappe.prompt([{fieldname:'notes', label:'Notes', fieldtype:'Small Text', reqd:1}], (v) => {
                    frappe.call({
                        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.reject_pharma_request',
                        args:{approval_request: frm.doc.name, notes: v.notes},
                        callback(){ frm.reload_doc(); }
                    });
                });
            });
        }
    }
});
