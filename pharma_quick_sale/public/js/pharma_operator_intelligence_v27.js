
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
    let $panel = $('.pharma-operator-intelligence-panel');
    if (!$panel.length) $panel = $('<div class="pharma-operator-intelligence-panel"></div>').appendTo('body');
    const s = data.decision_summary || {}, margin = data.margin || {};
    const batches = data.batch_history || [], subs = data.substitutes || [];
    $panel.html(`<div class="poi-head">Operator Intelligence <button class="poi-close">×</button></div>
      <div class="poi-body">
        <div><b>Item:</b> ${data.item_code || ''}</div>
        <div><b>Available Batches:</b> ${s.available_batches || 0}</div>
        <div><b>Last Sale:</b> ${s.last_sale_rate || '-'}</div>
        <div><b>Last Purchase:</b> ${s.last_purchase_rate || '-'}</div>
        <div><b>Margin:</b> ${Number(margin.margin_percent || 0).toFixed(2)}%</div>
        <div><b>Near Expiry:</b> ${s.near_expiry_count || 0}</div>
        <div><b>Substitutes:</b> ${s.substitute_count || 0}</div><hr>
        <b>Batch History</b>
        <table class="table table-condensed"><tr><th>Batch</th><th>Exp</th><th>Qty</th><th>PRate</th><th>LSale</th></tr>
          ${batches.slice(0,5).map(b => `<tr><td>${b.batch_no || ''}</td><td>${b.expiry_date || ''}</td><td>${b.available_qty || 0}</td><td>${b.purchase_rate || '-'}</td><td>${b.last_sale_rate || '-'}</td></tr>`).join('')}
        </table>
        <b>Substitutes</b><ul>${subs.slice(0,5).map(x => `<li>${x.item_code} — Stock ${x.stock_qty || 0}</li>`).join('')}</ul>
      </div>`).show();
    $panel.find('.poi-close').on('click', () => $panel.hide());
  }
};
