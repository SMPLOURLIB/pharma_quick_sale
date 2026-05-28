frappe.ui.form.on('Pharma Tour Plan', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Create DCR'), () => {
                frappe.prompt([
                    {fieldname:'doctor', label:'Doctor', fieldtype:'Link', options:'Pharma Doctor'},
                    {fieldname:'visit_date', label:'Visit Date', fieldtype:'Date'}
                ], (v) => {
                    frappe.call({
                        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_dcr_from_tour_plan',
                        args:{tour_plan: frm.doc.name, doctor: v.doctor, visit_date: v.visit_date},
                        callback(r){ if (r.message) frappe.set_route('Form', 'Pharma DCR', r.message); }
                    });
                });
            });

            if (frm.doc.status !== 'Approved') {
                frm.add_custom_button(__('Approve Plan'), () => {
                    frappe.call({
                        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.approve_tour_plan',
                        args:{pharma_tour_plan: frm.doc.name, approve: 1},
                        callback(){ frm.reload_doc(); }
                    });
                });
            }
        }
    }
});
