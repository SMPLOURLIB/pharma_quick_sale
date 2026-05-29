
window.PharmaOperatorIntelligenceV27 = {
  async loadPanel({item_code, customer=null, warehouse=null, qty=1, rate=0, batch_no=null}) {
    if (!item_code) return;
    return new Promise(resolve => {
      frappe.call({
        method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_operator_decision_panel',
        args: {item_code, customer, warehouse, qty, rate, batch_no},
        callback: r => { const data = r.message || {}; this.render(data); resolve(data); }
      });
    });
  },
  render(data) {
    let $panel = $('.pob-right-panel-body.pob-right-search-body');
    if (!$panel.length) $panel = $('<div class="pob-right-panel-body"></div>').appendTo('.pob-right-panel');
    const s = data.decision_summary || {}, margin = data.margin || {};
    const batches = data.batch_history || [], subs = data.substitutes || [];
    $panel.html(`
      <div class="poi-body">
        <div class="poi-item"><b>Item:</b> <span> ${data.item_code || ''}</span></div>
        <div class="poi-item"><b>Available Batches:</b> <span> ${s.available_batches || 0}</span></div>
        <div class="poi-item"><b>Last Sale:</b> <span> ${s.last_sale_rate || '-'}</span></div>
        <div class="poi-item"><b>Last Purchase:</b> <span> ${s.last_purchase_rate || '-'}</span></div>
        <div class="poi-item"><b>Margin:</b> <span> ${Number(margin.margin_percent || 0).toFixed(2)}%</span></div>
        <div class="poi-item"><b>Near Expiry:</b> <span> ${s.near_expiry_count || 0}</span></div>
        <div class="poi-item"><b>Substitutes:</b> <span> ${s.substitute_count || 0}</span></div><hr>
        <b>Batch History</b>
        <table class="table table-condensed"><tr><th>Batch</th><th>Exp</th><th>Qty</th><th>PRate</th><th>LSale</th></tr>
          ${batches.slice(0,5).map(b => `<tr><td>${b.batch_no || ''}</td><td>${b.expiry_date || ''}</td><td>${b.available_qty || 0}</td><td>${b.purchase_rate || '-'}</td><td>${b.last_sale_rate || '-'}</td></tr>`).join('')}
        </table>
        <b>Substitutes</b><ul>${subs.slice(0,5).map(x => `<li>${x.item_code} — Stock ${x.stock_qty || 0}</li>`).join('')}</ul>
      </div>`).show();
  }
};
