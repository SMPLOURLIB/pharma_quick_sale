
window.PharmaFastBillingV241 = {
  dbName: 'pharma_quick_sale_fast_cache_v241',
  dbVersion: 1,
  db: null,
  memory: {items: [], customers: [], batches: [], barcodeIndex: {}, itemIndex: {}, customerIndex: {}},

  openDB() {
    return new Promise((resolve, reject) => {
      if (this.db) return resolve(this.db);
      const req = indexedDB.open(this.dbName, this.dbVersion);
      req.onupgradeneeded = e => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('items')) db.createObjectStore('items', {keyPath: 'item_code'});
        if (!db.objectStoreNames.contains('customers')) db.createObjectStore('customers', {keyPath: 'name'});
        if (!db.objectStoreNames.contains('batches')) db.createObjectStore('batches', {keyPath: ['item_code', 'warehouse', 'batch_no']});
        if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta', {keyPath: 'key'});
      };
      req.onsuccess = e => { this.db = e.target.result; resolve(this.db); };
      req.onerror = () => reject(req.error);
    });
  },

  async putMany(storeName, rows) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readwrite');
      const store = tx.objectStore(storeName);
      (rows || []).forEach(row => store.put(row));
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => reject(tx.error);
    });
  },

  async getAll(storeName) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly');
      const req = tx.objectStore(storeName).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  },

  async bootstrapFromServer(args={}) {
    const start = performance.now();
    return new Promise((resolve, reject) => {
      frappe.call({
        method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.fast_billing_bootstrap',
        args,
        freeze: true,
        freeze_message: 'Loading fast billing cache...',
        callback: async r => {
          const data = r.message || {};
          await this.putMany('items', data.items || []);
          await this.putMany('customers', data.customers || []);
          await this.putMany('batches', data.batches || []);
          await this.loadMemory();
          this.recordBenchmark('cache_bootstrap_ms', performance.now() - start, {items: (data.items || []).length});
          resolve(data);
        },
        error: reject
      });
    });
  },

  async loadMemory() {
    this.memory.items = await this.getAll('items');
    this.memory.customers = await this.getAll('customers');
    this.memory.batches = await this.getAll('batches');
    this.rebuildIndexes();
    return this.memory;
  },

  rebuildIndexes() {
    this.memory.barcodeIndex = {};
    this.memory.itemIndex = {};
    this.memory.customerIndex = {};
    (this.memory.items || []).forEach(item => {
      this.memory.itemIndex[item.item_code] = item;
      (item.barcodes || []).forEach(b => this.memory.barcodeIndex[b] = item);
    });
    (this.memory.customers || []).forEach(c => this.memory.customerIndex[c.name] = c);
  },

  searchItems(txt, limit=20) {
    const start = performance.now();
    txt = (txt || '').toLowerCase().trim();
    if (!txt) return [];
    const scored = [];
    for (const item of this.memory.items || []) {
      let score = 0;
      const code = (item.item_code || '').toLowerCase();
      const name = (item.item_name || '').toLowerCase();
      const comp = (item.composition || '').toLowerCase();
      const mfg = (item.manufacturer || '').toLowerCase();
      const brand = (item.brand || '').toLowerCase();
      const barcodes = item.barcodes || [];
      if (barcodes.includes(txt)) score = 1000;
      else if (code === txt) score = 900;
      else if (code.startsWith(txt)) score = 800;
      else if (name.startsWith(txt)) score = 700;
      else if (brand.startsWith(txt)) score = 650;
      else if (comp.includes(txt)) score = 500;
      else if (mfg.includes(txt)) score = 400;
      else if (name.includes(txt) || code.includes(txt)) score = 300;
      if (score) scored.push({score, item});
    }
    const result = scored.sort((a,b) => b.score - a.score).slice(0, limit).map(x => x.item);
    this.recordBenchmark('search_ms', performance.now() - start, {txt, count: result.length}, true);
    return result;
  },

  searchCustomers(txt, limit=20) {
    txt = (txt || '').toLowerCase().trim();
    if (!txt) return [];
    const rows = [];
    for (const c of this.memory.customers || []) {
      const hay = [c.name, c.customer_name, c.mobile_no, c.tax_id, c.gstin, c.pharma_drug_license_no, c.pharma_whatsapp_no].filter(Boolean).join(' ').toLowerCase();
      if (hay.includes(txt)) rows.push(c);
      if (rows.length >= limit) break;
    }
    return rows;
  },

  resolveBarcode(barcode) {
    return this.memory.barcodeIndex[barcode] || this.memory.itemIndex[barcode] || null;
  },

  localFEFO(item_code, warehouse, qty) {
    let remaining = Number(qty || 0);
    const rows = (this.memory.batches || [])
      .filter(b => b.item_code === item_code && (!warehouse || b.warehouse === warehouse) && Number(b.actual_qty || 0) > 0)
      .sort((a,b) => String(a.expiry_date || '').localeCompare(String(b.expiry_date || '')));
    const out = [];
    for (const b of rows) {
      if (remaining <= 0) break;
      const alloc = Math.min(Number(b.actual_qty || 0), remaining);
      out.push({batch_no: b.batch_no, expiry_date: b.expiry_date, qty: alloc, available_qty: Number(b.actual_qty || 0)});
      remaining -= alloc;
    }
    return out;
  },

  async scanToPayload(barcode, warehouse) {
    const start = performance.now();
    let item = this.resolveBarcode(barcode);
    if (!item) {
      const r = await new Promise(resolve => frappe.call({
        method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.barcode_resolve',
        args: {barcode, warehouse},
        callback: rr => resolve(rr)
      }));
      item = ((r.message || {}).item || null);
    }
    if (!item) return null;
    const batches = this.localFEFO(item.item_code, warehouse, 1);
    this.recordBenchmark('scan_to_add_ms', performance.now() - start, {barcode, item_code: item.item_code});
    return {item, qty: 1, batches};
  },

  applyPayloadToUI(payload) {
    if (window.PharmaQuickSaleV241Adapter && typeof window.PharmaQuickSaleV241Adapter.applyPayload === 'function') {
      return window.PharmaQuickSaleV241Adapter.applyPayload(payload);
    }
    window.__last_pharma_held_payload = payload;
    console.log('Held payload ready for UI adapter', payload);
    frappe.show_alert({message: 'Held payload restored; final row binding requires UAT mapping.', indicator: 'orange'});
    return false;
  },

  bindHotkeys(adapter={}) {
    $(document).off('keydown.v241_fast_billing').on('keydown.v241_fast_billing', e => {
      const key = e.key;
      if (e.ctrlKey && key.toLowerCase() === 'f') { e.preventDefault(); adapter.focusSearch && adapter.focusSearch(); }
      if (e.ctrlKey && key.toLowerCase() === 's') { e.preventDefault(); adapter.saveInvoice && adapter.saveInvoice(); }
      if (e.ctrlKey && key.toLowerCase() === 'p') { e.preventDefault(); adapter.savePrint && adapter.savePrint(); }
      if (key === 'F2') { e.preventDefault(); adapter.focusQty && adapter.focusQty(); }
      if (key === 'F3') { e.preventDefault(); adapter.focusRate && adapter.focusRate(); }
      if (key === 'F4') { e.preventDefault(); adapter.applyScheme && adapter.applyScheme(); }
      if (key === 'F6') { e.preventDefault(); adapter.focusCustomer && adapter.focusCustomer(); }
      if (key === 'F8') { e.preventDefault(); adapter.holdInvoice && adapter.holdInvoice(); }
      if (key === 'F9') { e.preventDefault(); adapter.recallHeld && adapter.recallHeld(); }
      if (key === 'Escape') { $('.pqs-inline-results,.v241-suggestions').hide(); }
    });
  },

  recordBenchmark(metric, elapsed_ms, context={}, silent=false) {
    if (silent) return;
    frappe.call({
      method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.record_operator_benchmark',
      args: {metric, elapsed_ms, context: JSON.stringify(context)}
    });
  }
};
