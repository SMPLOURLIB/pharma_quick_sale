
frappe.pages['pharma-operator-billing'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Pharma Operator Billing',
        single_column: true
    });

    $(frappe.render_template('pharma_operator_billing')).appendTo(page.body);

    const state = {
        items: [],
        customer: null,
        company: null,
        warehouse: null,
        price_list: 'Standard Selling'
    };

    const $root = $(page.body).find('.pob-root');
    const $search = $root.find('.pob-search');
    const $customer = $root.find('.pob-customer');
    const $company = $root.find('.pob-company');
    const $warehouse = $root.find('.pob-warehouse');
    const $tbody = $root.find('.pob-grid tbody');
    const $suggestions = $root.find('.pob-suggestions');

    function status(msg, indicator='blue') {
        $root.find('.pob-status').html(`<span class="indicator ${indicator}">${msg}</span>`);
    }

    function money(v) {
        return (Number(v || 0)).toFixed(2);
    }

    function collectPayload() {
        return {
            customer: state.customer || $customer.val(),
            company: state.company || $company.val(),
            warehouse: state.warehouse || $warehouse.val(),
            price_list: state.price_list,
            posting_date: frappe.datetime.get_today(),
            grand_total: calcTotals().grand_total,
            items: state.items.map(row => ({
                item_code: row.item_code,
                item_name: row.item_name,
                qty: Number(row.qty || 0),
                free_qty: Number(row.free_qty || 0),
                rate: Number(row.rate || 0),
                discount_percentage: Number(row.discount_percentage || 0),
                batch_rows: row.batch_rows || []
            })),
            batch_allocations: state.items.flatMap(row => (row.batch_rows || []).map(b => ({
                item_code: row.item_code,
                batch_no: b.batch_no,
                qty: b.qty,
                free_qty: 0
            })))
        };
    }

    function calcTotals() {
        let qty = 0, total = 0;
        state.items.forEach(row => {
            const line = Number(row.qty || 0) * Number(row.rate || 0) * (1 - Number(row.discount_percentage || 0) / 100);
            row.amount = line;
            qty += Number(row.qty || 0);
            total += line;
        });
        return {qty, grand_total: total};
    }

    function renderGrid(focusLast=false) {
        $tbody.empty();
        state.items.forEach((row, idx) => {
            const batch = (row.batch_rows || [])[0] || {};
            const tr = $(`<tr data-idx="${idx}">
                <td>${idx + 1}</td>
                <td><b>${row.item_code}</b><br><small>${row.item_name || ''}</small></td>
                <td>${batch.batch_no || ''}</td>
                <td>${batch.expiry_date || ''}</td>
                <td><input class="form-control input-xs pob-row-qty" value="${row.qty || 1}"></td>
                <td><input class="form-control input-xs pob-row-free" value="${row.free_qty || 0}"></td>
                <td><input class="form-control input-xs pob-row-rate" value="${row.rate || 0}"></td>
                <td><input class="form-control input-xs pob-row-disc" value="${row.discount_percentage || 0}"></td>
                <td>${row.item_tax_template || ''}</td>
                <td class="pob-row-amount">${money(row.amount)}</td>
                <td><button class="btn btn-xs btn-danger pob-row-del">×</button></td>
            </tr>`);
            $tbody.append(tr);
        });

        const totals = calcTotals();
        $root.find('.pob-line-count').text(state.items.length);
        $root.find('.pob-total-qty').text(totals.qty);
        $root.find('.pob-grand-total').text(money(totals.grand_total));
        window.__current_pharma_quick_sale_payload = collectPayload();

        if (focusLast) $tbody.find('tr:last .pob-row-qty').focus().select();
    }

    function addItem(item, qty=1, batches=[]) {
        const existing = state.items.find(x => x.item_code === item.item_code);
        if (existing) {
            existing.qty = Number(existing.qty || 0) + Number(qty || 1);
            renderGrid();
            $search.val('').focus();
            return;
        }

        state.items.push({
            item_code: item.item_code,
            item_name: item.item_name,
            qty: qty,
            free_qty: 0,
            rate: Number(item.rate || item.ptr || 0),
            discount_percentage: 0,
            item_tax_template: item.item_tax_template || '',
            has_batch_no: item.has_batch_no,
            batch_rows: batches || []
        });
        renderGrid();
        $search.val('').focus();
    }

    function renderSuggestions(rows) {
        if (!rows.length) {
            $suggestions.hide().empty();
            return;
        }
        const html = rows.map(x => `<div class="pob-suggestion" data-item="${x.item_code}">
            <b>${x.item_code}</b> ${x.item_name || ''}<br>
            <small>${x.composition || ''} | Stock ${x.actual_qty || 0} | Rate ${x.rate || x.ptr || 0}</small>
        </div>`).join('');
        $suggestions.html(html).show();
    }

    async function loadCache() {
        if (!window.PharmaFastBillingV241) {
            frappe.msgprint('v24.1 fast billing helper not loaded.');
            return;
        }
        state.warehouse = $warehouse.val();
        await window.PharmaFastBillingV241.bootstrapFromServer({warehouse: state.warehouse, price_list: state.price_list});
        status('Cache loaded', 'green');
        $search.focus();
    }

    async function scanOrSearch(value) {
        const txt = (value || '').trim();
        if (!txt) return;
        state.warehouse = $warehouse.val();

        let item = window.PharmaFastBillingV241 ? window.PharmaFastBillingV241.resolveBarcode(txt) : null;
        if (item) {
            const batches = window.PharmaFastBillingV241.localFEFO(item.item_code, state.warehouse, 1);
            addItem(item, 1, batches);
            status('Scanned: ' + item.item_code, 'green');
            return;
        }

        const rows = window.PharmaFastBillingV241 ? window.PharmaFastBillingV241.searchItems(txt, 8) : [];
        renderSuggestions(rows);
        if (rows.length === 1) {
            const batches = window.PharmaFastBillingV241.localFEFO(rows[0].item_code, state.warehouse, 1);
            addItem(rows[0], 1, batches);
        }
    }

    $root.find('.pob-load-cache').on('click', loadCache);

    $search.on('input', frappe.utils.debounce(() => {
        scanOrSearch($search.val());
    }, 120));

    $search.on('keydown', e => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const first = $suggestions.find('.pob-suggestion:first').data('item');
            if (first && window.PharmaFastBillingV241) {
                const item = window.PharmaFastBillingV241.memory.itemIndex[first];
                const batches = window.PharmaFastBillingV241.localFEFO(item.item_code, $warehouse.val(), 1);
                addItem(item, 1, batches);
                $suggestions.hide();
            } else {
                scanOrSearch($search.val());
            }
        }
    });

    $suggestions.on('click', '.pob-suggestion', function() {
        const code = $(this).data('item');
        const item = window.PharmaFastBillingV241.memory.itemIndex[code];
        const batches = window.PharmaFastBillingV241.localFEFO(item.item_code, $warehouse.val(), 1);
        addItem(item, 1, batches);
        $suggestions.hide();
    });

    $tbody.on('input', 'input', function() {
        const tr = $(this).closest('tr');
        const idx = Number(tr.data('idx'));
        const row = state.items[idx];
        row.qty = Number(tr.find('.pob-row-qty').val() || 0);
        row.free_qty = Number(tr.find('.pob-row-free').val() || 0);
        row.rate = Number(tr.find('.pob-row-rate').val() || 0);
        row.discount_percentage = Number(tr.find('.pob-row-disc').val() || 0);
        calcTotals();
        tr.find('.pob-row-amount').text(money(row.amount));
        const totals = calcTotals();
        $root.find('.pob-total-qty').text(totals.qty);
        $root.find('.pob-grand-total').text(money(totals.grand_total));
        window.__current_pharma_quick_sale_payload = collectPayload();
    });

    $tbody.on('click', '.pob-row-del', function() {
        const idx = Number($(this).closest('tr').data('idx'));
        state.items.splice(idx, 1);
        renderGrid();
    });

    $root.find('.pob-submit').on('click', () => {
        state.customer = $customer.val();
        state.company = $company.val();
        state.warehouse = $warehouse.val();
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.operator_submit_invoice',
            args: {data: collectPayload(), action: 'invoice'},
            freeze: true,
            freeze_message: 'Submitting invoice...',
            callback: r => {
                const d = r.message || {};
                status('Invoice submitted', 'green');
                if (d.sales_invoice) frappe.set_route('Form', 'Sales Invoice', d.sales_invoice);
            }
        });
    });

    $root.find('.pob-hold').on('click', () => {
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.operator_save_held_invoice',
            args: {data: collectPayload()},
            callback: r => status('Held bill saved: ' + r.message, 'green')
        });
    });

    function recallHeld() {
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.held_invoice_list',
            callback: r => {
                const rows = r.message || [];
                const html = `<table class="table table-bordered"><tr><th>Held</th><th>Customer</th><th>Total</th><th></th></tr>
                    ${rows.map(x => `<tr><td>${x.name}</td><td>${x.customer || ''}</td><td>${x.grand_total || 0}</td><td><button class="btn btn-xs btn-primary pob-recall-one" data-name="${x.name}">Recall</button></td></tr>`).join('')}</table>`;
                const d = new frappe.ui.Dialog({title: 'Recall Held Bill', fields: [{fieldname: 'html', fieldtype: 'HTML'}]});
                d.fields_dict.html.$wrapper.html(html);
                d.show();
                d.fields_dict.html.$wrapper.find('.pob-recall-one').on('click', ev => {
                    frappe.call({
                        method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.held_invoice_restore',
                        args: {held_invoice: $(ev.currentTarget).data('name')},
                        callback: rr => {
                            const p = rr.message || {};
                            $customer.val(p.customer || '');
                            $company.val(p.company || '');
                            $warehouse.val(p.warehouse || '');
                            state.items = (p.items || []).map(x => ({
                                item_code: x.item_code,
                                item_name: x.item_name,
                                qty: x.qty,
                                free_qty: x.free_qty,
                                rate: x.rate,
                                discount_percentage: x.discount_percentage,
                                batch_rows: x.batch_rows || []
                            }));
                            renderGrid();
                            d.hide();
                            status('Held bill recalled', 'green');
                        }
                    });
                });
            }
        });
    }

    $root.find('.pob-recall').on('click', recallHeld);

    window.PharmaOperatorBilling = {
        state, addItem, renderGrid, collectPayload, recallHeld,
        focusSearch: () => $search.focus(),
        focusCustomer: () => $customer.focus(),
        focusQty: () => $tbody.find('tr:last .pob-row-qty').focus().select(),
        focusRate: () => $tbody.find('tr:last .pob-row-rate').focus().select(),
        saveInvoice: () => $root.find('.pob-submit').click(),
        holdInvoice: () => $root.find('.pob-hold').click(),
        recallHeld
    };

    if (window.PharmaFastBillingV241) {
        window.PharmaFastBillingV241.bindHotkeys(window.PharmaOperatorBilling);
        window.PharmaFastBillingV241.loadMemory().then(() => status('Local cache ready', 'green')).catch(() => status('Load cache to begin', 'orange'));
    }

    status('Ready', 'green');
};


