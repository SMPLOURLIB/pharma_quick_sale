
frappe.pages['pharma-loss-approvals'].on_page_load = function(wrapper) {
  window.PharmaLossApprovalsV31 = new PharmaLossApprovalsV31(wrapper);
};

class PharmaLossApprovalsV31 {
  constructor(wrapper) {
    this.wrapper = $(wrapper);
    this.page = frappe.ui.make_app_page({
      parent: wrapper,
      title: 'Loss Sale Approvals',
      single_column: true
    });
    this.render();
    this.load();
  }

  render() {
    this.wrapper.find('.layout-main-section').html(`
      <div class="pla31">
        <div class="pla31-toolbar">
          <select class="pla31-status">
            <option value="">Draft + Approved</option>
            <option value="Draft">Draft</option>
            <option value="Approved">Approved</option>
            <option value="Used">Used</option>
            <option value="Rejected">Rejected</option>
            <option value="Expired">Expired</option>
          </select>
          <button class="btn btn-sm btn-default pla31-refresh">Refresh</button>
        </div>
        <div class="pla31-list"></div>
      </div>
    `);
    this.wrapper.find('.pla31-refresh,.pla31-status').on('click change', () => this.load());
  }

  load() {
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.get_loss_sale_approval_queue_v31_2_2',
      args:{status:this.wrapper.find('.pla31-status').val() || null},
      callback:r => this.renderList(r.message || [])
    });
  }

  renderList(rows) {
    this.wrapper.find('.pla31-list').html(rows.map(row => `
      <div class="pla31-card">
        <div class="pla31-head">
          <b>${row.name}</b>
          <span>${row.customer || ''}</span>
          <span class="pla31-status-pill">${row.status}</span>
        </div>
        <div>Reason: ${row.reason || '-'}</div>
        <div>Valid Until: ${row.valid_until || '-'}</div><div>Used Invoice: ${row.used_sales_invoice || '-'}</div><div>Used By: ${row.used_by || '-'}</div><div>Used On: ${row.used_on || '-'}</div>
        <table class="table table-bordered">
          <thead><tr><th>Item</th><th>Batch</th><th>Qty</th><th>Selling</th><th>Cost</th><th>Loss</th><th>Margin%</th></tr></thead>
          <tbody>
            ${(row.items || []).map(i => `<tr><td>${i.item_code}</td><td>${i.batch_no || '-'}</td><td>${i.qty}</td><td>${i.selling_rate}</td><td>${i.cost_rate}</td><td>${i.loss_amount}</td><td>${i.margin_percent}</td></tr>`).join('')}
          </tbody>
        </table>
        <div class="pla31-actions">
          ${row.status === 'Draft' ? `<button class="btn btn-sm btn-primary pla31-approve" data-name="${row.name}">Approve</button><button class="btn btn-sm btn-danger pla31-reject" data-name="${row.name}">Reject</button>` : ''}
        </div>
      </div>
    `).join('') || '<div class="text-muted">No approvals found.</div>'});

    this.wrapper.find('.pla31-approve').on('click', e => this.decide($(e.currentTarget).data('name'), 1));
    this.wrapper.find('.pla31-reject').on('click', e => this.decide($(e.currentTarget).data('name'), 0));
  }

  decide(name, approve) {
    frappe.call({
      method:'pharma_quick_sale.pharma_quick_sale.doctype.pharma_quick_sale.pharma_quick_sale.approve_loss_sale_approval_v31_2_1',
      args:{approval:name, approve:approve},
      callback:() => {
        frappe.show_alert({message: approve ? 'Approved' : 'Rejected', indicator: approve ? 'green' : 'red'});
        this.load();
      }
    });
  }
}
