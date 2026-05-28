
window.PharmaFastOperatorV29 = {
  safeClick(selector){ const el=$(selector).first(); if(el.length){el.trigger('click'); return true;} return false; },
  safeFocus(selector){ const el=$(selector).first(); if(el.length){el.focus(); return true;} return false; },
  collectPayloadSafe(){
    if(window.PharmaOperatorBilling && window.PharmaOperatorBilling.collectPayload) return window.PharmaOperatorBilling.collectPayload();
    return {customer: $('.pob-customer').val() || $('[data-fieldname="customer"] input').val() || null, warehouse: $('.pob-warehouse').val() || $('[data-fieldname="warehouse"] input').val() || null, items: []};
  },
  bind(){
    $(document).on('keydown', function(e){
      if(!['F2','F3','F5','F6','F7','F8','F9','F10'].includes(e.key)) return;
      e.preventDefault();
      if(e.key==='F2'){
        if(window.PharmaOperatorBilling && window.PharmaOperatorBilling.focusSearch) window.PharmaOperatorBilling.focusSearch();
        else if(!window.PharmaFastOperatorV29.safeFocus('.pob-search input')) window.PharmaFastOperatorV29.safeFocus('input[type="search"], input[data-fieldname="item_code"]');
      }
      if(e.key==='F3'){
        if(!window.PharmaFastOperatorV29.safeClick('.pob-grid tbody tr:last')) frappe.show_alert({message:'No billing row selected for batch view', indicator:'orange'});
      }
      if(e.key==='F5'){
        if(window.PharmaOperatorBilling && window.PharmaOperatorBilling.focusCustomer) window.PharmaOperatorBilling.focusCustomer();
        else if(!window.PharmaFastOperatorV29.safeFocus('.pob-customer')) window.PharmaFastOperatorV29.safeFocus('[data-fieldname="customer"] input');
      }
      if(e.key==='F6'){
        const p=window.PharmaFastOperatorV29.collectPayloadSafe();
        if(!p.customer) return frappe.show_alert({message:'Select customer first', indicator:'orange'});
        frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_customer_outstanding_snapshot', args:{customer:p.customer}, callback:r=>frappe.msgprint({title:'Outstanding', message:'<pre>'+JSON.stringify(r.message||{}, null, 2)+'</pre>'})});
      }
      if(e.key==='F7'){
        const item=$('.pob-grid tbody tr:last td:nth-child(2) b').text() || $('[data-fieldname="item_code"] input').val();
        if(!item) return frappe.show_alert({message:'Select item first', indicator:'orange'});
        frappe.call({method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_commercial_substitutes', args:{item_code:item}, callback:r=>frappe.msgprint({title:'Substitutes', message:(r.message||[]).map(x=>x.item_code || x.substitute_item).join('<br>')||'No substitutes'})});
      }
      if(e.key==='F8'){
        if(window.PharmaOperatorBilling && window.PharmaOperatorBilling.holdBill) window.PharmaOperatorBilling.holdBill();
        else frappe.show_alert({message:'Hold Bill action is not available on this page', indicator:'orange'});
      }
      if(e.key==='F9'){
        if(window.PharmaOperatorBilling && window.PharmaOperatorBilling.saveInvoice) window.PharmaOperatorBilling.saveInvoice();
        else if(!window.PharmaFastOperatorV29.safeClick('.primary-action, button[data-label="Save"]')) frappe.show_alert({message:'Invoice action is not available on this page', indicator:'orange'});
      }
      if(e.key==='F10'){
        if(!window.PharmaFastOperatorV29.safeClick('.pob-grid tbody tr:last')) frappe.show_alert({message:'No billing row selected for intelligence panel', indicator:'orange'});
      }
    });
  }
};
$(function(){ window.PharmaFastOperatorV29.bind(); });
