
frappe.pages['pharma-operator-billing'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Pharma Operator Billing',
        single_column: true
    });

    $(frappe.render_template('pharma_operator_billing')).appendTo(page.body);

    const $templateRoot = $(page.body).find('.pob-root');
    if (!$templateRoot.find('#pob-company-control').length) {
        $templateRoot.prepend(`
            <div class="pob-link-controls row pob32-ribbon" style="margin-bottom: 8px;">
                <div class="col-md-3" id="pob-company-control"></div>
                <div class="col-md-3" id="pob-customer-control"></div>
                <div class="col-md-3" id="pob-warehouse-control"></div>
                <div class="col-md-3" id="pob-price-list-control"></div>
            </div>
        `);
        $templateRoot.find('.pob-company,.pob-customer,.pob-warehouse')
            .closest('.form-group, div')
            .hide();
    }

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

    // =============================================================
    // V33.1 IndexedDB + stale-search safety hotfix
    // Fixes:
    // - IDBDatabase.transaction: 'items' is not a known object store name
    // - item is undefined when stale suggestion/cache index is used
    // =============================================================

    async function resetFastBillingIndexedDBV331() {
        if (!window.indexedDB) return false;

        const dbNames = [
            'pharma_fast_billing_v24_1',
            'PharmaFastBillingV241',
            'pharma_fast_billing',
            'pharma_billing_cache'
        ];

        for (const dbName of dbNames) {
            try {
                await new Promise(resolve => {
                    const req = indexedDB.deleteDatabase(dbName);
                    req.onsuccess = () => resolve(true);
                    req.onerror = () => resolve(false);
                    req.onblocked = () => resolve(false);
                });
            } catch (e) {
                // continue
            }
        }

        return true;
    }

    async function safeBootstrapFastBillingV331() {
        if (!window.PharmaFastBillingV241) {
            frappe.msgprint('v24.1 fast billing helper not loaded.');
            return false;
        }

        state.warehouse = typeof getCurrentWarehouse === 'function'
            ? getCurrentWarehouse()
            : ($warehouse.val() || state.warehouse || '');

        try {
            await window.PharmaFastBillingV241.bootstrapFromServer({
                warehouse: state.warehouse,
                price_list: typeof getPriceList === 'function' ? getPriceList() : state.price_list
            });
            return true;
        } catch (e) {
            const msg = String((e && e.message) || e || '');

            if (
                msg.includes('not a known object store') ||
                msg.includes('object store') ||
                msg.includes('IDBDatabase.transaction')
            ) {
                status('Repairing local billing cacheâ€¦', 'orange');

                await resetFastBillingIndexedDBV331();

                try {
                    if (window.PharmaFastBillingV241.memory) {
                        window.PharmaFastBillingV241.memory = {};
                    }

                    await window.PharmaFastBillingV241.bootstrapFromServer({
                        warehouse: state.warehouse,
                        price_list: typeof getPriceList === 'function' ? getPriceList() : state.price_list
                    });

                    status('Local cache repaired', 'green');
                    return true;
                } catch (retryError) {
                    console.error('Fast billing cache retry failed', retryError);
                    status('Local cache failed; server search fallback active', 'orange');
                    return false;
                }
            }

            console.error('Fast billing bootstrap failed', e);
            status('Local cache failed; server search fallback active', 'orange');
            return false;
        }
    }

    function getMemoryItemSafeV331(code) {
        if (!code || !window.PharmaFastBillingV241 || !window.PharmaFastBillingV241.memory) {
            return null;
        }

        const index = window.PharmaFastBillingV241.memory.itemIndex || {};
        return index[code] || null;
    }

    function fetchSingleItemServerV331(code, callback) {
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.fast_item_search_v30',
            args: {
                query: code,
                warehouse: typeof getCurrentWarehouse === 'function' ? getCurrentWarehouse() : ($warehouse.val() || null),
                price_list: typeof getPriceList === 'function' ? getPriceList() : (state.price_list || 'Standard Selling')
            },
            callback: r => {
                const rows = r.message || [];
                const exact = rows.find(x => x.item_code === code || x.barcode === code) || rows[0] || null;
                callback(exact);
            },
            error: () => callback(null)
        });
    }


    // =============================================================
    // V32 Counter UX State + Helpers
    // =============================================================
    let selectedSuggestionIndex = 0;

    if (typeof setting_controls === 'undefined') {
        var setting_controls = false;
    }

    if (typeof getCustomer !== 'function') {
        var customer_control = null;
        var company_control = null;
        var warehouse_control = null;
        var price_list_control = null;

        function getCustomer() {
            return customer_control ? customer_control.get_value() : ($customer.val() || '');
        }

        function setCustomer(v, update_control = true) {
            v = v || '';
            state.customer = v;
            $customer.val(v);
            if (update_control && customer_control && customer_control.get_value() !== v) {
                setting_controls = true;
                customer_control.set_value(v);
                setting_controls = false;
            }
        }

        function getCompany() {
            return company_control ? company_control.get_value() : ($company.val() || '');
        }

        function setCompany(v, update_control = true) {
            v = v || '';
            state.company = v;
            $company.val(v);
            if (update_control && company_control && company_control.get_value() !== v) {
                setting_controls = true;
                company_control.set_value(v);
                setting_controls = false;
            }
        }

        function getWarehouse() {
            return warehouse_control ? warehouse_control.get_value() : ($warehouse.val() || '');
        }

        function setWarehouse(v, update_control = true) {
            v = v || '';
            state.warehouse = v;
            $warehouse.val(v);
            if (update_control && warehouse_control && warehouse_control.get_value() !== v) {
                setting_controls = true;
                warehouse_control.set_value(v);
                setting_controls = false;
            }
        }

        function getPriceList() {
            return price_list_control ? price_list_control.get_value() : (state.price_list || 'Standard Selling');
        }

        function setPriceList(v, update_control = true) {
            v = v || 'Standard Selling';
            state.price_list = v;
            if (update_control && price_list_control && price_list_control.get_value() !== v) {
                setting_controls = true;
                price_list_control.set_value(v);
                setting_controls = false;
            }
        }

        function make_controls() {
            company_control = frappe.ui.form.make_control({
                parent: $root.find('#pob-company-control'),
                df: {
                    fieldtype: 'Link',
                    options: 'Company',
                    fieldname: 'company',
                    label: 'Company',
                    reqd: 1,
                    onchange: () => {
                        if (setting_controls) return;
                        setCompany(company_control.get_value(), false);
                        if (warehouse_control) {
                            warehouse_control.df.get_query = () => ({ filters: { company: getCompany() } });
                        }
                    }
                },
                render_input: true
            });

            customer_control = frappe.ui.form.make_control({
                parent: $root.find('#pob-customer-control'),
                df: {
                    fieldtype: 'Link',
                    options: 'Customer',
                    fieldname: 'customer',
                    label: 'Customer',
                    reqd: 1,
                    onchange: () => {
                        if (setting_controls) return;
                        setCustomer(customer_control.get_value(), false);
                    }
                },
                render_input: true
            });

            warehouse_control = frappe.ui.form.make_control({
                parent: $root.find('#pob-warehouse-control'),
                df: {
                    fieldtype: 'Link',
                    options: 'Warehouse',
                    fieldname: 'warehouse',
                    label: 'Warehouse',
                    reqd: 1,
                    get_query: () => ({ filters: { company: getCompany() } }),
                    onchange: () => {
                        if (setting_controls) return;
                        setWarehouse(warehouse_control.get_value(), false);
                    }
                },
                render_input: true
            });

            price_list_control = frappe.ui.form.make_control({
                parent: $root.find('#pob-price-list-control'),
                df: {
                    fieldtype: 'Link',
                    options: 'Price List',
                    fieldname: 'price_list',
                    label: 'Price List',
                    reqd: 1,
                    get_query: () => ({ filters: { selling: 1 } }),
                    onchange: () => {
                        if (setting_controls) return;
                        setPriceList(price_list_control.get_value(), false);
                    }
                },
                render_input: true
            });

            const defaultCompany = frappe.defaults.get_default('company');
            if (defaultCompany) setCompany(defaultCompany);
            setPriceList(state.price_list || 'Standard Selling');

            frappe.call({
                method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_billing_defaults_v30',
                callback: r => {
                    const d = r.message || {};
                    setCompany(d.company || getCompany() || defaultCompany || '');
                    setWarehouse(d.warehouse || getWarehouse() || '');
                    setPriceList(d.price_list || getPriceList() || 'Standard Selling');
                }
            });
        }

        make_controls();
    }

    function inject_v32_styles() {
        if ($('#pob32-counter-ux-style').length) return;
        $('head').append(`
            <style id="pob32-counter-ux-style">
                .pob-root { --pob-row-h: 30px; --pob-font: 12px; font-size: var(--pob-font); }
                .pob-link-controls { position: sticky; top: 0; z-index: 5; background: var(--fg-color, #fff); padding: 4px 0 6px; border-bottom: 1px solid #e5e7eb; }
                .pob-root .control-label { font-size: 11px; margin-bottom: 2px; color: #555; }
                .pob-root .form-control, .pob-root input { height: 28px; min-height: 28px; padding: 3px 6px; font-size: 12px; }
                .pob-root .btn { padding: 3px 8px; font-size: 12px; line-height: 1.3; }
                .pob-grid { font-size: 12px; table-layout: fixed; }
                .pob-grid th, .pob-grid td { padding: 3px 5px !important; vertical-align: middle !important; line-height: 1.2; }
                .pob-grid tbody tr { height: var(--pob-row-h); }
                .pob-grid input { height: 24px; padding: 2px 4px; font-size: 12px; }
                .pob-suggestions { max-height: 320px; overflow-y: auto; border: 1px solid #cbd5e1; box-shadow: 0 10px 24px rgba(0,0,0,0.12); background: var(--fg-color, #fff); z-index: 20; }
                .pob-suggestion { padding: 5px 8px !important; border-bottom: 1px solid #edf2f7; cursor: pointer; line-height: 1.25; }
                .pob-suggestion.active, .pob-suggestion:hover { background: #eef2ff; }
                .pob-sug-main { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
                .pob-sug-code { font-weight: 700; }
                .pob-sug-meta { font-size: 11px; color: #555; display: flex; gap: 10px; flex-wrap: wrap; }
                .pob-batch-btn { min-width: 92px; height: 24px; padding: 1px 6px !important; font-size: 11px !important; white-space: nowrap; }
                .pob32-batch-list .list-group-item { padding: 6px 8px; cursor: pointer; }
                .pob32-batch-list .list-group-item:hover, .pob32-batch-list .list-group-item.active { background: #eef2ff; }
            </style>
        `);
    }

    function safeItemLabel(x) {
        const code = x.item_code || '';
        const name = x.item_name || '';
        return code === name ? code : `${code} ${name}`.trim();
    }

    function normalizeBatchRows(rows) {
        return (rows || []).map(r => ({
            batch_no: r.batch_no || r.batch || r.name,
            expiry_date: r.expiry_date || r.exp,
            qty: Number(r.qty || r.available_qty || r.actual_qty || 0),
            available_qty: Number(r.available_qty || r.actual_qty || r.qty || 0),
            purchase_rate: Number(r.purchase_rate || r.rate || 0),
            last_sale_rate: Number(r.last_sale_rate || 0)
        })).filter(r => r.batch_no);
    }

    function batchLabel(batch) {
        if (!batch || !batch.batch_no) return 'Select';
        const exp = batch.expiry_date ? String(batch.expiry_date).slice(0, 10) : '-';
        const qty = batch.qty || batch.available_qty || batch.actual_qty || 0;
        return `${batch.batch_no} | ${exp} | ${qty}`;
    }

    function getCurrentWarehouse() {
        return typeof getWarehouse === 'function' ? getWarehouse() : ($warehouse.val() || state.warehouse || '');
    }

    function getCurrentCustomer() {
        return typeof getCustomer === 'function' ? getCustomer() : ($customer.val() || state.customer || '');
    }

    // V32.3.1 compatibility wrapper: all batch fetch behavior goes through V323.
    async function fetchBatchesForItem(item_code) {
        return fetchBatchesForItemV323(item_code);
    }

    function highlightSuggestion() {
        const $items = $suggestions.find('.pob-suggestion');
        $items.removeClass('active');
        const $active = $items.eq(selectedSuggestionIndex);
        $active.addClass('active');

        if ($active.length && $suggestions[0]) {
            const container = $suggestions[0];
            const active = $active[0];
            if (active.offsetTop < container.scrollTop) container.scrollTop = active.offsetTop;
            else if (active.offsetTop + active.offsetHeight > container.scrollTop + container.clientHeight) {
                container.scrollTop = active.offsetTop + active.offsetHeight - container.clientHeight;
            }
        }
    }


    function hasMissingBatchRows() {
        return state.items.some(row => {
            const batchRows = row.batch_rows || [];
            const hasBatch = batchRows.length && batchRows[0].batch_no;
            return row.has_batch_no && !hasBatch;
        });
    }

    function validateBeforeSubmit(payload, done) {
        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.validate_billing_party_v30',
            args: { customer: payload.customer, warehouse: payload.warehouse, company: payload.company },
            callback: r => {
                const res = r.message || {};
                if (!res.valid) {
                    frappe.msgprint((res.errors || ['Validation failed']).join('<br>'));
                    done(false);
                    return;
                }
                done(true);
            },
            error: () => {
                frappe.msgprint('Preflight validation failed. Please check server logs.');
                done(false);
            }
        });
    }

    inject_v32_styles();


    // =============================================================
    // V32.1 Operator UX Hardening
    // V32.1.1 Cleanup: no F4 conflict, no modal batch helper, synchronous renderGrid, namespaced handlers
    // =============================================================

    let selectedGridIndex = 0;

    function inject_v32_1_styles() {
        if ($('#pob32-1-counter-ux-style').length) return;

        $('head').append(`
            <style id="pob32-1-counter-ux-style">
                .pob-sticky-totals {
                    position: sticky;
                    bottom: 0;
                    z-index: 12;
                    background: var(--fg-color, #fff);
                    border-top: 1px solid #d1d5db;
                    padding: 6px 10px;
                    display: flex;
                    justify-content: flex-end;
                    gap: 20px;
                    font-weight: 600;
                    box-shadow: 0 -2px 8px rgba(0,0,0,0.05);
                }

                .pob-inline-batch {
                    min-width: 135px;
                    max-width: 180px;
                    height: 24px !important;
                    padding: 1px 4px !important;
                    font-size: 11px !important;
                }

                .pob-grid tbody tr.pob-selected-row {
                    outline: 2px solid #4f46e5;
                    outline-offset: -2px;
                    background: #f5f7ff;
                }

                .pob-suggestions {
                    max-height: 240px !important;
                }

                .pob-batch-chip {
                    font-weight: 600;
                    color: #1d4ed8;
                }

                .pob-exp-chip {
                    font-weight: 600;
                }

                .pob-exp-soon {
                    color: #b91c1c;
                    font-weight: 700;
                }

                .pob-margin-good {
                    color: #047857;
                    font-weight: 700;
                }

                .pob-margin-warning {
                    color: #b45309;
                    font-weight: 700;
                }

                .pob-margin-danger {
                    color: #b91c1c;
                    font-weight: 700;
                }

                .pob-intelligence-panel {
                    position: fixed;
                    right: 8px;
                    top: 90px;
                    width: 320px;
                    max-width: 30vw;
                    height: calc(100vh - 110px);
                    overflow-y: auto;
                    background: var(--fg-color, #fff);
                    border: 1px solid #d1d5db;
                    z-index: 15;
                    padding: 8px;
                    box-shadow: 0 10px 24px rgba(0,0,0,0.08);
                }

                .pob-root.has-intel-dock {
                    padding-right: 330px;
                }

                @media (max-width: 1100px) {
                    .pob-intelligence-panel {
                        position: static;
                        width: auto;
                        max-width: none;
                        height: auto;
                        margin-top: 8px;
                    }
                    .pob-root.has-intel-dock {
                        padding-right: 0;
                    }
                }
            </style>
        `);
    }

    function ensureStickyTotals() {
        if ($root.find('.pob-sticky-totals').length) return;

        const totals = $(`
            <div class="pob-sticky-totals">
                <span>Lines: <span class="pob-line-count">0</span></span>
                <span>Qty: <span class="pob-total-qty">0</span></span>
                <span>Total: <span class="pob-grand-total">0.00</span></span>
            </div>
        `);

        $root.append(totals);
    }

    function ensureIntelligenceDock() {
        const existing = $root.find('.pob-intelligence-panel, .pob-intelligence, .pob-intel').first();

        if (existing.length) {
            existing.addClass('pob-intelligence-panel');
            $root.addClass('has-intel-dock');
        }
    }

    function marginClass(margin) {
        margin = Number(margin || 0);

        if (margin < 5) return 'pob-margin-danger';
        if (margin < 12) return 'pob-margin-warning';

        return 'pob-margin-good';
    }

    function isNearExpiry(expiry_date) {
        if (!expiry_date || !frappe.datetime) return false;

        try {
            const exp = frappe.datetime.str_to_obj(String(expiry_date).slice(0, 10));
            const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
            const diff = frappe.datetime.get_day_diff(exp, today);
            return diff <= 30;
        } catch (e) {
            return false;
        }
    }

    function parseQuickQty(txt) {
        txt = (txt || '').trim().toLowerCase();

        const strip = txt.match(/^(\d+)s$/);
        if (strip) {
            return {
                qty: Number(strip[1] || 1),
                uom: 'STRIP'
            };
        }

        const box = txt.match(/^(\d+)b$/);
        if (box) {
            return {
                qty: Number(box[1] || 1),
                uom: 'BOX'
            };
        }

        const tab = txt.match(/^(\d+)t$/);
        if (tab) {
            return {
                qty: Number(tab[1] || 1),
                uom: 'TABLET'
            };
        }

        const star = txt.match(/^\*(\d+)$/);
        if (star) {
            return {
                qty: Number(star[1] || 1),
                uom: null
            };
        }

        return {
            qty: Number(txt || 1),
            uom: null
        };
    }

    function renderBatchOptions(row) {
        const batches = row.available_batches || row.batch_options || row.batch_rows || [];

        if (!batches.length) {
            return `<option value="">No Batch Found</option>`;
        }

        return batches.map(b => {
            const selected = (row.batch_no || ((row.batch_rows || [])[0] || {}).batch_no) === b.batch_no
                ? 'selected'
                : '';

            const exp = b.expiry_date || '-';
            const qty = b.available_qty || b.qty || 0;
            const near = isNearExpiry(exp) ? ' âš ' : '';

            return `
                <option value="${b.batch_no}" ${selected}>
                    ${b.batch_no} | ${exp}${near} | Qty ${qty}
                </option>
            `;
        }).join('');
    }

    async function hydrateRowBatches(row) {
        if (!row || !row.item_code) return row;

        if (row.available_batches && row.available_batches.length) {
            return row;
        }

        const batches = await fetchBatchesForItemV323(row.item_code);
        row.available_batches = batches;

        if (!row.batch_no && batches.length) {
            row.batch_rows = [batches[0]];
            row.batch_no = batches[0].batch_no;
            row.expiry_date = batches[0].expiry_date;
        }

        return row;
    }

    function selectGridRow(idx) {
        selectedGridIndex = Math.max(0, Math.min(idx, state.items.length - 1));
        $tbody.find('tr').removeClass('pob-selected-row');
        $tbody.find('tr').eq(selectedGridIndex).addClass('pob-selected-row');
    }

    function getSelectedGridRow() {
        if (!state.items.length) return null;
        return Math.max(0, Math.min(selectedGridIndex || 0, state.items.length - 1));
    }

    async function focusInlineBatch(idx) {
        idx = idx == null ? getSelectedGridRow() : idx;
        if (idx == null) return;

        await hydrateRowBatches(state.items[idx]);
        renderGrid();

        setTimeout(() => {
            $tbody.find(`.pob-inline-batch[data-idx="${idx}"]`).focus();
        }, 50);
    }

    function applyQuickQtyToSelected(txt) {
        const idx = getSelectedGridRow();
        if (idx == null) return false;

        const parsed = parseQuickQty(txt);
        if (!parsed.qty || parsed.qty <= 0) return false;

        const row = state.items[idx];
        row.qty = parsed.qty;
        row.uom_hint = parsed.uom;
        renderGrid();
        return true;
    }

    // V32.3.1 compatibility wrapper: all exact-add behavior goes through V323.
    function enhanceExactBarcodeAdd(txt, rows) {
        const exact = shouldAutoAddExactV323(txt, rows);
        if (!exact) return false;
        addExactItemWithBatchesV323(exact);
        return true;
    }

    inject_v32_1_styles();


    // =============================================================
    // V32.2 No-Mouse Navigation Engine for Marg-style operators
    // =============================================================

    const NAV_COLUMNS = ['batch', 'qty', 'free', 'rate', 'disc'];
    let navState = {
        mode: 'search',
        row: 0,
        col: 1, // default to qty
        lastFocusSelector: '.pob-search'
    };

    function inject_v32_2_styles() {
        if ($('#pob32-2-nav-style').length) return;

        $('head').append(`
            <style id="pob32-2-nav-style">
                .pob-nav-focus {
                    outline: 2px solid #2563eb !important;
                    outline-offset: -1px;
                    background: #eff6ff !important;
                }
                .pob-grid tbody tr.pob-selected-row td {
                    background: #f8fafc;
                }
                .pob-hotkey-help {
                    font-size: 11px;
                    color: #475569;
                    border-top: 1px solid #e5e7eb;
                    padding-top: 4px;
                    margin-top: 4px;
                }
            </style>
        `);
    }

    function navClamp() {
        if (!state.items.length) {
            navState.row = 0;
            navState.col = 1;
            return;
        }

        navState.row = Math.max(0, Math.min(navState.row, state.items.length - 1));
        navState.col = Math.max(0, Math.min(navState.col, NAV_COLUMNS.length - 1));
    }

    function cellSelector(row, col) {
        const column = NAV_COLUMNS[col];

        if (column === 'batch') return `.pob-inline-batch[data-idx="${row}"]`;
        if (column === 'qty') return `.pob-grid tbody tr[data-idx="${row}"] .pob-row-qty`;
        if (column === 'free') return `.pob-grid tbody tr[data-idx="${row}"] .pob-row-free`;
        if (column === 'rate') return `.pob-grid tbody tr[data-idx="${row}"] .pob-row-rate`;
        if (column === 'disc') return `.pob-grid tbody tr[data-idx="${row}"] .pob-row-disc`;

        return `.pob-grid tbody tr[data-idx="${row}"] .pob-row-qty`;
    }

    function clearNavFocus() {
        $root.find('.pob-nav-focus').removeClass('pob-nav-focus');
        $tbody.find('tr').removeClass('pob-selected-row');
    }

    function focusSearch(select = true) {
        navState.mode = 'search';
        navState.lastFocusSelector = '.pob-search';
        clearNavFocus();
        $search.focus();
        if (select) $search.select();
    }

    function focusCustomer() {
        navState.mode = 'customer';
        if (customer_control && customer_control.$input) {
            customer_control.$input.focus();
            customer_control.$input.select();
        }
    }

    function focusCell(row = navState.row, col = navState.col, select = true) {
        if (!state.items.length) {
            focusSearch();
            return;
        }

        navState.mode = 'grid';
        navState.row = row;
        navState.col = col;
        navClamp();

        clearNavFocus();

        const selector = cellSelector(navState.row, navState.col);
        const $el = $root.find(selector);

        selectedGridIndex = navState.row;
        selectGridRow(navState.row);

        if ($el.length) {
            $el.addClass('pob-nav-focus');
            $el.focus();
            if (select && $el.is('input')) $el.select();
            navState.lastFocusSelector = selector;
        }
    }

    function restoreNavFocus() {
        setTimeout(() => {
            if (navState.mode === 'grid') {
                focusCell(navState.row, navState.col, false);
            } else if (navState.mode === 'customer') {
                focusCustomer();
            } else {
                focusSearch(false);
            }
        }, 30);
    }

    function moveCell(rowDelta, colDelta) {
        if (!state.items.length) {
            focusSearch();
            return;
        }

        let row = navState.row + rowDelta;
        let col = navState.col + colDelta;

        if (col >= NAV_COLUMNS.length) {
            col = 0;
            row += 1;
        }

        if (col < 0) {
            col = NAV_COLUMNS.length - 1;
            row -= 1;
        }

        if (row >= state.items.length) {
            focusSearch();
            return;
        }

        if (row < 0) {
            focusSearch();
            return;
        }

        focusCell(row, col);
    }

    function commitFocusedCell() {
        const $active = $(document.activeElement);
        if (!$active.length) return;

        if ($active.hasClass('pob-row-qty') ||
            $active.hasClass('pob-row-free') ||
            $active.hasClass('pob-row-rate') ||
            $active.hasClass('pob-row-disc') ||
            $active.hasClass('pob-inline-batch')) {
            $active.trigger('change');
        }
    }

    function deleteSelectedLine() {
        const idx = getSelectedGridRow();

        if (idx == null || !state.items.length) return;

        state.items.splice(idx, 1);
        navState.row = Math.max(0, idx - 1);
        renderGrid();
        restoreNavFocus();
    }

    function duplicateSelectedLine() {
        const idx = getSelectedGridRow();

        if (idx == null || !state.items[idx]) return;

        const src = state.items[idx];

        state.items.splice(idx + 1, 0, Object.assign({}, src, {
            batch_rows: [...(src.batch_rows || [])],
            available_batches: [...(src.available_batches || [])]
        }));

        navState.row = idx + 1;
        renderGrid();
        restoreNavFocus();
    }

    function addHotkeyHelp() {
        if ($root.find('.pob-hotkey-help').length) return;

        $root.find('.pob-status').after(`
            <div class="pob-hotkey-help">
                Ctrl+Shift+R Clear Cache Â· F3 Customer Â· F5 Search Â· F2 Batch Â· F6 Qty Â· F7 Disc Â· Ctrl+S Invoice Â· F8 Hold Â· F9 Recall Â· Del Delete Â· Ctrl+D Duplicate Â· Esc Search
            </div>
        `);
    }

    function operatorSubmitFromKeyboard() {
        const $btn = $root.find('.pob-submit');
        if ($btn.length) $btn.click();
    }

    function operatorHoldFromKeyboard() {
        const $btn = $root.find('.pob-hold');
        if ($btn.length) $btn.click();
    }

    function operatorRecallFromKeyboard() {
        const $btn = $root.find('.pob-recall');
        if ($btn.length) $btn.click();
    }

    function handleGridKey(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            commitFocusedCell();
            moveCell(0, 1);
            return true;
        }

        if (e.key === 'Tab') {
            e.preventDefault();
            commitFocusedCell();
            moveCell(0, e.shiftKey ? -1 : 1);
            return true;
        }

        if (e.key === 'ArrowRight') {
            e.preventDefault();
            commitFocusedCell();
            moveCell(0, 1);
            return true;
        }

        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            commitFocusedCell();
            moveCell(0, -1);
            return true;
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            commitFocusedCell();
            moveCell(1, 0);
            return true;
        }

        if (e.key === 'ArrowUp') {
            e.preventDefault();
            commitFocusedCell();
            moveCell(-1, 0);
            return true;
        }

        if (e.key === 'Home') {
            e.preventDefault();
            focusCell(navState.row, 0);
            return true;
        }

        if (e.key === 'End') {
            e.preventDefault();
            focusCell(navState.row, NAV_COLUMNS.length - 1);
            return true;
        }

        if (e.key === 'Delete') {
            e.preventDefault();
            deleteSelectedLine();
            return true;
        }

        return false;
    }

    function bindNoMouseNavigation() {
        $(document).off('keydown.pob32nav').on('keydown.pob32nav', function(e) {
            const $target = $(e.target);
            const inOperator = $target.closest('.pob-root').length > 0;
            const inModal = $target.closest('.modal').length > 0;

            if (inModal) return;

            // Global operator keys.
            if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'r') {
                e.preventDefault();
                resetFastBillingIndexedDBV331().then(() => {
                    status('Local billing cache cleared. Click Load Cache.', 'green');
                });
                return;
            }

            if (e.ctrlKey && e.key.toLowerCase() === 's') {
                e.preventDefault();
                operatorSubmitFromKeyboard();
                return;
            }

            if (e.key === 'F3') {
                e.preventDefault();
                focusCustomer();
                return;
            }

            if (e.key === 'F5') {
                e.preventDefault();
                focusSearch();
                return;
            }

            if (e.key === 'F8') {
                e.preventDefault();
                operatorHoldFromKeyboard();
                return;
            }

            if (e.key === 'F9') {
                e.preventDefault();
                operatorRecallFromKeyboard();
                return;
            }

            if (e.key === 'Escape') {
                e.preventDefault();
                $suggestions.hide().empty();
                focusSearch();
                return;
            }

            if (!inOperator) return;

            // Grid-specific shortcuts.
            if (e.key === 'F2') {
                e.preventDefault();
                focusCell(getSelectedGridRow() ?? 0, 0);
                return;
            }

            if (e.key === 'F6') {
                e.preventDefault();
                focusCell(getSelectedGridRow() ?? 0, 1);
                return;
            }

            if (e.key === 'F7') {
                e.preventDefault();
                focusCell(getSelectedGridRow() ?? 0, 4);
                return;
            }

            if (e.ctrlKey && e.key.toLowerCase() === 'd') {
                e.preventDefault();
                duplicateSelectedLine();
                return;
            }

            if (e.ctrlKey && e.key.toLowerCase() === 'l') {
                e.preventDefault();
                deleteSelectedLine();
                return;
            }

            if (
                $target.hasClass('pob-row-qty') ||
                $target.hasClass('pob-row-free') ||
                $target.hasClass('pob-row-rate') ||
                $target.hasClass('pob-row-disc') ||
                $target.hasClass('pob-inline-batch')
            ) {
                if (handleGridKey(e)) return;
            }
        });
    }

    inject_v32_2_styles();

    // =============================================================
    // V32.3 Batch + Search Intelligence Stabilization
    // V32.3.1 Cleanup: V323 batch/search paths are authoritative; legacy helpers are compatibility wrappers
    // =============================================================

    const batchCacheV323 = {};

    function batchCacheKey(item_code, warehouse) {
        return `${item_code || ''}::${warehouse || ''}`;
    }

    function cacheBatchesForItem(item_code, warehouse, batches) {
        const normalized = normalizeBatchRows(batches || []);
        batchCacheV323[batchCacheKey(item_code, warehouse)] = normalized;
        return normalized;
    }

    function getCachedBatchesForItem(item_code, warehouse) {
        return batchCacheV323[batchCacheKey(item_code, warehouse)] || [];
    }

    function chooseFEFOBatch(batches) {
        batches = normalizeBatchRows(batches || []).filter(b => Number(b.available_qty || b.qty || 0) > 0);

        if (!batches.length) return null;

        return batches.sort((a, b) => {
            const ae = a.expiry_date || '9999-12-31';
            const be = b.expiry_date || '9999-12-31';
            if (ae < be) return -1;
            if (ae > be) return 1;
            return String(a.batch_no || '').localeCompare(String(b.batch_no || ''));
        })[0];
    }

    function enrichSearchRowsWithBatchIntel(rows) {
        const warehouse = getCurrentWarehouse ? getCurrentWarehouse() : (state.warehouse || '');

        return (rows || []).map(row => {
            const cached = getCachedBatchesForItem(row.item_code, warehouse);
            const best = chooseFEFOBatch(cached);

            if (best) {
                row.best_batch = row.best_batch || best.batch_no;
                row.best_expiry = row.best_expiry || best.expiry_date;
                row.actual_qty = row.actual_qty || best.available_qty || best.qty || 0;
            }

            row.ptr = row.ptr || row.rate || row.standard_rate || row.price_list_rate || 0;
            row.mrp = row.mrp || row.pharma_mrp || row.maximum_retail_price || 0;
            row.last_customer_rate = row.last_customer_rate || row.last_rate || row.customer_last_rate || '';
            row.margin_percent = row.margin_percent || row.gross_margin_percent || 0;

            return row;
        });
    }

    async function fetchBatchesForItemV323(item_code) {
        const warehouse = getCurrentWarehouse ? getCurrentWarehouse() : (state.warehouse || '');
        const cached = getCachedBatchesForItem(item_code, warehouse);

        if (cached.length) return cached;

        if (window.PharmaFastBillingV241 && window.PharmaFastBillingV241.localFEFO) {
            const localRows = normalizeBatchRows(window.PharmaFastBillingV241.localFEFO(item_code, warehouse, 999));
            if (localRows.length) {
                return cacheBatchesForItem(item_code, warehouse, localRows);
            }
        }

        return new Promise(resolve => {
            frappe.call({
                method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_batch_history',
                args: { item_code, warehouse },
                callback: r => resolve(cacheBatchesForItem(item_code, warehouse, r.message || [])),
                error: () => resolve([])
            });
        });
    }

    async function ensureRowBatchesV323(row) {
        if (!row || !row.item_code) return [];

        const warehouse = getCurrentWarehouse ? getCurrentWarehouse() : (state.warehouse || '');
        row.available_batches = row.available_batches && row.available_batches.length
            ? normalizeBatchRows(row.available_batches)
            : await fetchBatchesForItemV323(row.item_code);

        const currentBatchNo = row.batch_no || ((row.batch_rows || [])[0] || {}).batch_no;

        if (currentBatchNo) {
            const current = (row.available_batches || []).find(b => b.batch_no === currentBatchNo);
            if (current) {
                row.batch_no = current.batch_no;
                row.expiry_date = current.expiry_date;
                row.batch_rows = [current];
                return row.available_batches;
            }
        }

        const fefo = chooseFEFOBatch(row.available_batches || []);

        if (fefo) {
            row.batch_no = fefo.batch_no;
            row.expiry_date = fefo.expiry_date;
            row.batch_rows = [fefo];
        }

        return row.available_batches || [];
    }

    function searchRowRate(row) {
        return row.ptr || row.rate || row.standard_rate || row.price_list_rate || 0;
    }

    function searchRowMrp(row) {
        return row.mrp || row.pharma_mrp || row.maximum_retail_price || 0;
    }

    function searchStock(row) {
        return row.actual_qty || row.stock_qty || row.available_qty || 0;
    }

    function searchMargin(row) {
        return Number(row.margin_percent || row.gross_margin_percent || 0);
    }

    // V32.3.1 backend search field contract:

    // =============================================================
    // V33 Virtual Grid Navigation Engine
    // Goal: Spreadsheet-like row/cell editing without full-grid redraws
    // during normal qty/free/rate/discount/batch edits.
    // =============================================================

    const V33_GRID_COLUMNS = ['batch', 'qty', 'free', 'rate', 'disc'];
    let v33GridReady = false;

    function v33Money(v) {
        return (Number(v || 0)).toFixed(2);
    }

    function v33GetRowElement(idx) {
        return $tbody.find(`tr[data-idx="${idx}"]`);
    }

    function v33GetInput(idx, col) {
        const $row = v33GetRowElement(idx);
        const c = V33_GRID_COLUMNS[col];

        if (c === 'batch') return $row.find('.pob-inline-batch');
        if (c === 'qty') return $row.find('.pob-row-qty');
        if (c === 'free') return $row.find('.pob-row-free');
        if (c === 'rate') return $row.find('.pob-row-rate');
        if (c === 'disc') return $row.find('.pob-row-disc');

        return $row.find('.pob-row-qty');
    }

    function v33CaptureFocus() {
        const active = document.activeElement;
        const $active = $(active);
        const $row = $active.closest('tr[data-idx]');

        if (!$row.length) {
            return {
                mode: $active.hasClass('pob-search') ? 'search' : 'other',
                row: typeof navState !== 'undefined' ? navState.row : 0,
                col: typeof navState !== 'undefined' ? navState.col : 1,
                selector: null
            };
        }

        const idx = Number($row.data('idx'));
        let col = 1;

        if ($active.hasClass('pob-inline-batch')) col = 0;
        else if ($active.hasClass('pob-row-qty')) col = 1;
        else if ($active.hasClass('pob-row-free')) col = 2;
        else if ($active.hasClass('pob-row-rate')) col = 3;
        else if ($active.hasClass('pob-row-disc')) col = 4;

        return { mode: 'grid', row: idx, col };
    }

    function v33RestoreFocus(snapshot, select = false) {
        if (!snapshot) return;

        setTimeout(() => {
            if (snapshot.mode === 'grid') {
                if (typeof focusCell === 'function') {
                    focusCell(snapshot.row, snapshot.col, select);
                } else {
                    const $input = v33GetInput(snapshot.row, snapshot.col);
                    if ($input.length) {
                        $input.focus();
                        if (select && $input.is('input')) $input.select();
                    }
                }
                return;
            }

            if (snapshot.mode === 'search') {
                $search.focus();
            }
        }, 0);
    }

    function v33CalcLine(row) {
        const gross = Number(row.qty || 0) * Number(row.rate || 0);
        const discount = gross * Number(row.discount_percentage || 0) / 100;
        row.amount = gross - discount;
        return row.amount;
    }

    function v33UpdateTotalsOnly() {
        const totals = calcTotals();
        $root.find('.pob-line-count').text(state.items.length);
        $root.find('.pob-total-qty').text(totals.qty);
        $root.find('.pob-grand-total').text(v33Money(totals.grand_total));
        window.__current_pharma_quick_sale_payload = collectPayload();
    }

    function v33UpdateRowOnly(idx) {
        const row = state.items[idx];
        if (!row) return;

        v33CalcLine(row);

        const $row = v33GetRowElement(idx);
        if (!$row.length) return;

        const batch = (row.batch_rows || [])[0] || {};
        const expValue = batch.expiry_date || row.expiry_date || '';
        const margin = row.margin_percent || row.gross_margin_percent || 0;
        const marginCls = typeof marginClass === 'function' ? marginClass(margin) : '';

        $row.find('.pob-row-qty').val(row.qty || 0);
        $row.find('.pob-row-free').val(row.free_qty || 0);
        $row.find('.pob-row-rate').val(row.rate || 0);
        $row.find('.pob-row-disc').val(row.discount_percentage || 0);
        $row.find('.pob-row-amount')
            .text(v33Money(row.amount))
            .removeClass('pob-margin-good pob-margin-warning pob-margin-danger')
            .addClass(marginCls);

        const $expCell = $row.find('td').eq(3);
        $expCell
            .text(expValue || '')
            .toggleClass('pob-exp-soon', typeof isNearExpiry === 'function' ? isNearExpiry(expValue) : false);

        v33UpdateTotalsOnly();
    }

    function v33ReadRowInputs(idx) {
        const row = state.items[idx];
        const $row = v33GetRowElement(idx);

        if (!row || !$row.length) return;

        const rawQty = $row.find('.pob-row-qty').val();
        const parsedQty = typeof parseQuickQty === 'function'
            ? parseQuickQty(rawQty)
            : {qty: Number(rawQty || 0), uom: null};

        row.qty = Number(parsedQty.qty || 0);
        row.uom_hint = parsedQty.uom;
        row.free_qty = Number($row.find('.pob-row-free').val() || 0);
        row.rate = Number($row.find('.pob-row-rate').val() || 0);
        row.discount_percentage = Number($row.find('.pob-row-disc').val() || 0);

        if (row.batch_no && row.available_batches && row.available_batches.length) {
            const selected = row.available_batches.find(b => b.batch_no === row.batch_no);
            if (selected) row.batch_rows = [selected];
        }
    }

    function v33CommitCell(idx = null) {
        if (idx == null) {
            const snap = v33CaptureFocus();
            idx = snap && snap.mode === 'grid' ? snap.row : null;
        }

        if (idx == null) return;

        v33ReadRowInputs(idx);
        v33UpdateRowOnly(idx);
    }

    function v33RenderRowHtml(row, idx) {
        if ((!row.batch_rows || !row.batch_rows.length) && row.available_batches && row.available_batches.length) {
            const fefo = typeof chooseFEFOBatch === 'function' ? chooseFEFOBatch(row.available_batches) : null;
            if (fefo) {
                row.batch_no = fefo.batch_no;
                row.expiry_date = fefo.expiry_date;
                row.batch_rows = [fefo];
            }
        }

        const batch = (row.batch_rows || [])[0] || {};
        const expValue = batch.expiry_date || row.expiry_date || '';
        const expClass = typeof isNearExpiry === 'function' && isNearExpiry(expValue) ? 'pob-exp-soon' : '';
        const margin = row.margin_percent || row.gross_margin_percent || 0;
        const marginCls = typeof marginClass === 'function' ? marginClass(margin) : '';

        v33CalcLine(row);

        return `<tr data-idx="${idx}">
            <td>${idx + 1}</td>
            <td><b>${row.item_code}</b><br><small>${row.item_name || ''}</small></td>
            <td>
                <select class="form-control input-xs pob-inline-batch" data-idx="${idx}">
                    ${typeof renderBatchOptions === 'function' ? renderBatchOptions(row) : ''}
                </select>
                ${(!row.available_batches || !row.available_batches.length) ? '<small class="text-warning">No lot</small>' : ''}
            </td>
            <td class="${expClass}">${expValue || ''}</td>
            <td><input class="form-control input-xs pob-row-qty" value="${row.qty || 1}"></td>
            <td><input class="form-control input-xs pob-row-free" value="${row.free_qty || 0}"></td>
            <td><input class="form-control input-xs pob-row-rate" value="${row.rate || 0}"></td>
            <td><input class="form-control input-xs pob-row-disc" value="${row.discount_percentage || 0}"></td>
            <td>${row.item_tax_template || ''}</td>
            <td class="pob-row-amount ${marginCls}">${v33Money(row.amount)}</td>
            <td><button class="btn btn-xs btn-danger pob-row-del">Ã—</button></td>
        </tr>`;
    }

    function v33FullRenderGrid(focusLast = false) {
        const snapshot = v33CaptureFocus();

        $tbody.empty();

        state.items.forEach((row, idx) => {
            $tbody.append(v33RenderRowHtml(row, idx));
        });

        v33UpdateTotalsOnly();

        if (state.items.length && typeof selectGridRow === 'function') {
            const targetRow = focusLast ? state.items.length - 1 : Math.min(snapshot.row || 0, state.items.length - 1);
            selectGridRow(targetRow);
        }

        if (focusLast) {
            if (typeof focusCell === 'function') focusCell(state.items.length - 1, 1, true);
        } else {
            v33RestoreFocus(snapshot, false);
        }
    }

    function v33AddRow(row, focus = true) {
        state.items.push(row);
        const idx = state.items.length - 1;

        $tbody.append(v33RenderRowHtml(row, idx));
        v33UpdateTotalsOnly();

        selectedGridIndex = idx;

        if (typeof navState !== 'undefined') {
            navState.row = idx;
            navState.col = 1;
        }

        if (typeof selectGridRow === 'function') selectGridRow(idx);
        if (focus && typeof focusCell === 'function') focusCell(idx, 1, true);
    }

    function v33ReindexGrid() {
        $tbody.find('tr').each(function(idx) {
            $(this).attr('data-idx', idx);
            $(this).find('td:first').text(idx + 1);
            $(this).find('.pob-inline-batch').attr('data-idx', idx);
        });
    }

    function v33DeleteRow(idx) {
        if (idx == null || !state.items.length) return;

        state.items.splice(idx, 1);
        v33GetRowElement(idx).remove();
        v33ReindexGrid();
        v33UpdateTotalsOnly();

        if (typeof navState !== 'undefined') {
            navState.row = Math.max(0, Math.min(idx, state.items.length - 1));
            navState.col = 1;
        }

        if (state.items.length && typeof focusCell === 'function') {
            focusCell(navState.row, navState.col, true);
        } else if (typeof focusSearch === 'function') {
            focusSearch();
        }
    }

    function v33DuplicateRow(idx) {
        const src = state.items[idx];
        if (!src) return;

        const copy = Object.assign({}, src, {
            batch_rows: [...(src.batch_rows || [])],
            available_batches: [...(src.available_batches || [])]
        });

        state.items.splice(idx + 1, 0, copy);

        const $existing = v33GetRowElement(idx);
        const html = v33RenderRowHtml(copy, idx + 1);

        if ($existing.length) $existing.after(html);
        else $tbody.append(html);

        v33ReindexGrid();
        v33UpdateTotalsOnly();

        if (typeof navState !== 'undefined') {
            navState.row = idx + 1;
            navState.col = 1;
        }

        if (typeof focusCell === 'function') focusCell(idx + 1, 1, true);
    }

    function bindV33GridEvents() {
        if (v33GridReady) return;
        v33GridReady = true;

        $tbody.off('input.v33grid').on('input.v33grid', '.pob-row-qty,.pob-row-free,.pob-row-rate,.pob-row-disc', function() {
            const idx = Number($(this).closest('tr').data('idx'));
            v33ReadRowInputs(idx);
            v33UpdateRowOnly(idx);
        });

        $tbody.off('change.v33grid').on('change.v33grid', '.pob-row-qty,.pob-row-free,.pob-row-rate,.pob-row-disc', function() {
            const idx = Number($(this).closest('tr').data('idx'));
            v33CommitCell(idx);
        });

        $tbody.off('click.v33row').on('click.v33row', 'tr', function() {
            const idx = Number($(this).data('idx'));
            if (typeof selectGridRow === 'function') selectGridRow(idx);
            if (typeof navState !== 'undefined') navState.row = idx;
        });

        $tbody.off('click.v33delete').on('click.v33delete', '.pob-row-del', function(e) {
            e.preventDefault();
            const idx = Number($(this).closest('tr').data('idx'));
            v33DeleteRow(idx);
        });

        $tbody.off('change.v33batch').on('change.v33batch', '.pob-inline-batch', function() {
            const idx = Number($(this).data('idx'));
            const row = state.items[idx];
            const batch_no = $(this).val();

            if (!row) return;

            const batch = (row.available_batches || []).find(x => x.batch_no === batch_no);

            if (!batch) return;

            row.batch_no = batch.batch_no;
            row.expiry_date = batch.expiry_date;
            row.batch_rows = [batch];

            v33UpdateRowOnly(idx);

            if (typeof status === 'function') status(`Batch selected: ${batch.batch_no}`, 'green');

            if (typeof focusCell === 'function') setTimeout(() => focusCell(idx, 1, true), 20);
        });
    }

    const renderGridLegacyV33 = typeof renderGrid === 'function' ? renderGrid : null;
    renderGrid = function(focusLast = false) {
        v33FullRenderGrid(focusLast);
    };

    const deleteSelectedLineLegacyV33 = typeof deleteSelectedLine === 'function' ? deleteSelectedLine : null;
    deleteSelectedLine = function() {
        const idx = typeof getSelectedGridRow === 'function' ? getSelectedGridRow() : (typeof navState !== 'undefined' ? navState.row : 0);
        v33DeleteRow(idx);
    };

    const duplicateSelectedLineLegacyV33 = typeof duplicateSelectedLine === 'function' ? duplicateSelectedLine : null;
    duplicateSelectedLine = function() {
        const idx = typeof getSelectedGridRow === 'function' ? getSelectedGridRow() : (typeof navState !== 'undefined' ? navState.row : 0);
        v33DuplicateRow(idx);
    };

    bindV33GridEvents();


    // fast_item_search_v30/cache rows should ideally include:
    // item_code, item_name, barcode, actual_qty/stock_qty, ptr/rate,
    // mrp/pharma_mrp, best_batch/batch_no, best_expiry/expiry_date,
    // last_customer_rate/last_rate, margin_percent/gross_margin_percent.
    // Missing optional fields are rendered blank rather than blocking billing.

    function renderSearchMetaV323(row) {
        const rate = searchRowRate(row);
        const mrp = searchRowMrp(row);
        const batch = row.batch_no || row.best_batch || '';
        const exp = row.expiry_date || row.best_expiry || '';
        const stock = searchStock(row);
        const last = row.last_customer_rate || row.last_rate || '';
        const margin = searchMargin(row);
        const expSoon = isNearExpiry(exp);
        const marginHtml = margin ? `<span class="${marginClass(margin)}">Margin ${margin}%</span>` : '';

        return `
            <span>PTR ${rate || '-'}</span>
            ${mrp ? `<span>MRP ${mrp}</span>` : ''}
            <span>Qty ${stock}</span>
            ${batch ? `<span class="pob-batch-chip">Batch ${batch}</span>` : ''}
            ${exp ? `<span class="pob-exp-chip ${expSoon ? 'pob-exp-soon' : ''}">Exp ${exp}${expSoon ? ' âš ' : ''}</span>` : ''}
            ${last ? `<span>Last ${last}</span>` : ''}
            ${marginHtml}
        `;
    }

    function hydrateSearchBatchesAsyncV323(rows) {
        const topRows = (rows || []).slice(0, 10);

        topRows.forEach(row => {
            if (!row || !row.item_code) return;

            const warehouse = getCurrentWarehouse ? getCurrentWarehouse() : (state.warehouse || '');
            const cached = getCachedBatchesForItem(row.item_code, warehouse);

            if (cached.length) return;

            fetchBatchesForItemV323(row.item_code).then(() => {
                if ($suggestions.is(':visible')) {
                    const currentText = $search.val();
                    if (currentText && window.PharmaFastBillingV241) {
                        const localRows = window.PharmaFastBillingV241.searchItems(currentText, 20) || [];
                        if (localRows.length) renderSuggestions(localRows);
                    }
                }
            });
        });
    }

    function commitBatchSelectionV323(idx, batch_no, keepFocus = true) {
        const row = state.items[idx];
        if (!row) return;

        const batch = (row.available_batches || []).find(x => x.batch_no === batch_no);

        if (!batch) {
            status('Selected batch not available', 'orange');
            return;
        }

        row.batch_no = batch.batch_no;
        row.expiry_date = batch.expiry_date;
        row.batch_rows = [batch];

        renderGrid();

        status(`Batch selected: ${batch.batch_no}`, 'green');

        if (keepFocus && typeof focusCell === 'function') {
            setTimeout(() => focusCell(idx, 1, true), 20);
        }
    }

    function handleBatchDropdownKeyV323(e) {
        const $target = $(e.target);

        if (!$target.hasClass('pob-inline-batch')) return false;

        const idx = Number($target.data('idx'));

        if (e.key === 'Enter' || e.key === 'Tab') {
            e.preventDefault();
            commitBatchSelectionV323(idx, $target.val(), false);
            if (typeof moveCell === 'function') moveCell(0, 1);
            return true;
        }

        if (e.key === 'Escape') {
            e.preventDefault();
            if (typeof focusSearch === 'function') focusSearch();
            return true;
        }

        return false;
    }

    function shouldAutoAddExactV323(txt, rows) {
        txt = String(txt || '').trim().toLowerCase();

        if (!txt || !rows || !rows.length) return null;

        return rows.find(x =>
            String(x.barcode || '').toLowerCase() === txt ||
            String(x.item_code || '').toLowerCase() === txt
        ) || null;
    }

    async function addExactItemWithBatchesV323(item) {
        const batches = await fetchBatchesForItemV323(item.item_code);
        addItem(item, 1, batches);
        $search.val('').focus();
        $suggestions.hide().empty();
        status('Added: ' + item.item_code, 'green');
    }

    function inject_v32_3_styles() {
        if ($('#pob32-3-style').length) return;

        $('head').append(`
            <style id="pob32-3-style">
                .pob-sug-meta span { white-space: nowrap; }
                .pob-inline-batch:focus {
                    border-color: #2563eb !important;
                    box-shadow: 0 0 0 1px #2563eb !important;
                }
                .pob-exp-soon { color: #b91c1c !important; }
                .pob-batch-chip { color: #1d4ed8 !important; }
            </style>
        `);
    }

    inject_v32_3_styles();


    addHotkeyHelp();
    bindNoMouseNavigation();

    ensureStickyTotals();
    ensureIntelligenceDock();



    function status(msg, indicator='blue') {
        $root.find('.pob-status').html(`<span class="indicator ${indicator}">${msg}</span>`);
    }

    function money(v) {
        return (Number(v || 0)).toFixed(2);
    }

    function collectPayload() {
        return {
            customer: state.customer || getCurrentCustomer(),
            company: state.company || getCompany(),
            warehouse: state.warehouse || getCurrentWarehouse(),
            price_list: getPriceList(),
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

        for (let idx = 0; idx < state.items.length; idx++) {
            const row = state.items[idx];

            if (!row.available_batches && row.item_code) {
                row.available_batches = normalizeBatchRows(row.batch_rows || []);
            }

            if ((!row.batch_rows || !row.batch_rows.length) && row.available_batches && row.available_batches.length) {
                const fefo = chooseFEFOBatch(row.available_batches);
                if (fefo) {
                    row.batch_no = fefo.batch_no;
                    row.expiry_date = fefo.expiry_date;
                    row.batch_rows = [fefo];
                }
            }

            const batch = (row.batch_rows || [])[0] || {};
            const expValue = batch.expiry_date || row.expiry_date || '';
            const expClass = isNearExpiry(expValue) ? 'pob-exp-soon' : '';
            const margin = row.margin_percent || row.gross_margin_percent || 0;
            const marginCls = marginClass(margin);

            const tr = $(`<tr data-idx="${idx}">
                <td>${idx + 1}</td>
                <td><b>${row.item_code}</b><br><small>${row.item_name || ''}</small></td>
                <td>
                    <select class="form-control input-xs pob-inline-batch" data-idx="${idx}">
                        ${renderBatchOptions(row)}
                    </select>
                    ${(!row.available_batches || !row.available_batches.length) ? '<small class="text-warning">No lot</small>' : ''}
                </td>
                <td class="${expClass}">${expValue || ''}</td>
                <td><input class="form-control input-xs pob-row-qty" value="${row.qty || 1}"></td>
                <td><input class="form-control input-xs pob-row-free" value="${row.free_qty || 0}"></td>
                <td><input class="form-control input-xs pob-row-rate" value="${row.rate || 0}"></td>
                <td><input class="form-control input-xs pob-row-disc" value="${row.discount_percentage || 0}"></td>
                <td>${row.item_tax_template || ''}</td>
                <td class="pob-row-amount ${marginCls}">${money(row.amount)}</td>
                <td><button class="btn btn-xs btn-danger pob-row-del">Ã—</button></td>
            </tr>`);

            $tbody.append(tr);
        }

        const totals = calcTotals();
        $root.find('.pob-line-count').text(state.items.length);
        $root.find('.pob-total-qty').text(totals.qty);
        $root.find('.pob-grand-total').text(money(totals.grand_total));
        window.__current_pharma_quick_sale_payload = collectPayload();

        if (state.items.length) {
            selectGridRow(Math.min(selectedGridIndex || 0, state.items.length - 1));
        }

        if (focusLast) $tbody.find('tr:last .pob-row-qty').focus().select();
    }

    function addItem(item, qty=1, batches=[]) {
        const existing = state.items.find(x => x.item_code === item.item_code);
        const normalizedBatches = cacheBatchesForItem(item.item_code, getCurrentWarehouse ? getCurrentWarehouse() : (state.warehouse || ''), batches || []);
        const selectedBatch = chooseFEFOBatch(normalizedBatches);

        if (existing) {
            existing.qty = Number(existing.qty || 0) + Number(qty || 1);
            existing.available_batches = normalizedBatches.length ? normalizedBatches : (existing.available_batches || []);

            if (!existing.batch_no && selectedBatch) {
                existing.batch_no = selectedBatch.batch_no;
                existing.expiry_date = selectedBatch.expiry_date;
                existing.batch_rows = [selectedBatch];
            }

            if (typeof v33UpdateRowOnly === 'function') {
                const existingIdx = state.items.indexOf(existing);
                v33UpdateRowOnly(existingIdx);
            } else {
                renderGrid();
            }
            $search.val('').focus();
            return;
        }

        const newRow = {
            item_code: item.item_code,
            item_name: item.item_name,
            qty: qty,
            free_qty: 0,
            rate: Number(item.rate || item.ptr || item.standard_rate || 0),
            discount_percentage: 0,
            item_tax_template: item.item_tax_template || '',
            has_batch_no: item.has_batch_no,
            available_batches: normalizedBatches,
            batch_rows: selectedBatch ? [selectedBatch] : [],
            batch_no: selectedBatch ? selectedBatch.batch_no : null,
            expiry_date: selectedBatch ? selectedBatch.expiry_date : null,
            margin_percent: item.margin_percent || 0,
            mrp: item.mrp || item.pharma_mrp || 0,
            last_customer_rate: item.last_customer_rate || item.last_rate || ''
        };

        if (typeof v33AddRow === 'function') {
            v33AddRow(newRow, false);
        } else {
            state.items.push(newRow);
            selectedGridIndex = state.items.length - 1;
            if (typeof navState !== 'undefined') {
                navState.row = state.items.length - 1;
                navState.col = 1;
            }
            renderGrid();
        }

        $search.val('').focus();
        $suggestions.hide().empty();
    }

    function renderSuggestions(rows) {
        rows = enrichSearchRowsWithBatchIntel(rows || []);
        selectedSuggestionIndex = 0;

        if (!rows.length) {
            $suggestions.hide().empty();
            return;
        }

        const html = rows.map((x, i) => {
            const itemLabel = safeItemLabel(x);
            const stock = searchStock(x);

            return `<div class="pob-suggestion ${i === 0 ? 'active' : ''}" data-index="${i}" data-item="${x.item_code}">
                <div class="pob-sug-main">
                    <span class="pob-sug-code">${itemLabel}</span>
                    <span>Stock ${stock}</span>
                </div>
                <div class="pob-sug-meta">
                    ${renderSearchMetaV323(x)}
                    ${x.composition ? `<span>${x.composition}</span>` : ''}
                </div>
            </div>`;
        }).join('');

        $suggestions.html(html).show();
        highlightSuggestion();
        hydrateSearchBatchesAsyncV323(rows);
    }

    async function loadCache() {
        const ok = await safeBootstrapFastBillingV331();

        if (ok) {
            status('Cache loaded', 'green');
        } else {
            status('Server search fallback active', 'orange');
        }

        $search.focus();
    }

    async function scanOrSearch(value) {
        const txt = (value || '').trim();
        if (!txt) return;
        state.warehouse = getCurrentWarehouse();

        let item = window.PharmaFastBillingV241 ? window.PharmaFastBillingV241.resolveBarcode(txt) : null;
        if (item && item.item_code) {
            const batches = window.PharmaFastBillingV241.localFEFO(item.item_code, state.warehouse || getCurrentWarehouse(), 999);
            addItem(item, 1, batches);
            status('Scanned: ' + item.item_code, 'green');
            return;
        }

        const rows = window.PharmaFastBillingV241 ? window.PharmaFastBillingV241.searchItems(txt, 20) : [];

        if (rows && rows.length) {
            const exactLocalV323 = shouldAutoAddExactV323(txt, rows);
            if (exactLocalV323) {
                addExactItemWithBatchesV323(exactLocalV323);
                return;
            }
            renderSuggestions(rows);

            if (rows.length === 1) {
                const batches = window.PharmaFastBillingV241.localFEFO(rows[0].item_code, getCurrentWarehouse(), 999);
                addItem(rows[0], 1, batches);
            }
            return;
        }

        frappe.call({
            method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.fast_item_search_v30',
            args: {
                query: txt,
                warehouse: getCurrentWarehouse(),
                price_list: getPriceList()
            },
            callback: r => {
                const serverRows = r.message || [];
                const exactServerV323 = shouldAutoAddExactV323(txt, serverRows);
                if (exactServerV323) {
                    addExactItemWithBatchesV323(exactServerV323);
                    return;
                }
                renderSuggestions(serverRows);
                if (!serverRows.length) status('No item found: ' + txt, 'orange');
            },
            error: () => status('Item search failed. Check server log.', 'red')
        });
    }

    $root.find('.pob-load-cache').on('click', loadCache);

    $search.on('input', frappe.utils.debounce(() => {
        scanOrSearch($search.val());
    }, 120));

    $search.on('keydown', e => {
        const $items = $suggestions.find('.pob-suggestion');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedSuggestionIndex = Math.min($items.length - 1, selectedSuggestionIndex + 1);
            highlightSuggestion();
            return;
        }

        if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedSuggestionIndex = Math.max(0, selectedSuggestionIndex - 1);
            highlightSuggestion();
            return;
        }

        if (e.key === 'Escape') {
            e.preventDefault();
            $suggestions.hide().empty();
            return;
        }

        if (e.key === 'Enter') {
            e.preventDefault();

            const $selected = $items.eq(selectedSuggestionIndex);
            const first = $selected.length ? $selected.data('item') : $suggestions.find('.pob-suggestion:first').data('item');

            if (first && window.PharmaFastBillingV241) {
                const item = getMemoryItemSafeV331(first);

                if (item && item.item_code) {
                    const batches = window.PharmaFastBillingV241.localFEFO(item.item_code, getCurrentWarehouse(), 999);
                    addItem(item, 1, batches);
                    $suggestions.hide();
                    return;
                }

                fetchSingleItemServerV331(first, serverItem => {
                    if (!serverItem || !serverItem.item_code) {
                        status('Item not found in cache/server: ' + first, 'orange');
                        return;
                    }
                    addExactItemWithBatchesV323(serverItem);
                    $suggestions.hide();
                });
                return;
            }

            scanOrSearch($search.val());
        }
    });

    $suggestions.on('click', '.pob-suggestion', function() {
        const code = $(this).data('item');
        const item = getMemoryItemSafeV331(code);

        if (item && item.item_code) {
            const batches = window.PharmaFastBillingV241.localFEFO(item.item_code, getCurrentWarehouse(), 999);
            addItem(item, 1, batches);
            $suggestions.hide();
            return;
        }

        fetchSingleItemServerV331(code, serverItem => {
            if (!serverItem || !serverItem.item_code) {
                status('Item not found in cache/server: ' + code, 'orange');
                return;
            }
            addExactItemWithBatchesV323(serverItem);
            $suggestions.hide();
        });
    });

    $tbody.on('input', 'input', function() {
        if (typeof v33GridReady !== 'undefined' && v33GridReady) return;
        const tr = $(this).closest('tr');
        const idx = Number(tr.data('idx'));
        const row = state.items[idx];
        const rawQty = tr.find('.pob-row-qty').val();
        const parsedQty = parseQuickQty(rawQty);
        row.qty = Number(parsedQty.qty || 0);
        row.uom_hint = parsedQty.uom;
        row.free_qty = Number(tr.find('.pob-row-free').val() || 0);
        row.rate = Number(tr.find('.pob-row-rate').val() || 0);
        row.discount_percentage = Number(tr.find('.pob-row-disc').val() || 0);
        calcTotals();
        tr.find('.pob-row-amount').text(money(row.amount));
        const totals = calcTotals();
        $root.find('.pob-total-qty').text(totals.qty);
        $root.find('.pob-grand-total').text(money(totals.grand_total));
        window.__current_pharma_quick_sale_payload = collectPayload();
        // V32.3 qty edit keeps selected batch and current navigation context.
        if (row.batch_no && row.available_batches && row.available_batches.length) {
            const selected = row.available_batches.find(b => b.batch_no === row.batch_no);
            if (selected) row.batch_rows = [selected];
        }
    });

    $tbody.on('click', '.pob-row-del', function() {
        if (typeof v33GridReady !== 'undefined' && v33GridReady) return;
        const idx = Number($(this).closest('tr').data('idx'));
        state.items.splice(idx, 1);
        renderGrid();
    });

    $tbody.on('change', '.pob-inline-batch', function() {
        if (typeof v33GridReady !== 'undefined' && v33GridReady) return;
        const idx = Number($(this).data('idx'));
        commitBatchSelectionV323(idx, $(this).val(), true);
    });

    $tbody.on('keydown', '.pob-inline-batch', function(e) {
        if (handleBatchDropdownKeyV323(e)) return;
    });

    $tbody.on('click', 'tr', function() {
        selectGridRow(Number($(this).data('idx')));
    });


    $root.find('.pob-submit').on('click', () => {
        state.customer = getCurrentCustomer();
        state.company = getCompany();
        state.warehouse = getCurrentWarehouse();

        const payload = collectPayload();

        if (hasMissingBatchRows()) {
            frappe.msgprint('One or more batch-controlled items do not have a selected batch/lot.');
            return;
        }

        validateBeforeSubmit(payload, ok => {
            if (!ok) return;

            frappe.call({
                method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.operator_submit_invoice',
                args: {data: payload, action: 'invoice'},
                freeze: true,
                freeze_message: 'Submitting invoice...',
                callback: r => {
                    const d = r.message || {};
                    status('Invoice submitted', 'green');
                    if (d.sales_invoice) frappe.set_route('Form', 'Sales Invoice', d.sales_invoice);
                }
            });
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
                            setCustomer(p.customer || '');
                            setCompany(p.company || '');
                            setWarehouse(p.warehouse || '');
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



    // =============================================================
    // V32.1 keyboard hardening
    // =============================================================
    $(document).off('keydown.pob32').on('keydown.pob32', function(e) {
        if (e.key === 'F2' || e.key === 'F6' || e.key === 'F7' || e.key === 'Delete' || (e.ctrlKey && ['l','d','s'].includes(e.key.toLowerCase()))) return;
        if ($(e.target).closest('.modal').length) return;
        if (!$(e.target).closest('.pob-root').length && !['F2','F6','Escape'].includes(e.key) && !(e.ctrlKey && ['l','d'].includes(e.key.toLowerCase()))) {
            return;
        }

        // F2 â†’ focus batch selector for selected row.
        if (e.key === 'F2') {
            e.preventDefault();
            focusInlineBatch(getSelectedGridRow());
            return;
        }

        // F6 â†’ focus quantity for selected row.
        if (e.key === 'F6') {
            e.preventDefault();
            const idx = getSelectedGridRow();
            if (idx != null) {
                $tbody.find('tr').eq(idx).find('.pob-row-qty').focus().select();
            }
            return;
        }

        // ESC â†’ clear suggestions.
        if (e.key === 'Escape') {
            $suggestions.hide().empty();
            return;
        }

        // Ctrl+L â†’ delete selected line.
        if (e.ctrlKey && e.key.toLowerCase() === 'l') {
            e.preventDefault();
            const idx = getSelectedGridRow();
            if (idx != null) {
                state.items.splice(idx, 1);
                renderGrid();
            }
            return;
        }

        // Ctrl+D â†’ duplicate selected line.
        if (e.ctrlKey && e.key.toLowerCase() === 'd') {
            e.preventDefault();
            const idx = getSelectedGridRow();
            if (idx != null && state.items[idx]) {
                state.items.splice(idx + 1, 0, Object.assign({}, state.items[idx], {
                    batch_rows: [...(state.items[idx].batch_rows || [])],
                    available_batches: [...(state.items[idx].available_batches || [])]
                }));
                selectedGridIndex = idx + 1;
                renderGrid();
            }
        }
    });

    window.PharmaOperatorBilling = {
        state, addItem, renderGrid, collectPayload, recallHeld, focusInlineBatch, getSelectedGridRow,  getCustomer:getCurrentCustomer, getCompany, getWarehouse:getCurrentWarehouse, getPriceList, focusCell, focusSearch, focusCustomer, moveCell, v33CommitCell, v33UpdateRowOnly, v33FullRenderGrid,
        focusSearch: () => $search.focus(),
        focusCustomer: () => customer_control && customer_control.$input.focus(),
        focusQty: () => $tbody.find('tr:last .pob-row-qty').focus().select(),
        focusRate: () => $tbody.find('tr:last .pob-row-rate').focus().select(),
        saveInvoice: () => $root.find('.pob-submit').click(),
        holdInvoice: () => $root.find('.pob-hold').click(),
        recallHeld
    };

    if (window.PharmaFastBillingV241) {
        window.PharmaFastBillingV241.bindHotkeys(window.PharmaOperatorBilling);
        window.PharmaFastBillingV241.loadMemory()
            .then(() => status('Local cache ready', 'green'))
            .catch(async () => {
                await resetFastBillingIndexedDBV331();
                status('Load cache to begin', 'orange');
            });
    }

    status('Ready', 'green');
};


// v27.1 intelligence binding
(function() {
    function tryLoadOperatorIntelligenceFromRow($row) {
        if (!window.PharmaOperatorIntelligenceV27 || !$row || !$row.length) return;
        const itemText = $row.find('td:nth-child(2) b').first().text();
        if (!itemText) return;
        const customer = window.PharmaOperatorBilling && window.PharmaOperatorBilling.getCustomer ? window.PharmaOperatorBilling.getCustomer() : ($('.pob-customer').val() || null);
        const warehouse = window.PharmaOperatorBilling && window.PharmaOperatorBilling.getWarehouse ? window.PharmaOperatorBilling.getWarehouse() : ($('.pob-warehouse').val() || null);
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

    $(document).off('click.pob27intel', '.pob-grid tbody tr').on('click.pob27intel', '.pob-grid tbody tr', function() {
        tryLoadOperatorIntelligenceFromRow($(this));
    });

    $(document).off('focus.pob27intel', '.pob-row-qty, .pob-row-rate, .pob-row-disc').on('focus.pob27intel', '.pob-row-qty, .pob-row-rate, .pob-row-disc', function() {
        tryLoadOperatorIntelligenceFromRow($(this).closest('tr'));
    });

    $(document).off('keydown.pob27intel').on('keydown.pob27intel', function(e) {
        if (e.key === 'F10') {
            e.preventDefault();
            const $row = $('.pob-grid tbody tr:has(input:focus)').first();
            tryLoadOperatorIntelligenceFromRow($row.length ? $row : $('.pob-grid tbody tr:last'));
        }
    });
})();


// v28.1 hardened scheme binding
$(document).off('keydown.pob28scheme1').on('keydown.pob28scheme1', function(e) {
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
$(document).off('keydown.pob28scheme2').on('keydown.pob28scheme2', function(e) {
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

