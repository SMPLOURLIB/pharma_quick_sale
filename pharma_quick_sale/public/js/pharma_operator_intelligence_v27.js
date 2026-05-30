
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
      <table>
        <tr><th><b>Item:</b></th><td>${data.item_code || ''}</td></tr>
        <tr><th><b>Available Batches:</b></th><td>${s.available_batches || 0}</td></tr>
        <tr><th><b>Last Sale:</b> <span> </th><td>${s.last_sale_rate || '-'}</td></tr>
        <tr><th><b>Last Purchase:</b> </th><td>${s.last_purchase_rate || '-'}</td></tr>
        <tr><th><b>Margin:</b> </th><td>${Number(margin.margin_percent || 0).toFixed(2)}%</td></tr>
        <tr><th><b>Near Expiry:</b> </th><td>${s.near_expiry_count || 0}</td></tr>
        <tr><th><b>Substitutes:</b> </th><td>${s.substitute_count || 0}</td></tr>
        </table> 
      <hr>
        <b>Batch History</b>
        <table class="table table-condensed"><tr><th>Batch</th><th>Exp</th><th>Qty</th><th>PRate</th><th>LSale</th></tr>
          ${batches.slice(0,5).map(b => `<tr><td>${b.batch_no || ''}</td><td>${b.expiry_date || ''}</td><td>${b.available_qty || 0}</td><td>${b.purchase_rate || '-'}</td><td>${b.last_sale_rate || '-'}</td></tr>`).join('')}
        </table>
        <b>Substitutes</b><ul>${subs.slice(0,5).map(x => `<li>${x.item_code} — Stock ${x.stock_qty || 0}</li>`).join('')}</ul>
      </div>`).show();
  }
};
