
window.PharmaAdvancedSchemeV28 = {
  evaluate(items, customer, cb) {
    frappe.call({
      method: 'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.hardened_apply_best_advanced_scheme',
      args: {items: JSON.stringify(items || []), customer: customer},
      callback: r => {
        const data = r.message || {};
        this.render(data);
        if (cb) cb(data);
      }
    });
  },
  render(data) {
    let $panel = $('.pharma-advanced-scheme-panel');
    if (!$panel.length) $panel = $('<div class="pharma-advanced-scheme-panel"></div>').appendTo('body');
    const best = data.best || {};
    if (!best.scheme) {
      $panel.html('<div class="pas-head">Advanced Scheme <button class="pas-close">×</button></div><div class="pas-body">No eligible advanced scheme.</div>').show();
    } else {
      $panel.html(`<div class="pas-head">Advanced Scheme <button class="pas-close">×</button></div>
        <div class="pas-body">
          <b>${best.scheme_name}</b><br>
          Type: ${best.scheme_type}<br>
          Benefit: ${best.benefit_amount || 0}<br>
          Discount: ${best.discount_percentage || 0}% / ${best.discount_amount || 0}<br>
          Free Items: ${((data.payload && data.payload.free_item_rows) || best.free_items || []).map(x => `${x.item_code} x ${x.qty}`).join(', ') || '-'}
        </div>`).show();
    }
    $panel.find('.pas-close').on('click', () => $panel.hide());
  }
};
