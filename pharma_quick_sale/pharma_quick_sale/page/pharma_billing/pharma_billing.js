
frappe.pages['pharma-billing'].on_page_load = function(wrapper) {
  window.PharmaBillingV30 = new PharmaBillingEngineV30(wrapper);
};

class PharmaBillingEngineV30 {
  constructor(wrapper) {
    this.wrapper = $(wrapper);
    this.page = frappe.ui.make_app_page({ parent: wrapper, title: 'Pharma Billing', single_column: true });
    this.state = {
      company: null, customer: null, warehouse: null, tax_category: null,
      loss_sale_approval: null,
      price_list: 'Standard Selling', items: [], selectedSearchIndex: 0,
      activeResults: [], activeBatches: [], barcodeMode: false
    };
    this.db = null;
    this.render();
    this.bind();
    this.initCache();
  }

  render() {
    this.wrapper.find('.layout-main-section').html(`
      <div class="pb30">
        <div class="pb30-top">
          <div><label>Company</label><input class="pb30-company" placeholder="Company"></div>
          <div><label>Customer</label><input class="pb30-customer" list="pb30-customers" placeholder="F5 customer / distributor"><datalist id="pb30-customers"></datalist></div>
          <div><label>Warehouse</label><input class="pb30-warehouse" placeholder="Default warehouse"></div>
          <div><label>Tax Category</label><input class="pb30-tax-category" placeholder="GST/default"></div>
          <div><label>Item / Barcode</label><input class="pb30-search" placeholder="Type item, composition, barcode…"></div>
          <button class="pb30-cache btn btn-sm btn-default">Refresh Cache</button>
        </div>
        <div class="pb30-main">
          <div class="pb30-left">
            <div class="pb30-results"></div>
            <table class="table table-bordered pb30-grid"><thead><tr><th>#</th><th>Item</th><th>Batch</th><th>Exp</th><th>Qty</th><th>Rate</th><th>Disc%</th><th>Amount</th></tr></thead><tbody></tbody></table>
          </div>
          <div class="pb30-right"><div class="pb30-status">Ready. F2 search, Enter add, F3 batch, F4 scheme, F9 invoice.</div><div class="pb30-batches"></div><div class="pb30-intel"></div></div>
        </div>
        <div class="pb30-footer"><div>Total Qty: <b class="pb30-total-qty">0</b></div><div>Net Total: <b class="pb30-net-total">0.00</b></div><button class="btn btn-warning pb30-loss-approval">Loss Approval</button><button class="btn btn-primary pb30-invoice">F9 Invoice</button><button class="btn btn-default pb30-new">New Bill</button></div>
      </div>`);
    setTimeout(() => this.$search().focus(), 200);
  }

  $search(){ return this.wrapper.find('.pb30-search'); }
  $customer(){ return this.wrapper.find('.pb30-customer'); }
  $warehouse(){ return this.wrapper.find('.pb30-warehouse'); }
  $company(){ return this.wrapper.find('.pb30-company'); }
  $taxCategory(){ return this.wrapper.find('.pb30-tax-category'); }

  bind() {
    this.wrapper.find('.pb30-cache').on('click', () => this.refreshCache());
    this.wrapper.find('.pb30-invoice').on('click', () => this.submitInvoice());
    this.wrapper.find('.pb30-loss-approval').on('click', () => this.requestLossApproval());
    this.wrapper.find('.pb30-new').on('click', () => this.newBill());
    this.$search().on('input', frappe.utils.debounce(() => this.search(this.$search().val()), 80));
    this.$search().on('keydown', e => this.handleSearchKey(e));

    $(document).off('keydown.pb30').on('keydown.pb30', e => {
      if (!$(e.target).closest('.pb30').length && !['F2','F3','F4','F5','F6','F7','F8','F9','F10','F11','F12','Escape'].includes(e.key)) return;
      if (e.key === 'F2') { e.preventDefault(); this.$search().focus().select(); }
      if (e.key === 'F3') { e.preventDefault(); this.showBatchSelectorForLastRow(); }
      if (e.key === 'F4') { e.preventDefault(); this.applyScheme(); }
      if (e.key === 'F5') { e.preventDefault(); this.$customer().focus().select(); }
      if (e.key === 'F6') { e.preventDefault(); this.showOutstanding(); }
      if (e.key === 'F7') { e.preventDefault(); this.showSubstitutes(); }
      if (e.key === 'F8') { e.preventDefault(); this.holdBill(); }
      if (e.key === 'F9') { e.preventDefault(); this.submitInvoice(); }
      if (e.key === 'F10') { e.preventDefault(); this.showIntelligenceForLastRow(); }
      if (e.key === 'F11') { e.preventDefault(); this.repeatOrder(); }
      if (e.key === 'F12') { e.preventDefault(); this.toggleBarcodeMode(); }
      if (e.key === 'Escape') { this.clearOverlays(); }
    });
  }

