frappe.ui.form.on('Pharma Supplier Claim', {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Settle Claim'), () => {
                const d = new frappe.ui.Dialog({
                    title: 'Settle Supplier Claim',
                    fields: [
                        {fieldname: 'settlement_type', label: 'Settlement Type', fieldtype: 'Select', options: 'Credit Note\nReplacement\nRejected\nWrite Off', default: 'Credit Note', reqd: 1},
                        {fieldname: 'supplier_credit_note', label: 'Supplier Credit Note Ref', fieldtype: 'Data'},
                        {fieldname: 'notes', label: 'Notes', fieldtype: 'Small Text'}
                    ],
                    primary_action_label: 'Settle',
                    primary_action(values) {
                        if (values.settlement_type === 'Credit Note' && !values.supplier_credit_note) {
                            frappe.msgprint('Supplier Credit Note Ref is required for Credit Note settlement.');
                            return;
                        }

                        frappe.call({
                            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.settle_supplier_claim',
                            args: {
                                pharma_supplier_claim: frm.doc.name,
                                settlement_type: values.settlement_type,
                                supplier_credit_note: values.supplier_credit_note,
                                notes: values.notes
                            },
                            callback() {
                                d.hide();
                                frm.reload_doc();
                            }
                        });
                    }
                });

                const toggle_fields = () => {
                    const settlement_type = d.get_value('settlement_type');
                    const show_cn = settlement_type === 'Credit Note';
                    d.fields_dict.supplier_credit_note.$wrapper.toggle(show_cn);
                };

                d.fields_dict.settlement_type.df.onchange = toggle_fields;
                d.show();
                toggle_fields();
            });

            frm.add_custom_button(__('Create Replacement PR'), () => {
                frappe.prompt([
                    {fieldname: 'target_warehouse', label: 'Target Warehouse', fieldtype: 'Link', options: 'Warehouse', reqd: 1},
                    {fieldname: 'replacement_batches', label: 'Replacement Batches JSON Required: {"ITEM":{"batch_no":"NEW","expiry_date":"2027-12-31"}}', fieldtype: 'Code', reqd: 1}
                ], (values) => {
                    frappe.call({
                        method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.preflight_replacement_purchase_receipt',
                        args: {
                            pharma_supplier_claim: frm.doc.name,
                            target_warehouse: values.target_warehouse,
                            replacement_batches: values.replacement_batches,
                            require_new_batch: 1
                        },
                        callback(preflight) {
                            const pf = preflight.message || {};
                            if (!pf.valid) {
                                frappe.msgprint((pf.errors || []).join('<br>'));
                                return;
                            }

                            frappe.call({
                                method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_replacement_purchase_receipt',
                                args: {
                                    pharma_supplier_claim: frm.doc.name,
                                    target_warehouse: values.target_warehouse,
                                    replacement_batches: values.replacement_batches,
                                    require_new_batch: 1
                                },
                                callback(r) {
                                    if (r.message && r.message.purchase_receipt) {
                                        frappe.set_route('Form', 'Purchase Receipt', r.message.purchase_receipt);
                                    }
                                }
                            });
                        }
                    });
                });
            });
        }
    }
});