// v27.1 intelligence binding
(function() {
    function tryLoadOperatorIntelligenceFromRow($row) {
        if (!window.PharmaOperatorIntelligenceV27 || !$row || !$row.length) return;
        const itemText = $row.find('td:nth-child(2) b').first().text();
        if (!itemText) return;
        const customer = $('.pob-customer').val() || null;
        const warehouse = $('.pob-warehouse').val() || null;
        const qty = $row.find('.pob-row-qty').val() || 1;
        const rate = $row.find('.pob-row-rate').val() || 0;
        window.PharmaOperatorIntelligenceV27.loadPanel({
            item_code: itemText,
            customer: customer,
            warehouse: warehouse,
            qty: qty,
            rate: rate
        });
    }

    $(document).on('click', '.pob-grid tbody tr', function() {
        tryLoadOperatorIntelligenceFromRow($(this));
    });

    $(document).on('focus', '.pob-row-qty, .pob-row-rate, .pob-row-disc', function() {
        tryLoadOperatorIntelligenceFromRow($(this).closest('tr'));
    });

    $(document).on('keydown', function(e) {
        if (e.key === 'F10') {
            e.preventDefault();
            const $row = $('.pob-grid tbody tr:has(input:focus)').first();
            tryLoadOperatorIntelligenceFromRow($row.length ? $row : $('.pob-grid tbody tr:last'));
        }
    });
})();