  initCache() {
    const req = indexedDB.open('PharmaBillingV30', 2);
    req.onupgradeneeded = e => {
      const db = e.target.result;
      ['items','customers','batches'].forEach(store => {
        if (!db.objectStoreNames.contains(store)) db.createObjectStore(store, {keyPath: store === 'items' ? 'item_code' : store === 'customers' ? 'name' : 'key'});
      });
    };
    req.onsuccess = e => { this.db = e.target.result; this.loadDefaults(); this.refreshCache(false); };
    req.onerror = () => this.status('IndexedDB unavailable; using server search.');
  }

  loadDefaults() {
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_billing_defaults_v30',
      callback:r => {
        const d = r.message || {};
        this.$company().val(d.company || '');
        this.$warehouse().val(d.warehouse || '');
        this.state.price_list = d.price_list || 'Standard Selling';
        this.$taxCategory().val(d.tax_category || '');
      }
    });
  }

  validatePartyInputs(cb) {
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.validate_billing_party_v30',
      args:{customer:this.$customer().val(), warehouse:this.$warehouse().val(), company:this.$company().val()},
      callback:r => {
        const res = r.message || {};
        if (!res.valid) { frappe.msgprint((res.errors || []).join('<br>')); cb(false); return; }
        this.$customer().val(res.customer || this.$customer().val());
        this.$warehouse().val(res.warehouse || this.$warehouse().val());
        this.$company().val(res.company || this.$company().val());
        cb(true);
      }
    });
  }

  writeStore(store, rows) {
    if (!this.db) return;
    const tx = this.db.transaction(store, 'readwrite');
    rows.forEach(row => tx.objectStore(store).put(row));
  }

  async getAll(store) {
    return new Promise(resolve => {
      if (!this.db) return resolve([]);
      const tx = this.db.transaction(store, 'readonly');
      const req = tx.objectStore(store).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => resolve([]);
    });
  }

  refreshCache(force=true) {
    this.status('Refreshing local cache…');
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_billing_cache_v30',
      args:{warehouse:this.$warehouse().val() || null, company:this.$company().val() || null, item_limit:25000, batch_limit:100000, customer_limit:25000},
      callback:r => {
        const data = r.message || {};
        this.writeStore('items', data.items || []);
        this.writeStore('customers', data.customers || []);
        this.writeStore('batches', data.batches || []);
        this.updateCustomerDatalist(data.customers || []);
        this.status(`Cache ready: ${(data.items||[]).length} items, ${(data.batches||[]).length} batches.`);
      }
    });
  }

  updateCustomerDatalist(customers) {
    this.wrapper.find('#pb30-customers').html((customers || []).slice(0, 5000).map(c => `<option value="${c.name}">${c.customer_name || c.name}</option>`).join(''));
  }

  async search(q) {
    q = (q || '').toLowerCase().trim();
    if (!q) { this.renderResults([]); return; }
    const rows = await this.getAll('items');
    const results = rows.filter(x => [x.item_code,x.item_name,x.barcode,x.composition,x.brand,x.manufacturer].join(' ').toLowerCase().includes(q)).slice(0, 12);
    if (!results.length) {
      frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.fast_item_search_v30', args:{query:q, warehouse:this.$warehouse().val() || null}, callback:r => this.renderResults(r.message || [])});
      return;
    }
    this.renderResults(results);
  }

  renderResults(results) {
    this.state.activeResults = results || []; this.state.selectedSearchIndex = 0;
    this.wrapper.find('.pb30-results').html((results||[]).map((x,i)=>`<div class="pb30-result ${i===0?'active':''}" data-index="${i}"><span>${i+1}. <b>${x.item_code}</b> ${x.item_name || ''}</span><span>Stock ${x.stock_qty || 0} | MRP ${x.mrp || '-'} | PTR ${x.ptr || '-'}</span></div>`).join(''));
    this.wrapper.find('.pb30-result').on('click', e => this.addItemByIndex(Number($(e.currentTarget).data('index'))));
  }

  handleSearchKey(e) {
    const max = this.state.activeResults.length;
    if (e.key === 'ArrowDown') { e.preventDefault(); this.state.selectedSearchIndex = Math.min(max-1, this.state.selectedSearchIndex+1); this.highlightResults(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); this.state.selectedSearchIndex = Math.max(0, this.state.selectedSearchIndex-1); this.highlightResults(); }
    if (e.key === 'Enter') { e.preventDefault(); if (this.state.barcodeMode) this.addBarcode(this.$search().val()); else this.addItemByIndex(this.state.selectedSearchIndex); }
    if (/^[1-9]$/.test(e.key) && max >= Number(e.key)) { e.preventDefault(); this.addItemByIndex(Number(e.key)-1); }
  }

  highlightResults() {
    this.wrapper.find('.pb30-result').removeClass('active');
    this.wrapper.find(`.pb30-result[data-index="${this.state.selectedSearchIndex}"]`).addClass('active');
  }

  async addItemByIndex(i) {
    const item = this.state.activeResults[i]; if (!item) return;
    const batches = await this.getBatches(item.item_code);
    const chosen = this.autoSelectBatch(batches);
    const row = {row_id: frappe.utils.get_random(8), item_code:item.item_code, item_name:item.item_name, qty:1, rate:item.ptr || item.standard_rate || 0, discount_percentage:0, batch_no:chosen ? chosen.batch_no : null, expiry_date:chosen ? chosen.expiry_date : null, amount:item.ptr || item.standard_rate || 0, batch_allocations:chosen ? [{batch_no:chosen.batch_no, qty:1, expiry_date:chosen.expiry_date}] : []};
    this.previewAutoAllocation(row);
    this.state.items.push(row); this.renderGrid(); this.$search().val('').focus(); this.renderResults([]); this.showIntelligence(row);
  }

  async getBatches(item_code) {
    const all = await this.getAll('batches');
    const rows = all.filter(x => x.item_code === item_code && Number(x.available_qty || 0) > 0);
    if (rows.length) return rows;
    return new Promise(resolve => frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_batch_history', args:{item_code, warehouse:this.$warehouse().val() || null}, callback:r => resolve(r.message || [])}));
  }

  autoSelectBatch(batches) {
    if (!batches || !batches.length) return null;
    return batches.slice().sort((a,b) => String(a.expiry_date || '9999').localeCompare(String(b.expiry_date || '9999')))[0];
  }

  renderGrid() {
    const tbody = this.wrapper.find('.pb30-grid tbody');
    tbody.html(this.state.items.map((x,i)=>`<tr data-index="${i}"><td>${i+1}</td><td><b>${x.item_code}</b><br>${x.item_name||''}</td><td>${x.batch_no || '-'}</td><td>${x.expiry_date || '-'}</td><td><input class="pb30-qty" data-index="${i}" value="${x.qty}"></td><td><input class="pb30-rate" data-index="${i}" value="${x.rate}"></td><td><input class="pb30-disc" data-index="${i}" value="${x.discount_percentage||0}"></td><td>${Number(x.amount||0).toFixed(2)}</td></tr>`).join(''));
    tbody.find('input').on('change', e => this.updateRow($(e.currentTarget)));
    tbody.find('tr').on('click', e => this.showIntelligence(this.state.items[Number($(e.currentTarget).data('index'))]));
    this.updateTotals();
  }

  updateRow($input) {
    const i = Number($input.data('index')); const row = this.state.items[i];
    row.qty = Number(this.wrapper.find(`.pb30-qty[data-index="${i}"]`).val() || 0);
    row.rate = Number(this.wrapper.find(`.pb30-rate[data-index="${i}"]`).val() || 0);
    row.discount_percentage = Number(this.wrapper.find(`.pb30-disc[data-index="${i}"]`).val() || 0);
    row.amount = row.qty * row.rate * (1 - row.discount_percentage/100);
    if (row.batch_no) row.batch_allocations = [{batch_no:row.batch_no, qty:row.qty, expiry_date:row.expiry_date}];
    this.renderGrid();
    this.analyzeCurrentBill();
  }

  updateTotals() {
    const qty = this.state.items.reduce((s,x)=>s+Number(x.qty||0),0);
    const total = this.state.items.reduce((s,x)=>s+Number(x.amount||0),0);
    this.wrapper.find('.pb30-total-qty').text(qty); this.wrapper.find('.pb30-net-total').text(total.toFixed(2));
  }

  previewAutoAllocation(row) {
    if (!row || !row.item_code || !row.qty) return;
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_batch_allocation_preview_v31',
      args:{item_code:row.item_code, qty:row.qty, warehouse:this.$warehouse().val() || null, customer:this.$customer().val() || null},
      callback:r => {
        const d = r.message || {};
        if (d.allocations && d.allocations.length) {
          row.batch_allocations = d.allocations;
          row.batch_no = d.allocations[0].batch_no;
          row.expiry_date = d.allocations[0].expiry_date;
          this.renderGrid();
          this.wrapper.find('.pb30-batches').html('<h4>Auto Allocation</h4>' + d.allocations.map(a => `<div class="pb30-batch">${a.batch_no} → ${a.qty} | Exp ${a.expiry_date || '-'}</div>`).join('') + (d.shortage_qty ? `<div class="text-danger">Shortage: ${d.shortage_qty}</div>` : ''));
        }
      }
    });
  }

  showBatchSelectorForLastRow() {
    const row = this.state.items[this.state.items.length-1]; if (!row) return this.status('No row for batch selection.');
    this.getBatches(row.item_code).then(batches => {
      this.state.activeBatches = batches;
      this.wrapper.find('.pb30-batches').html(`<h4>Batch Selector</h4>` + batches.map((b,i)=>`<div class="pb30-batch" data-index="${i}">${i+1}. <b>${b.batch_no}</b> Exp ${b.expiry_date || '-'} Qty ${b.available_qty || 0}</div>`).join(''));
      this.wrapper.find('.pb30-batch').on('click', e => this.chooseBatch(Number($(e.currentTarget).data('index'))));
    });
  }

  chooseBatch(i) {
    const b = this.state.activeBatches[i]; const row = this.state.items[this.state.items.length-1]; if (!b || !row) return;
    row.batch_no = b.batch_no; row.expiry_date = b.expiry_date; row.batch_allocations = [{batch_no:b.batch_no, qty:row.qty, expiry_date:b.expiry_date}]; this.renderGrid();
  }

  toggleBarcodeMode() {
    this.state.barcodeMode = !this.state.barcodeMode;
    this.status(this.state.barcodeMode ? 'Smart Barcode Mode ON: scan, scan, scan, F9.' : 'Smart Barcode Mode OFF.');
    this.$search().focus().select();
  }

  addBarcode(barcode) {
    if (!barcode) return;
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.smart_barcode_add_v31_2',
      args:{barcode:barcode, customer:this.$customer().val() || null, warehouse:this.$warehouse().val() || null},
      callback:r => {
        const res = r.message || {};
        if (!res.found) { this.status(res.message || 'Barcode not found.'); return; }
        this.state.items.push(res.row);
        this.renderGrid();
        this.$search().val('').focus();
        this.showIntelligence(res.row);
      }
    });
  }

  repeatOrder(mode='last_invoice') {
    const payload = this.collectPayload();
    if (!payload.customer) return this.status('Select customer before repeat order.');
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_repeat_order_to_payload_v31_2',
      args:{data:payload, mode:mode},
      callback:r => {
        const updated = r.message || payload;
        this.state.items = updated.items || [];
        this.renderGrid();
        this.status(updated.repeat_order_source ? `Repeat order loaded from ${updated.repeat_order_source}` : 'No repeat order found.');
      }
    });
  }

  analyzeCurrentBill() {
    const payload = this.collectPayload();
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.analyze_billing_payload_v31_2',
      args:{data:payload},
      callback:r => {
        const d = r.message || {};
        const warnings = d.warnings || [];
        if (d.has_block && !this.state.loss_sale_approval) this.status('Loss sale approval required before invoice.');
        this.wrapper.find('.pb30-intel').html('<h4>Billing Intelligence</h4>' + (warnings.length ? warnings.map(w => `<div class="${w.severity==='BLOCK'?'text-danger':'text-warning'}">${w.item_code}: ${w.message}</div>`).join('') : '<div>No warnings.</div>'));
      }
    });
  }

  showIntelligenceForLastRow() { const row = this.state.items[this.state.items.length-1]; if (row) this.showIntelligence(row); this.analyzeCurrentBill(); }

  showIntelligence(row) {
    frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_operator_decision_panel', args:{item_code:row.item_code, customer:this.$customer().val() || null, warehouse:this.$warehouse().val() || null, qty:row.qty, rate:row.rate, batch_no:row.batch_no}, callback:r => {
      const d = r.message || {}; const s = d.decision_summary || {};
      this.wrapper.find('.pb30-intel').html(`<h4>Intelligence</h4><div>Last Sale: ${s.last_sale_rate || '-'}</div><div>Last Purchase: ${s.last_purchase_rate || '-'}</div><div>Margin: ${Number(s.margin_percent || 0).toFixed(2)}%</div><div>Substitutes: ${s.substitute_count || 0}</div><div>Near Expiry: ${s.near_expiry_count || 0}</div>`);
    }});
  }

  applyScheme() {
    const payload = this.collectPayload();
    frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_advanced_scheme_to_operator_payload', args:{data:payload}, callback:r => {
      const updated = r.message || payload;
      this.state.items = (updated.items || []).map(x => Object.assign({amount:Number(x.qty||0)*Number(x.rate||0)}, x));
      this.renderGrid(); this.status(updated.advanced_scheme_name ? `Scheme applied: ${updated.advanced_scheme_name}` : 'No eligible scheme.');
    }});
  }

  showOutstanding() {
    const customer = this.$customer().val(); if (!customer) return this.status('Select customer first.');
    frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_customer_outstanding_snapshot', args:{customer}, callback:r => this.wrapper.find('.pb30-intel').html('<pre>'+JSON.stringify(r.message||{}, null, 2)+'</pre>')});
  }

  showSubstitutes() {
    const row = this.state.items[this.state.items.length-1]; if (!row) return;
    frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_commercial_substitutes', args:{item_code:row.item_code, warehouse:this.$warehouse().val()||null}, callback:r => this.wrapper.find('.pb30-intel').html('<h4>Substitutes</h4>'+(r.message||[]).map(x=>`<div>${x.item_code}</div>`).join(''))});
  }

  holdBill() { localStorage.setItem('pharma_billing_v30_hold', JSON.stringify(this.collectPayload())); this.status('Bill held.'); }
  newBill() { this.state.items = []; this.$search().val(''); this.renderGrid(); this.$search().focus(); this.status('New bill ready.'); }

  collectPayload() {
    const batch_allocations = [];
    this.state.items.forEach(row => (row.batch_allocations||[]).forEach(b => batch_allocations.push({item_row_id:row.row_id, item_code:row.item_code, batch_no:b.batch_no, qty:b.qty, expiry_date:b.expiry_date})));
    return {company:this.$company().val(), customer:this.$customer().val(), warehouse:this.$warehouse().val(), tax_category:this.$taxCategory().val(), loss_sale_approval:this.state.loss_sale_approval, price_list:this.state.price_list, items:this.state.items, batch_allocations, grand_total:this.state.items.reduce((s,x)=>s+Number(x.amount||0),0)};
  }

  requestLossApproval() {
    const payload = this.collectPayload();
    frappe.prompt([{fieldname:'reason', label:'Reason', fieldtype:'Small Text', reqd:1}], values => {
      frappe.call({
        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.create_loss_sale_approval_v31_2_1',
        args:{data:payload, reason:values.reason},
        callback:r => {
          const approval = r.message;
          this.state.loss_sale_approval = approval;
          frappe.msgprint(`Loss sale approval created: ${approval}. Manager must approve before invoicing.`);
        }
      });
    }, 'Request Loss Sale Approval');
  }

  submitInvoice() {
    const payload = this.collectPayload();
    if (!payload.customer) return this.status('Customer required.');
    if (!payload.company) return this.status('Company required.');
    if (!payload.items.length) return this.status('No items.');
    this.validatePartyInputs(valid => {
      if (!valid) return;
      this.analyzeCurrentBill();
      frappe.call({
        method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.apply_auto_batch_allocation_to_payload_v31',
        args:{data:this.collectPayload()},
        freeze:true,
        callback:alloc => {
          const data = alloc.message || this.collectPayload();
          if (data.batch_allocation_errors && data.batch_allocation_errors.length) {
            frappe.msgprint(data.batch_allocation_errors.join('<br>'));
            return;
          }
          frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.operator_submit_invoice', args:{data:data, action:'invoice'}, freeze:true, callback:r => { const msg = r.message || {}; frappe.msgprint(`Invoice created: ${msg.sales_invoice || ''}`); this.newBill(); }});
        }
      });
    });
  }

  clearOverlays(){ this.wrapper.find('.pb30-results,.pb30-batches').empty(); }
  status(msg){ this.wrapper.find('.pb30-status').text(msg); }
}
