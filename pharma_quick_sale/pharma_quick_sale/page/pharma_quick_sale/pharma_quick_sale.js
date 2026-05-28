
//    page.add_inner_button('v24.1 Speed Mode', async () => {
//        if (!window.PharmaFastBillingV241) {
//            frappe.msgprint('Fast billing helper is not loaded.');
//            return;
//        }
//        const warehouse = this && this.warehouse ? this.warehouse.get_value() : null;
//        await window.PharmaFastBillingV241.bootstrapFromServer({warehouse, price_list: 'Standard Selling'});
//        $('body').addClass('pqs-dense-mode');
//        frappe.show_alert({message: 'v24.1 IndexedDB cache loaded and dense mode enabled.', indicator: 'green'});
//    });


frappe.pages['pharma_quick_sale'].on_page_load = function(wrapper) {
    new PharmaQuickSalePage(wrapper);
};

class PharmaQuickSalePage {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.live_calc_timer = null;
        this.scheme_timer = null;
        this.last_live_grand_total = 0;
        this.page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Pharma Quick Sale',
            single_column: true
        });
        this.make();
    }

    make() {
        this.page.body.html(this.get_html());
        this.add_css();
        this.make_controls();
        this.bind_events();
        this.add_row();
        setTimeout(() => $('#pqs-barcode').focus(), 300);
    }

    add_css() {
        if ($('#pqs-ui-polish-style').length) return;
        $('<style id="pqs-ui-polish-style">').text(`
            .pqs-shell {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 320px;
                gap: 14px;
                padding: 12px;
                background: #f7f8fa;
                min-height: calc(100vh - 120px);
            }
            .pqs-card {
                background: #fff;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,.05);
                padding: 12px;
            }
            .pqs-header-grid {
                display: grid;
                grid-template-columns: repeat(5, minmax(150px, 1fr));
                gap: 8px;
                align-items: end;
            }
            .pqs-toolbar {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin: 10px 0;
            }
            .pqs-table-wrap {
                overflow-x: auto;
                border: 1px solid #eef0f2;
                border-radius: 10px;
            }
            .pqs-table {
                margin-bottom: 0;
                background: #fff;
            }
            .pqs-table thead th {
                position: sticky;
                top: 0;
                background: #f3f4f6;
                z-index: 1;
                font-size: 12px;
                text-transform: uppercase;
                color: #4b5563;
                letter-spacing: .02em;
                vertical-align: middle;
            }
            .pqs-table td {
                vertical-align: middle !important;
            }
            .pqs-table input {
                min-width: 78px;
            }
            .pqs-batch-chip {
                display: inline-block;
                margin: 2px;
                padding: 3px 7px;
                border: 1px solid #d1d8dd;
                border-radius: 999px;
                background: #f8fafc;
                font-size: 12px;
                white-space: nowrap;
            }
            .pqs-batch-chip.good { border-color: #bbf7d0; background: #f0fdf4; color: #166534; }
            .pqs-batch-chip.warn { border-color: #fde68a; background: #fffbeb; color: #92400e; }
            .pqs-batch-chip.bad { border-color: #fecaca; background: #fef2f2; color: #991b1b; }
            .pqs-side {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            .pqs-side h4 {
                margin: 0 0 8px;
                font-size: 14px;
                font-weight: 700;
            }
            .pqs-info-line {
                display: flex;
                justify-content: space-between;
                border-bottom: 1px dashed #e5e7eb;
                padding: 5px 0;
                font-size: 13px;
            }
            .pqs-info-line strong {
                color: #111827;
            }
            .pqs-muted {
                color: #6b7280;
                font-size: 12px;
            }
            .pqs-shortcuts kbd {
                background: #f3f4f6;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 2px 5px;
                font-size: 11px;
            }
            .pqs-bottom-bar {
                position: sticky;
                bottom: 0;
                z-index: 5;
                margin-top: 12px;
                background: #111827;
                color: #fff;
                border-radius: 12px;
                padding: 10px 12px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                box-shadow: 0 -4px 12px rgba(0,0,0,.08);
            }
            .pqs-bottom-totals {
                display: flex;
                gap: 18px;
                flex-wrap: wrap;
            }
            .pqs-bottom-totals span {
                font-size: 13px;
                color: #d1d5db;
            }
            .pqs-bottom-totals b {
                color: #fff;
                font-size: 15px;
            }
            .pqs-bottom-actions {
                display: flex;
                gap: 8px;
            }
            .pqs-row-warning {
                background: #fff7ed !important;
            }
            .pqs-row-error {
                background: #fef2f2 !important;
            }
            @media (max-width: 1100px) {
                .pqs-shell { grid-template-columns: 1fr; }
                .pqs-header-grid { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
            }
        `).appendTo('head');
    }

    get_html() {
        return `
            <div class="pqs-shell">
                <div>
                    <div class="pqs-card">
                        <div class="pqs-header-grid">
                            <div id="pqs-customer"></div>
                            <div id="pqs-company"></div>
                            <div id="pqs-warehouse"></div>
                            <div>
                                <label class="control-label">Posting Date</label>
                                <input type="date" id="pqs-posting-date" class="form-control">
                            </div>
                            <div>
                                <label class="control-label">Barcode / Quick Scan</label>
                                <input type="text" id="pqs-barcode" class="form-control" placeholder="Scan barcode and press Enter">
                            </div>
                        </div>

                        <div class="pqs-toolbar">
                            <button class="btn btn-sm btn-default" id="pqs-add-row">+ Add Row</button>
                            <button class="btn btn-sm btn-default" id="pqs-repeat-last">Repeat Last Order</button>
                            <button class="btn btn-sm btn-warning" id="pqs-last-sales">Last Sales</button>
                            <button class="btn btn-sm btn-default" id="pqs-expiry-dashboard">Expiry Dashboard</button>
                            <button class="btn btn-sm btn-danger" id="pqs-clear">Clear</button>
                        </div>

                        <div class="pqs-table-wrap">
                            <table class="table table-bordered pqs-table">
                                <thead>
                                    <tr>
                                        <th style="min-width:220px;">Item</th>
                                        <th>Qty</th>
                                        <th>Free</th>
                                        <th>Rate</th>
                                        <th>Disc %</th>
                                        <th style="min-width:260px;">Batches</th>
                                        <th>Actions</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody id="pqs-items"></tbody>
                            </table>
                        </div>
                    </div>

                    <div class="pqs-bottom-bar">
                        <div class="pqs-bottom-totals">
                            <span>Qty <b id="pqs-total-qty">0</b></span>
                            <span>Free <b id="pqs-total-free">0</b></span>
                            <span>Net <b>₹ <span id="pqs-net-total">0.00</span></b></span>
                            <span>Tax <b>₹ <span id="pqs-tax-total">0.00</span></b></span>
                            <span>Grand <b>₹ <span id="pqs-grand-total">0.00</span></b></span>
                        </div>
                        <div class="pqs-bottom-actions">
                            <button class="btn btn-sm btn-info" id="pqs-create-so">Create SO</button>
                            <button class="btn btn-sm btn-primary" id="pqs-create-invoice">Create Invoice</button>
                        </div>
                    </div>
                </div>

                <div class="pqs-side">
                    <div class="pqs-card">
                        <h4>Customer Credit</h4>
                        <div id="pqs-credit-panel">
                            <div class="pqs-muted">Select customer to view credit status.</div>
                        </div>
                    </div>

                    <div class="pqs-card">
                        <h4>Live Item Intelligence</h4>
                        <div id="pqs-intelligence">
                            <div class="pqs-muted">Select an item to view price, stock, and last sale history.</div>
                        </div>
                    </div>

                    <div class="pqs-card">
                        <h4>Tax Summary</h4>
                        <div id="pqs-tax-summary">
                            <div class="pqs-info-line"><span>Net</span><strong>₹ <span id="pqs-side-net">0.00</span></strong></div>
                            <div class="pqs-info-line"><span>Taxes</span><strong>₹ <span id="pqs-side-tax">0.00</span></strong></div>
                            <div class="pqs-info-line"><span>Grand Total</span><strong>₹ <span id="pqs-side-grand">0.00</span></strong></div>
                            <div id="pqs-tax-lines" class="pqs-muted" style="margin-top:8px;"></div>
                        </div>
                    </div>

                    <div class="pqs-card pqs-shortcuts">
                        <h4>Shortcuts</h4>
                        <div class="pqs-info-line"><span><kbd>F2</kbd></span><strong>Add Row</strong></div>
                        <div class="pqs-info-line"><span><kbd>F4</kbd></span><strong>Price / Last Sale</strong></div>
                        <div class="pqs-info-line"><span><kbd>F5</kbd></span><strong>Apply Scheme</strong></div>
                        <div class="pqs-info-line"><span><kbd>F6</kbd></span><strong>Last Sales</strong></div>
                        <div class="pqs-info-line"><span><kbd>Ctrl</kbd> + <kbd>I</kbd></span><strong>Create Invoice</strong></div>
                        <div class="pqs-info-line"><span><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span><strong>Create SO</strong></div>
                    </div>
                </div>
            </div>
        `;
    }

    make_controls() {
        this.customer = frappe.ui.form.make_control({
            parent: $('#pqs-customer'),
            df: {fieldtype:'Link', options:'Customer', fieldname:'customer', label:'Customer', reqd:1, onchange: () => { this.schedule_live_calculation(); this.load_credit_snapshot(); }},
            render_input: true
        });

        this.company = frappe.ui.form.make_control({
            parent: $('#pqs-company'),
            df: {fieldtype:'Link', options:'Company', fieldname:'company', label:'Company', reqd:1, onchange: () => this.schedule_live_calculation()},
            render_input: true
        });
        this.company.set_value(frappe.defaults.get_default('company'));

        this.warehouse = frappe.ui.form.make_control({
            parent: $('#pqs-warehouse'),
            df: {fieldtype:'Link', options:'Warehouse', fieldname:'warehouse', label:'Warehouse', reqd:1, get_query: () => {
                return {
                    filters: {
                        company: this.company.get_value()
                    }
                };
            },
            onchange: () => this.schedule_live_calculation()},
            render_input: true
        });

        $('#pqs-posting-date').val(frappe.datetime.get_today());
        $('#pqs-posting-date').on('change', () => this.schedule_live_calculation());
    }

    bind_events() {
        $('#pqs-add-row').on('click', () => this.add_row());
        $('#pqs-create-invoice').on('click', () => this.save('invoice'));
        $('#pqs-create-so').on('click', () => this.save('sales_order'));
        $('#pqs-clear').on('click', () => this.clear());
        $('#pqs-barcode').on('change keydown', (e) => {
            if (e.type === 'change' || e.key === 'Enter') this.handle_barcode();
        });
        $('#pqs-last-sales').on('click', () => this.show_last_sales());
        $('#pqs-expiry-dashboard').on('click', () => this.show_expiry_dashboard());
        $('#pqs-repeat-last').on('click', () => this.repeat_last_order());

        $(document).off('keydown.pqs');
        $(document).on('keydown.pqs', (e) => {
            if (e.key === 'F2') {
                e.preventDefault();
                this.add_row();
            }
            if (e.key === 'F4') {
                e.preventDefault();
                const row = $('#pqs-items tr').last();
                if (row.length) this.price_lookup_dialog(row);
            }
            if (e.key === 'F5') {
                e.preventDefault();
                const row = $('#pqs-items tr').last();
                if (row.length) this.apply_scheme_for_row(row);
            }
            if (e.key === 'F6') {
                e.preventDefault();
                this.show_last_sales();
            }
            if (e.ctrlKey && e.key.toLowerCase() === 'i') {
                e.preventDefault();
                this.save('invoice');
            }
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                this.save('sales_order');
            }
        });
    }

    add_row(prefill={}) {
        const row_id = prefill.row_id || frappe.utils.get_random(8);
        const row = $(`
            <tr data-row="${row_id}">
                <td><input type="text" class="form-control quick-search" placeholder="Smart search brand/salt/item"><div class="item-control" style="margin-top:4px;"></div></td>
                <td><input type="number" class="form-control qty" value="${prefill.qty || 0}"></td>
                <td><input type="number" class="form-control free-qty" value="${prefill.free_qty || 0}"></td>
                <td><input type="number" class="form-control rate" value="${prefill.rate || 0}"></td>
                <td><input type="number" class="form-control discount" value="${prefill.discount_percentage || 0}"></td>
                <td>
                    <div class="batch-display"></div>
                    <button class="btn btn-xs btn-default fefo">Auto FEFO</button>
                    <button class="btn btn-xs btn-default manual-batch">Manual</button>
                </td>
                <td>
                    <button class="btn btn-xs btn-default lookup">Lookup</button>
                    <button class="btn btn-xs btn-default smart-search">Search</button>
                    <button class="btn btn-xs btn-success scheme">Scheme</button>
                    <button class="btn btn-xs btn-default substitute">Subs</button>
                </td>
                <td><button class="btn btn-xs btn-danger remove">×</button></td>
            </tr>
        `);

        $('#pqs-items').append(row);

        const item_control = frappe.ui.form.make_control({
            parent: row.find('.item-control'),
            df: {
                fieldtype:'Link',
                options:'Item',
                fieldname:'item_code',
                onchange: () => this.load_price_lookup(row)
            },
            render_input: true
        });

        row.data('row_id', row_id);
        row.data('item_control', item_control);
        row.data('batch_rows', prefill.batch_rows || []);

        if (prefill.item_code) item_control.set_value(prefill.item_code);

        row.find('.quick-search').on('input', () => this.inline_smart_search(row));
        row.find('.quick-search').on('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.inline_smart_search(row, true);
            }
        });

        row.find('.qty').on('input', () => {
            this.schedule_auto_scheme_for_row(row);
            this.calculate_totals();
            this.schedule_live_calculation();
        });
        row.find('.free-qty,.rate,.discount').on('input', () => {
            this.calculate_totals();
            this.schedule_live_calculation();
        });
        row.find('.fefo').on('click', () => this.allocate_fefo_for_row(row));
        row.find('.manual-batch').on('click', () => this.manual_batch_dialog(row));
        row.find('.lookup').on('click', () => this.price_lookup_dialog(row));
        row.find('.smart-search').on('click', () => this.smart_item_search_dialog(row));
        row.find('.scheme').on('click', () => this.apply_scheme_for_row(row));
        row.find('.substitute').on('click', () => this.show_substitutes(row));
        row.find('.remove').on('click', () => {
            row.remove();
            this.calculate_totals();
            this.schedule_live_calculation();
        });

        this.render_batches(row);
        this.calculate_totals();
        this.schedule_live_calculation();
    }

    get_item_code(row) {
        return row.data('item_control').get_value();
    }

    load_price_lookup(row) {
        const item_code = this.get_item_code(row);
        if (!item_code) return;

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_item_price_lookup',
            args: {
                item_code,
                customer: this.customer.get_value(),
                warehouse: this.warehouse.get_value(),
                price_list: 'Standard Selling'
            },
            callback: (r) => {
                const d = r.message || {};
                row.find('.rate').val(d.price || 0);
                this.update_intelligence_panel(d);
                this.auto_apply_scheme_for_row(row);
                this.calculate_totals();
                this.schedule_live_calculation();
            }
        });
    }

    update_intelligence_panel(d) {
        const last = (d.last_sale || []).slice(0, 3).map(x => `
            <div class="pqs-info-line">
                <span>${x.posting_date || ''}</span>
                <strong>${x.qty || 0} @ ₹${x.rate || 0}</strong>
            </div>
        `).join('');

        $('#pqs-intelligence').html(`
            <div class="pqs-info-line"><span>Item</span><strong>${d.item_name || d.item_code || ''}</strong></div>
            <div class="pqs-info-line"><span>Price</span><strong>₹ ${flt(d.price || 0).toFixed(2)}</strong></div>
            <div class="pqs-info-line"><span>MRP</span><strong>₹ ${flt((d.pharma_price || {}).mrp || 0).toFixed(2)}</strong></div>
            <div class="pqs-info-line"><span>PTR</span><strong>₹ ${flt((d.pharma_price || {}).ptr || 0).toFixed(2)}</strong></div>
            <div class="pqs-info-line"><span>PTS</span><strong>₹ ${flt((d.pharma_price || {}).pts || 0).toFixed(2)}</strong></div>
            <div class="pqs-info-line"><span>Stock</span><strong>${flt(d.stock_qty || 0)}</strong></div>
            <div style="margin-top:8px;"><b>Recent Sales</b></div>
            ${last || '<div class="pqs-muted">No recent sales found.</div>'}
        `);
    }

    allocate_fefo_for_row(row) {
        const item_code = this.get_item_code(row);
        const qty = flt(row.find('.qty').val()) + flt(row.find('.free-qty').val());
        const warehouse = this.warehouse.get_value();

        if (!item_code || !warehouse || qty <= 0) {
            frappe.msgprint('Select item, warehouse, and quantity first.');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.allocate_fefo',
            args: {item_code, warehouse, qty},
            freeze: true,
            freeze_message: 'Allocating FEFO batches...',
            callback: (r) => {
                let billable_remaining = flt(row.find('.qty').val());
                let free_remaining = flt(row.find('.free-qty').val());
                let allocations = [];

                (r.message || []).forEach(b => {
                    let available = flt(b.qty || b.available_qty);
                    let billable_qty = Math.min(available, billable_remaining);
                    billable_remaining -= billable_qty;
                    available -= billable_qty;

                    let free_qty = Math.min(available, free_remaining);
                    free_remaining -= free_qty;

                    allocations.push({
                        batch_no: b.batch_no,
                        expiry_date: b.expiry_date,
                        available_qty: b.available_qty,
                        qty: billable_qty,
                        free_qty: free_qty
                    });
                });

                row.data('batch_rows', allocations);
                this.render_batches(row);
                this.schedule_live_calculation();
            }
        });
    }

    manual_batch_dialog(row) {
        const item_code = this.get_item_code(row);
        let d = new frappe.ui.Dialog({
            title: 'Add Batch',
            fields: [
                {fieldname:'batch_no', fieldtype:'Link', options:'Batch', label:'Batch', reqd:1, get_query: () => { return { filters: {item: item_code} } }},
                {fieldname:'qty', fieldtype:'Float', label:'Qty', default: flt(row.find('.qty').val())},
                {fieldname:'free_qty', fieldtype:'Float', label:'Free Qty', default: flt(row.find('.free-qty').val())}
            ],
            primary_action_label: 'Add',
            primary_action: (values) => {
                let batches = row.data('batch_rows') || [];
                batches.push(values);
                row.data('batch_rows', batches);
                this.render_batches(row);
                this.schedule_live_calculation();
                d.hide();
            }
        });
        d.show();
    }

    render_batches(row) {
        const batches = row.data('batch_rows') || [];
        let html = batches.map(b => {
            const days = b.expiry_date ? frappe.datetime.get_diff(b.expiry_date, frappe.datetime.get_today()) : null;
            let status = 'good';
            if (days !== null && days <= 0) status = 'bad';
            else if (days !== null && days <= 90) status = 'warn';
            return `<span class="pqs-batch-chip ${status}">${b.batch_no}: ${b.qty || 0}+${b.free_qty || 0}${b.expiry_date ? ' | Exp ' + b.expiry_date : ''}</span>`;
        }).join('');
        row.find('.batch-display').html(html || '<span class="pqs-muted">No batch allocated</span>');
        row.toggleClass('pqs-row-warning', !!batches.length && batches.some(b => b.expiry_date && frappe.datetime.get_diff(b.expiry_date, frappe.datetime.get_today()) <= 90));
        row.toggleClass('pqs-row-error', !!batches.length && batches.some(b => b.expiry_date && frappe.datetime.get_diff(b.expiry_date, frappe.datetime.get_today()) <= 0));
    }

    price_lookup_dialog(row) {
        const item_code = this.get_item_code(row);
        if (!item_code) {
            frappe.msgprint('Select item first.');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_item_price_lookup',
            args: {
                item_code,
                customer: this.customer.get_value(),
                warehouse: this.warehouse.get_value(),
                price_list: 'Standard Selling'
            },
            callback: (r) => {
                const d = r.message || {};
                this.update_intelligence_panel(d);
                const last = (d.last_sale || []).map(x => `<tr><td>${x.posting_date}</td><td>${x.qty}</td><td>${x.rate}</td><td>${x.discount_percentage || 0}%</td></tr>`).join('');
                frappe.msgprint(`
                    <b>${d.item_name || item_code}</b><br>
                    Current Price: ${d.price || 0}<br>
                    Stock: ${d.stock_qty || 0}<br><br>
                    <table class="table table-bordered">
                        <tr><th>Date</th><th>Qty</th><th>Rate</th><th>Disc</th></tr>
                        ${last || '<tr><td colspan="4">No history</td></tr>'}
                    </table>
                `);
            }
        });
    }


    schedule_auto_scheme_for_row(row) {
        clearTimeout(row.data('scheme_timer'));
        const timer = setTimeout(() => this.auto_apply_scheme_for_row(row), 350);
        row.data('scheme_timer', timer);
    }

    inline_smart_search(row, auto_pick=false) {
        const txt = row.find('.quick-search').val();
        if (!txt || txt.length < 2) return;

        clearTimeout(row.data('search_timer'));
        const timer = setTimeout(() => {
            frappe.call({
                method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.pharma_item_search',
                args: {
                    txt,
                    warehouse: this.warehouse.get_value(),
                    customer: this.customer.get_value(),
                    price_list: 'Standard Selling',
                    limit: auto_pick ? 1 : 5
                },
                callback: (r) => {
                    const results = r.message || [];
                    if (!results.length) return;

                    if (auto_pick || results.length === 1) {
                        const x = results[0];
                        row.data('item_control').set_value(x.item_code);
                        row.find('.rate').val(flt(x.rate || x.ptr || 0));
                        row.find('.quick-search').val(x.item_name || x.item_code);
                        this.auto_apply_scheme_for_row(row);
                        this.calculate_totals();
                        this.schedule_live_calculation();
                        return;
                    }

                    const html = results.map(x => `
                        <div class="pqs-search-suggestion" data-item="${x.item_code}" data-rate="${x.rate || x.ptr || 0}" style="padding:5px; border-bottom:1px solid #eee; cursor:pointer;">
                            <b>${x.item_name || x.item_code}</b><br>
                            <small>${x.item_code} | Stock ${flt(x.stock_qty)} | MRP ${flt(x.mrp).toFixed(2)} | PTR ${flt(x.ptr).toFixed(2)}</small>
                        </div>
                    `).join('');

                    let box = row.find('.pqs-inline-results');
                    if (!box.length) {
                        box = $('<div class="pqs-inline-results" style="position:absolute;background:#fff;border:1px solid #ddd;z-index:9999;max-height:220px;overflow:auto;min-width:360px;"></div>');
                        row.find('.quick-search').after(box);
                    }
                    box.html(html).show();

                    box.find('.pqs-search-suggestion').on('click', (ev) => {
                        const el = $(ev.currentTarget);
                        row.data('item_control').set_value(el.data('item'));
                        row.find('.rate').val(flt(el.data('rate')));
                        row.find('.quick-search').val(el.find('b').text());
                        box.hide();
                        this.auto_apply_scheme_for_row(row);
                        this.calculate_totals();
                        this.schedule_live_calculation();
                    });
                }
            });
        }, 250);

        row.data('search_timer', timer);
    }

    validate_credit_before_save(callback) {
        const customer = this.customer.get_value();
        if (!customer) {
            callback(true);
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.validate_credit_before_quick_sale',
            args: {
                customer,
                company: this.company.get_value(),
                projected_grand_total: this.last_live_grand_total || 0
            },
            callback: (r) => {
                const d = r.message || {};
                if (d.allow === false) {
                    frappe.msgprint({
                        title: 'Credit Block',
                        indicator: 'red',
                        message: d.message || 'Credit limit exceeded.'
                    });
                    callback(false);
                    return;
                }

                if (d.status === 'WARNING') {
                    frappe.confirm(
                        d.message || 'Customer has overdue outstanding. Continue?',
                        () => callback(true),
                        () => callback(false)
                    );
                    return;
                }

                callback(true);
            }
        });
    }

    smart_item_search_dialog(row) {
        const d = new frappe.ui.Dialog({
            title: 'Smart Item Search',
            fields: [
                {fieldname: 'txt', fieldtype: 'Data', label: 'Search', reqd: 1},
                {fieldname: 'results_html', fieldtype: 'HTML'}
            ],
            primary_action_label: 'Search',
            primary_action: (values) => {
                frappe.call({
                    method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.pharma_item_search',
                    args: {
                        txt: values.txt,
                        warehouse: this.warehouse.get_value(),
                        customer: this.customer.get_value(),
                        price_list: 'Standard Selling'
                    },
                    callback: (r) => {
                        const results = r.message || [];
                        if (!results.length) {
                            d.fields_dict.results_html.$wrapper.html('<div class="text-muted">No results found.</div>');
                            return;
                        }

                        const html = `
                            <table class="table table-bordered">
                                <tr>
                                    <th>Item</th><th>Stock</th><th>MRP</th><th>PTR</th><th>Action</th>
                                </tr>
                                ${results.map(x => `
                                    <tr>
                                        <td>
                                            <b>${x.item_name || x.item_code}</b><br>
                                            <span class="text-muted">${x.item_code}</span><br>
                                            <small>${x.composition || ''}</small>
                                        </td>
                                        <td>${flt(x.stock_qty)}</td>
                                        <td>${flt(x.mrp).toFixed(2)}</td>
                                        <td>${flt(x.ptr).toFixed(2)}</td>
                                        <td><button class="btn btn-xs btn-primary pqs-select-search-item" data-item="${x.item_code}" data-rate="${x.rate || x.ptr || 0}">Select</button></td>
                                    </tr>
                                `).join('')}
                            </table>
                        `;
                        d.fields_dict.results_html.$wrapper.html(html);

                        d.fields_dict.results_html.$wrapper.find('.pqs-select-search-item').on('click', (ev) => {
                            const btn = $(ev.currentTarget);
                            row.data('item_control').set_value(btn.data('item'));
                            row.find('.rate').val(flt(btn.data('rate')));
                            d.hide();
                            this.auto_apply_scheme_for_row(row);
                            this.calculate_totals();
                            this.schedule_live_calculation();
                        });
                    }
                });
            }
        });

        d.show();
        setTimeout(() => d.fields_dict.txt.$input.focus(), 200);
    }

    auto_apply_scheme_for_row(row) {
        const item_code = this.get_item_code(row);
        const qty = flt(row.find('.qty').val());

        if (!item_code || qty <= 0) {
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_best_scheme',
            args: {
                customer: this.customer.get_value(),
                item_code,
                qty,
                posting_date: $('#pqs-posting-date').val()
            },
            callback: (r) => {
                const scheme = r.message;
                if (!scheme) {
                    row.removeAttr('data-scheme');
                    row.find('.scheme').removeClass('btn-warning').addClass('btn-success').text('Scheme');
                    return;
                }

                const current_free = flt(row.find('.free-qty').val());
                const new_free = flt(scheme.free_qty);

                if (current_free === new_free && row.attr('data-scheme') === (scheme.scheme_name || scheme.scheme)) {
                    return;
                }

                row.find('.free-qty').val(new_free);
                row.attr('data-scheme', scheme.scheme_name || scheme.scheme);
                row.find('.scheme').removeClass('btn-success').addClass('btn-warning').text('Scheme ✓');

                const had_batches = (row.data('batch_rows') || []).length > 0;
                if (had_batches) {
                    row.data('batch_rows', []);
                    this.render_batches(row);
                    if (this.warehouse.get_value()) {
                        this.allocate_fefo_for_row(row);
                    }
                }

                this.calculate_totals();
                this.schedule_live_calculation();
            }
        });
    }

    load_credit_snapshot() {
        const customer = this.customer.get_value();
        const company = this.company.get_value();

        if (!customer) {
            $('#pqs-credit-panel').html('<div class="pqs-muted">Select customer to view credit status.</div>');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_customer_credit_snapshot',
            args: {customer, company},
            callback: (r) => {
                const d = r.message || {};
                const color = d.status === 'BLOCK' ? '#dc2626' : (d.status === 'WARNING' ? '#d97706' : '#16a34a');

                $('#pqs-credit-panel').html(`
                    <div class="pqs-info-line"><span>Status</span><strong style="color:${color};">${d.status || 'OK'}</strong></div>
                    <div class="pqs-info-line"><span>Outstanding</span><strong>₹ ${flt(d.outstanding).toFixed(2)}</strong></div>
                    <div class="pqs-info-line"><span>Overdue</span><strong>₹ ${flt(d.overdue).toFixed(2)}</strong></div>
                    <div class="pqs-info-line"><span>Credit Limit</span><strong>₹ ${flt(d.credit_limit).toFixed(2)}</strong></div>
                    <div class="pqs-info-line"><span>Available</span><strong>₹ ${flt(d.available_credit).toFixed(2)}</strong></div>
                `);
            }
        });
    }

    apply_scheme_for_row(row) {
        const item_code = this.get_item_code(row);
        const qty = flt(row.find('.qty').val());
        const customer = this.customer.get_value();

        if (!item_code || qty <= 0) {
            frappe.msgprint('Select item and quantity before applying scheme.');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_best_scheme',
            args: {
                customer,
                item_code,
                qty,
                posting_date: $('#pqs-posting-date').val()
            },
            callback: (r) => {
                const scheme = r.message;
                if (!scheme) {
                    frappe.show_alert({message: 'No applicable scheme found.', indicator: 'orange'});
                    return;
                }

                const old_free_qty = flt(row.find('.free-qty').val());
                row.find('.free-qty').val(flt(scheme.free_qty));
                row.attr('data-scheme', scheme.scheme_name || scheme.scheme);
                row.find('.scheme').removeClass('btn-success').addClass('btn-warning').text('Scheme ✓');

                const had_batches = (row.data('batch_rows') || []).length > 0;
                if (had_batches && old_free_qty !== flt(scheme.free_qty)) {
                    row.data('batch_rows', []);
                    this.render_batches(row);
                    if (this.warehouse.get_value()) {
                        this.allocate_fefo_for_row(row);
                    }
                }

                frappe.show_alert({
                    message: `Scheme applied: ${scheme.scheme_name || scheme.scheme} | Free Qty ${scheme.free_qty}`,
                    indicator: 'green'
                });

                this.calculate_totals();
                this.schedule_live_calculation();
            }
        });
    }


    show_substitutes(row) {
        const item_code = this.get_item_code(row);
        if (!item_code) {
            frappe.msgprint('Select item first.');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_item_substitutes',
            args: {
                item_code: item_code,
                warehouse: this.warehouse.get_value()
            },
            callback: (r) => {
                const rows = r.message || [];
                if (!rows.length) {
                    frappe.msgprint('No substitutes configured for this item.');
                    return;
                }

                const html = `
                    <table class="table table-bordered">
                        <tr><th>Substitute</th><th>Type</th><th>Stock</th><th>Action</th></tr>
                        ${rows.map(x => `
                            <tr>
                                <td><b>${x.item_name || x.item_code}</b><br><small>${x.item_code}</small></td>
                                <td>${x.substitution_type || ''}</td>
                                <td>${flt(x.stock_qty)}</td>
                                <td><button class="btn btn-xs btn-primary pqs-use-substitute" data-item="${x.item_code}">Use</button></td>
                            </tr>
                        `).join('')}
                    </table>
                `;

                const d = new frappe.ui.Dialog({
                    title: 'Substitute Items',
                    fields: [{fieldname:'html', fieldtype:'HTML'}]
                });
                d.fields_dict.html.$wrapper.html(html);
                d.show();

                d.fields_dict.html.$wrapper.find('.pqs-use-substitute').on('click', (ev) => {
                    const item = $(ev.currentTarget).data('item');
                    row.data('item_control').set_value(item);
                    d.hide();
                    this.load_price_lookup(row);
                });
            }
        });
    }

    show_last_sales() {
        const customer = this.customer.get_value();
        if (!customer) {
            frappe.msgprint('Select customer first.');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_last_sales',
            args: {customer},
            callback: (r) => {
                const rows = (r.message || []).map(x => `<tr><td>${x.posting_date}</td><td>${x.item_code}</td><td>${x.qty}</td><td>${x.rate}</td></tr>`).join('');
                frappe.msgprint(`<table class="table table-bordered"><tr><th>Date</th><th>Item</th><th>Qty</th><th>Rate</th></tr>${rows || '<tr><td colspan="4">No history</td></tr>'}</table>`);
            }
        });
    }

    repeat_last_order() {
        const customer = this.customer.get_value();
        if (!customer) {
            frappe.msgprint('Select customer first.');
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_last_sales',
            args: {customer, limit: 20},
            freeze: true,
            freeze_message: 'Loading last order...',
            callback: (r) => {
                const rows = r.message || [];
                if (!rows.length) {
                    frappe.msgprint('No previous sales found for this customer.');
                    return;
                }

                // Use rows from the most recent invoice only.
                const latest_invoice = rows[0].invoice;
                const latest_rows = rows.filter(x => x.invoice === latest_invoice);

                latest_rows.forEach(x => {
                    this.add_row({
                        item_code: x.item_code,
                        qty: x.qty,
                        rate: x.rate,
                        discount_percentage: x.discount_percentage || 0
                    });
                });

                frappe.show_alert({
                    message: `Repeated items from ${latest_invoice}. Run FEFO before final save.`,
                    indicator: 'green'
                });

                this.schedule_live_calculation();
            }
        });
    }

    show_expiry_dashboard() {
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_expiry_dashboard',
            args: {warehouse: this.warehouse.get_value(), days: 180},
            callback: (r) => {
                const rows = (r.message || []).map(x => `<tr><td>${x.item_code}</td><td>${x.batch_no}</td><td>${x.expiry_date}</td><td>${x.qty}</td><td>${x.days_to_expiry}</td></tr>`).join('');
                frappe.msgprint(`<table class="table table-bordered"><tr><th>Item</th><th>Batch</th><th>Expiry</th><th>Qty</th><th>Days</th></tr>${rows || '<tr><td colspan="5">No expiring batches</td></tr>'}</table>`);
            }
        });
    }

    handle_barcode() {
        const barcode = $('#pqs-barcode').val();
        if (!barcode) return;

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_item_by_barcode',
            args: {
                barcode,
                warehouse: this.warehouse.get_value(),
                customer: this.customer.get_value(),
                price_list: 'Standard Selling'
            },
            callback: (r) => {
                const d = r.message;
                this.add_row({item_code: d.item_code, rate: d.price || 0});
                this.update_intelligence_panel(d);
                $('#pqs-barcode').val('').focus();
            }
        });
    }

    collect_data() {
        let items = [];
        let batch_allocations = [];

        $('#pqs-items tr').each((i, el) => {
            const row = $(el);
            const row_id = row.data('row_id');
            const item_code = this.get_item_code(row);
            if (!item_code) return;

            items.push({
                row_id,
                item_code,
                rate: flt(row.find('.rate').val()),
                discount_percentage: flt(row.find('.discount').val()),
                qty: flt(row.find('.qty').val()),
                free_qty: flt(row.find('.free-qty').val())
            });

            (row.data('batch_rows') || []).forEach(b => {
                batch_allocations.push({
                    item_row_id: row_id,
                    item_code,
                    batch_no: b.batch_no,
                    expiry_date: b.expiry_date,
                    available_qty: b.available_qty,
                    qty: flt(b.qty),
                    free_qty: flt(b.free_qty)
                });
            });
        });

        return {
            customer: this.customer.get_value(),
            company: this.company.get_value(),
            warehouse: this.warehouse.get_value(),
            posting_date: $('#pqs-posting-date').val(),
            price_list: 'Standard Selling',
            items,
            batch_allocations
        };
    }

    save(action) {
        const data = this.collect_data();
        if (!data.customer || !data.company || !data.warehouse || !data.items.length || !data.batch_allocations.length) {
            frappe.msgprint('Customer, Company, Warehouse, at least one item, and batch allocations are required for final save.');
            return;
        }

        this.validate_credit_before_save((allowed) => {
            if (!allowed) return;

            frappe.call({
                method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_quick_sale',
                args: {data, action},
                freeze: true,
                freeze_message: 'Creating document...',
                callback: (r) => {
                    const d = r.message || {};
                    frappe.msgprint(`Quick Sale: ${d.quick_sale || ''}<br>Sales Invoice: ${d.sales_invoice || ''}<br>Sales Order: ${d.sales_order || ''}`);
                    if (d.sales_invoice) frappe.set_route('Form', 'Sales Invoice', d.sales_invoice);
                    if (d.sales_order) frappe.set_route('Form', 'Sales Order', d.sales_order);
                }
            });
        });
    }

    calculate_totals() {
        let total_qty = 0, total_free = 0;
        $('#pqs-items tr').each((i, el) => {
            const row = $(el);
            total_qty += flt(row.find('.qty').val());
            total_free += flt(row.find('.free-qty').val());
        });
        $('#pqs-total-qty').text(total_qty);
        $('#pqs-total-free').text(total_free);
    }

    schedule_live_calculation() {
        clearTimeout(this.live_calc_timer);
        this.live_calc_timer = setTimeout(() => this.calculate_live_taxes(), 450);
    }

    calculate_live_taxes() {
        const data = this.collect_data();

        if (!data.customer || !data.company || !data.items.length) {
            this.update_totals_display(0, 0, 0, []);
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_live_sales_totals',
            args: {data},
            callback: (r) => {
                const d = r.message || {};
                this.last_live_grand_total = flt(d.grand_total);
                this.update_totals_display(d.net_total, d.total_taxes_and_charges, d.grand_total, d.taxes || []);
            }
        });
    }

    update_totals_display(net, tax, grand, taxes) {
        $('#pqs-net-total, #pqs-side-net').text(flt(net).toFixed(2));
        $('#pqs-tax-total, #pqs-side-tax').text(flt(tax).toFixed(2));
        $('#pqs-grand-total, #pqs-side-grand').text(flt(grand).toFixed(2));

        const lines = (taxes || []).map(t => `
            <div class="pqs-info-line">
                <span>${t.description || t.account_head}${t.rate ? ' (' + t.rate + '%)' : ''}</span>
                <strong>₹ ${flt(t.tax_amount).toFixed(2)}</strong>
            </div>
        `).join('');
        $('#pqs-tax-lines').html(lines || '<div class="pqs-muted">No tax lines yet. Check Sales Taxes and Charges Template.</div>');
    }

    clear() {
        $('#pqs-items').empty();
        this.add_row();
        this.calculate_totals();
        this.update_totals_display(0, 0, 0, []);
        $('#pqs-intelligence').html('<div class="pqs-muted">Select an item to view price, stock, and last sale history.</div>');
        setTimeout(() => $('#pqs-barcode').focus(), 100);
    }
}