// v28.1 hardened scheme binding
$(document).on('keydown', function(e) {
    if (e.key === 'F4' && window.PharmaOperatorBilling && window.PharmaOperatorBilling.collectPayload) {
        e.preventDefault();
        const payload = window.PharmaOperatorBilling.collectPayload();
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_advanced_scheme_to_operator_payload',
            args: {data: payload},
            callback: function(r) {
                const updated = r.message || {};
                if (updated.advanced_scheme_result && updated.advanced_scheme_result.payload && window.PharmaAdvancedSchemeV28) {
                    window.PharmaAdvancedSchemeV28.render({
                        best: updated.advanced_scheme_result.best,
                        payload: updated.advanced_scheme_result.payload
                    });
                }
                frappe.show_alert({message: updated.advanced_scheme_name ? ('Advanced scheme ready: ' + updated.advanced_scheme_name) : 'No eligible advanced scheme', indicator: updated.advanced_scheme_name ? 'green' : 'orange'});
                window.__current_pharma_quick_sale_payload = updated;
            }
        });
    }
});


// v28.2 complete scheme application binding
$(document).on('keydown', function(e) {
    if (e.key === 'F4' && window.PharmaOperatorBilling && window.PharmaOperatorBilling.collectPayload) {
        e.preventDefault();
        const payload = window.PharmaOperatorBilling.collectPayload();
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_advanced_scheme_to_operator_payload',
            args: {data: payload},
            callback: function(r) {
                const updated = r.message || {};
                window.__current_pharma_quick_sale_payload = updated;

                if (updated.advanced_scheme_name) {
                    // Best-effort UI application for dedicated Operator Billing page.
                    if (window.PharmaOperatorBilling && window.PharmaOperatorBilling.state && Array.isArray(updated.items)) {
                        window.PharmaOperatorBilling.state.items = updated.items.map(x => ({
                            item_code: x.item_code,
                            item_name: x.item_name || x.item_code,
                            qty: Number(x.qty || 0),
                            free_qty: Number(x.free_qty || 0),
                            rate: Number(x.rate || 0),
                            discount_percentage: Number(x.discount_percentage || 0),
                            batch_rows: x.batch_rows || [],
                            is_free_item: x.is_free_item,
                            scheme: x.scheme
                        }));
                        if (window.PharmaOperatorBilling.renderGrid) {
                            window.PharmaOperatorBilling.renderGrid();
                        }
                    }
                    frappe.show_alert({message: 'Advanced scheme applied: ' + updated.advanced_scheme_name, indicator: 'green'});
                } else {
                    frappe.show_alert({message: 'No eligible advanced scheme', indicator: 'orange'});
                }

                if (window.PharmaAdvancedSchemeV28 && updated.advanced_scheme_result) {
                    window.PharmaAdvancedSchemeV28.render({
                        best: updated.advanced_scheme_result.best,
                        payload: updated.advanced_scheme_result.payload
                    });
                }
            }
        });
    }
});