// v24-fast-hotkeys
$(document).on('keydown.v24_fast_billing', function(e) {
    if (e.ctrlKey && e.key.toLowerCase() === 'f') { e.preventDefault(); $('.quick-search:visible:first').focus(); }
    if (e.key === 'Escape') { $('.pqs-inline-results').hide(); }
});


window.PharmaQuickSaleV241Adapter = {
  applyPayload(payload) {
    window.__last_pharma_held_payload = payload;
    frappe.show_alert({message: 'Held bill payload restored. Final row binding requires site UAT mapping.', indicator: 'green'});
    if (payload && payload.customer) $('input[data-fieldname="customer"], input[placeholder*="Customer"]').first().val(payload.customer);
    return true;
  },
  focusSearch(){ $('.quick-search:visible:first, input[placeholder*="Smart search"]:visible:first, input[placeholder*="search"]:visible:first').focus(); },
  focusCustomer(){ $('input[data-fieldname="customer"], input[placeholder*="Customer"]').first().focus(); },
  focusQty(){ $('.qty:visible:first').focus().select(); },
  focusRate(){ $('.rate:visible:first').focus().select(); },
  applyScheme(){ $('.scheme:visible:last').trigger('click'); },
  saveInvoice(){ $('.btn:contains("Create Invoice")').first().trigger('click'); },
  savePrint(){ this.saveInvoice(); setTimeout(() => $('.btn:contains("Print")').first().trigger('click'), 800); },
  holdInvoice(){
    if (window.__current_pharma_quick_sale_payload) {
      frappe.call({
        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.held_invoice_save',
        args:{data: window.__current_pharma_quick_sale_payload},
        callback:r => frappe.show_alert({message:'Held bill saved: '+r.message, indicator:'green'})
      });
    } else frappe.msgprint('No active payload found to hold. Site-specific collect_data binding required.');
  },
  recallHeld(){
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.held_invoice_list',
      callback:r => {
        const rows = r.message || [];
        const html = `<table class="table table-bordered"><tr><th>Held Bill</th><th>Customer</th><th>Total</th><th>Action</th></tr>${rows.map(x => `<tr><td>${x.name}</td><td>${x.customer || ''}</td><td>${x.grand_total || 0}</td><td><button class="btn btn-xs btn-primary v241-recall-held" data-name="${x.name}">Recall</button></td></tr>`).join('')}</table>`;
        const d = new frappe.ui.Dialog({title:'Recall Held Bill', fields:[{fieldname:'html', fieldtype:'HTML'}]});
        d.fields_dict.html.$wrapper.html(html); d.show();
        d.fields_dict.html.$wrapper.find('.v241-recall-held').on('click', ev => {
          frappe.call({
            method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.held_invoice_restore',
            args:{held_invoice: $(ev.currentTarget).data('name')},
            callback:rr => { window.PharmaFastBillingV241.applyPayloadToUI(rr.message); d.hide(); }
          });
        });
      }
    });
  }
};

if (window.PharmaFastBillingV241) window.PharmaFastBillingV241.bindHotkeys(window.PharmaQuickSaleV241Adapter);
