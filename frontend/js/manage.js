/* PAYFLOW management views: beneficiaries, transactions, bills, requests, cards, analytics. */
(function () {
  const PF = window.PF;

  // -------------------------------------------------------------------------
  // Beneficiaries
  // -------------------------------------------------------------------------
  PF.views.beneficiaries = async function (view) {
    const list = await PF.api('/beneficiaries');
    const cards = list.map(function (b) {
      return '<div class="card"><div class="card-head"><div>' +
        '<div class="card-title">' + (b.favorite ? '★ ' : '') + PF.esc(b.nickname) + '</div>' +
        '<div class="card-sub mono">' + PF.esc(b.vpa) + '</div></div>' + PF.badge(b.category, 'blue') + '</div>' +
        '<div class="flex gap-1 mt-2">' +
          '<button class="btn btn-sm btn-primary" data-pay="' + PF.esc(b.vpa) + '">Pay</button>' +
          '<button class="btn btn-sm" data-fav="' + b.id + '">' + (b.favorite ? 'Unfavourite' : 'Favourite') + '</button>' +
          '<button class="btn btn-sm" data-hist="' + b.id + '">History</button>' +
          '<button class="btn btn-sm btn-danger" data-del="' + b.id + '">Delete</button>' +
        '</div></div>';
    }).join('');

    view.innerHTML = PF.sectionHead('Beneficiaries', 'Saved contacts for one-tap payments',
      '<button class="btn btn-primary" id="add-ben">+ Add Beneficiary</button>') +
      (list.length ? '<div class="grid grid-3">' + cards + '</div>' : '<div class="card empty">No saved beneficiaries yet.</div>');

    view.querySelectorAll('[data-pay]').forEach(function (b) {
      b.onclick = function () {
        sessionStorage.setItem('pf_recipient', b.dataset.pay);
        location.hash = '#/send';
      };
    });
    view.querySelectorAll('[data-fav]').forEach(function (b) {
      b.onclick = async function () {
        try { await PF.api('/beneficiaries/' + b.dataset.fav + '/favorite', { method: 'POST' }); PF.route(); }
        catch (err) { PF.showError(err); }
      };
    });
    view.querySelectorAll('[data-del]').forEach(function (b) {
      b.onclick = function () {
        PF.confirm('Delete beneficiary', 'This only removes the saved contact, not any transactions.', async function () {
          try { await PF.api('/beneficiaries/' + b.dataset.del, { method: 'DELETE' }); PF.toast('Removed', 'ok'); PF.route(); }
          catch (err) { PF.showError(err); }
        }, true);
      };
    });
    view.querySelectorAll('[data-hist]').forEach(function (b) {
      b.onclick = async function () {
        try {
          const rows = await PF.api('/beneficiaries/' + b.dataset.hist + '/history');
          const modal = PF.modal('<div class="modal-head"><h3>Beneficiary History</h3></div>' +
            PF.table(['TXN', 'Description', 'Category', 'Amount'], rows.map(function (e) {
              return '<tr><td class="mono">' + PF.esc(e.transaction_id) + '</td><td>' + PF.esc(e.description) +
                '</td><td>' + PF.badge(e.category, 'blue') + '</td><td>' + PF.inr(e.total_paise) + '</td></tr>';
            }), 'No shared transactions.') +
            '<div class="modal-foot"><button class="btn" id="bh-close">Close</button></div>', true);
          modal.querySelector('#bh-close').onclick = PF.closeModal;
        } catch (err) { PF.showError(err); }
      };
    });
    view.querySelector('#add-ben').onclick = function () {
      const modal = PF.modal(
        '<div class="modal-head"><h3>Add Beneficiary</h3></div>' +
        '<div class="form-grid">' +
          '<div class="field"><label>VPA / phone / username</label><input id="b-id" placeholder="rohit_kumar@payflow"></div>' +
          '<div class="field"><label>Nickname</label><input id="b-nick" placeholder="Rohit"></div>' +
          '<div class="form-row"><div class="field"><label>Category</label><select id="b-cat">' +
            '<option>P2P</option><option>Food</option><option>Shopping</option><option>Travel</option><option>Bills</option></select></div>' +
            '<div class="field"><label>&nbsp;</label><label class="checkline"><input type="checkbox" id="b-fav"> Favourite</label></div></div>' +
        '</div><div class="modal-foot"><button class="btn" id="b-cancel">Cancel</button>' +
          '<button class="btn btn-primary" id="b-go">Save Beneficiary</button></div>'
      );
      modal.querySelector('#b-cancel').onclick = PF.closeModal;
      modal.querySelector('#b-go').onclick = async function () {
        try {
          await PF.api('/beneficiaries', { method: 'POST', body: {
            identifier: modal.querySelector('#b-id').value.trim(),
            nickname: modal.querySelector('#b-nick').value.trim(),
            category: modal.querySelector('#b-cat').value,
            favorite: modal.querySelector('#b-fav').checked,
          }});
          PF.closeModal(); PF.toast('Beneficiary saved', 'ok'); PF.route();
        } catch (err) { PF.showError(err); }
      };
    };
  };

  // -------------------------------------------------------------------------
  // Transactions
  // -------------------------------------------------------------------------
  PF.views.transactions = async function (view) {
    view.innerHTML = PF.sectionHead('Transactions', 'Searchable, filterable immutable activity',
      '<button class="btn" id="csv-export">⇩ Export CSV</button>') +
      '<div class="card mb-2"><form id="tx-filter" class="form-row">' +
        '<div class="field"><label>Category</label><select id="f-cat"><option value="">All categories</option>' +
          ['P2P Transfer', 'Merchant Payment', 'Top-up', 'Bill', 'Fee', 'Reversal', 'Refund', 'Wallet Transfer']
            .map(function (c) { return '<option>' + c + '</option>'; }).join('') + '</select></div>' +
        '<div class="field"><label>From date</label><input type="date" id="f-start"></div>' +
        '<div class="field"><label>To date</label><input type="date" id="f-end"></div>' +
        '<div class="field"><label>&nbsp;</label><button class="btn btn-primary" type="submit">Apply Filters</button></div>' +
      '</form></div><div class="card" id="tx-table"><div class="empty">Loading…</div></div>';

    let rows = [];
    let page = 1;
    const perPage = 12;
    async function load() {
      const params = new URLSearchParams();
      const cat = view.querySelector('#f-cat').value;
      const start = view.querySelector('#f-start').value;
      const end = view.querySelector('#f-end').value;
      if (cat) params.set('category', cat);
      if (start) params.set('start_date', start);
      if (end) params.set('end_date', end);
      rows = await PF.api('/transactions?' + params.toString());
      page = 1;
      renderRows();
    }
    function renderRows() {
      const pages = Math.max(1, Math.ceil(rows.length / perPage));
      if (page > pages) page = pages;
      const visible = rows.slice((page - 1) * perPage, page * perPage);
      const controls = '<div class="flex between items-center mt-2" style="flex-wrap:wrap;gap:12px">' +
        '<span class="muted text-sm">Showing ' + (visible.length ? ((page - 1) * perPage + 1) : 0) + '–' +
          Math.min(page * perPage, rows.length) + ' of ' + rows.length + '</span>' +
        '<div class="flex gap-1">' +
          '<button class="btn btn-sm" id="tx-prev"' + (page <= 1 ? ' disabled' : '') + '>← Previous</button>' +
          '<span class="badge grey">Page ' + page + ' of ' + pages + '</span>' +
          '<button class="btn btn-sm" id="tx-next"' + (page >= pages ? ' disabled' : '') + '>Next →</button>' +
        '</div></div>';
      view.querySelector('#tx-table').innerHTML = PF.table(
        ['TXN ID', 'Date', 'Description', 'Category', 'Counterparty', 'Type', 'Amount', 'Status', 'Receipt'],
        visible.map(function (t) {
          const credit = t.direction === 'CREDIT';
          return '<tr><td class="mono">' + PF.esc(t.transaction_id) + '</td>' +
            '<td class="nowrap muted text-xs">' + PF.esc(PF.fmtDate(t.timestamp)) + '</td>' +
            '<td>' + PF.esc(t.description) + '</td>' +
            '<td>' + PF.badge(t.category, 'blue') + '</td>' +
            '<td class="mono">' + PF.esc(t.counterparty) + '</td>' +
            '<td>' + PF.badge(t.direction, credit ? 'green' : 'red') + '</td>' +
            '<td class="align-right ' + (credit ? 'success' : 'danger') + '">' + (credit ? '+' : '−') + PF.inr(t.amount_paise) + '</td>' +
            '<td>' + PF.badge(t.status, t.status === 'COMPLETED' ? 'green' : 'amber') + '</td>' +
            '<td><button class="btn btn-sm" data-receipt="' + PF.esc(t.transaction_id) + '">View</button></td></tr>';
        }), 'No transactions match these filters.'
      ) + controls;
      view.querySelectorAll('[data-receipt]').forEach(function (b) {
        b.onclick = function () { PF.downloadReceipt(b.dataset.receipt); };
      });
      const prev = view.querySelector('#tx-prev');
      const next = view.querySelector('#tx-next');
      if (prev) prev.onclick = function () { if (page > 1) { page -= 1; renderRows(); } };
      if (next) next.onclick = function () { if (page < pages) { page += 1; renderRows(); } };
    }
    view.querySelector('#tx-filter').onsubmit = async function (e) { e.preventDefault(); await load(); };
    view.querySelector('#csv-export').onclick = function () {
      const head = 'Transaction ID,Date,Description,Category,Counterparty,Direction,Amount Paise,Status\n';
      const body = rows.map(function (t) {
        return [t.transaction_id, t.timestamp, t.description, t.category, t.counterparty,
          t.direction, t.amount_paise, t.status].map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
      }).join('\n');
      const url = URL.createObjectURL(new Blob([head + body], { type: 'text/csv' }));
      const a = document.createElement('a'); a.href = url; a.download = 'payflow-transactions.csv';
      a.click(); URL.revokeObjectURL(url);
    };
    await load();
  };

  // -------------------------------------------------------------------------
  // Bills
  // -------------------------------------------------------------------------
  PF.views.bills = async function (view) {
    const categories = await PF.api('/bills/categories');
    const tiles = categories.map(function (c, i) {
      return '<div class="tile" data-cat="' + i + '"><div class="tile-icon">' +
        (c.icon === 'phone' ? '📱' : c.icon === 'tv' ? '📺' : c.icon === 'bolt' ? '⚡' :
         c.icon === 'flame' ? '🔥' : c.icon === 'drop' ? '💧' : c.icon === 'wifi' ? '📶' :
         c.icon === 'car' ? '🚗' : '🏛️') + '</div>' +
        '<div class="tile-title">' + PF.esc(c.name) + '</div>' +
        '<div class="tile-sub">' + c.providers.length + ' providers</div></div>';
    }).join('');
    view.innerHTML = PF.sectionHead('Bills & Recharges', 'Two-step simulated biller flow — fetch, then confirm') +
      '<div class="grid grid-4">' + tiles + '</div>';

    view.querySelectorAll('[data-cat]').forEach(function (tile) {
      tile.onclick = function () {
        const cat = categories[Number(tile.dataset.cat)];
        const modal = PF.modal(
          '<div class="modal-head"><div><h3>' + PF.esc(cat.name) + '</h3>' +
            '<div class="card-sub">Select a provider and enter your consumer ID</div></div></div>' +
          '<div class="form-grid">' +
            '<div class="field"><label>Provider</label><select id="bill-provider">' +
              cat.providers.map(function (p) { return '<option>' + PF.esc(p) + '</option>'; }).join('') + '</select></div>' +
            '<div class="field"><label>Consumer ID / Account number</label><input id="bill-consumer" placeholder="e.g. 987654321012"></div>' +
          '</div><div id="bill-result"></div>' +
          '<div class="modal-foot"><button class="btn" id="bill-cancel">Cancel</button>' +
            '<button class="btn btn-primary" id="bill-fetch">Fetch Bill</button></div>'
        );
        modal.querySelector('#bill-cancel').onclick = PF.closeModal;
        modal.querySelector('#bill-fetch').onclick = async function () {
          try {
            const bill = await PF.api('/bills/fetch', { method: 'POST', body: {
              category: cat.id, provider: modal.querySelector('#bill-provider').value,
              consumer_id: modal.querySelector('#bill-consumer').value.trim(),
            }});
            modal.querySelector('#bill-result').innerHTML =
              '<div class="card mt-2" style="box-shadow:none"><div class="between"><span class="muted text-xs">Amount Due</span>' +
              '<span class="kpi-value red" style="font-size:20px">' + PF.inr(bill.amount_paise) + '</span></div>' +
              '<div class="between text-xs mt-1"><span>Biller reference</span><b class="mono">' + PF.esc(bill.biller_reference) + '</b></div>' +
              '<div class="between text-xs mt-1"><span>Due date</span><b>' + PF.esc(bill.due_date) + '</b></div></div>';
            const foot = modal.querySelector('.modal-foot');
            foot.innerHTML = '<button class="btn" id="bill-cancel2">Cancel</button>' +
              '<button class="btn btn-success" id="bill-pay">Confirm & Pay ' + PF.inr(bill.amount_paise) + '</button>';
            foot.querySelector('#bill-cancel2').onclick = PF.closeModal;
            foot.querySelector('#bill-pay').onclick = async function () {
              try {
                const result = await PF.api('/bills/pay', { method: 'POST', body: { bill_id: bill.bill_id } });
                PF.closeModal();
                PF.receiptModal({
                  transaction_id: result.entry.transaction_id, reference: result.entry.reference,
                  timestamp: result.entry.timestamp, description: result.entry.description,
                  total_paise: result.entry.total_paise, fee_paise: 0,
                  status: 'COMPLETED', counterparty: result.bill.provider,
                });
              } catch (err) { PF.showError(err); }
            };
          } catch (err) { PF.showError(err); }
        };
      };
    });
  };

  // -------------------------------------------------------------------------
  // Payment requests
  // -------------------------------------------------------------------------
  PF.views.requests = async function (view) {
    const rows = await PF.api('/requests');
    const render = function (tab) {
      const subset = rows.filter(function (r) {
        return tab === 'incoming' ? r.direction === 'INCOMING' : r.direction === 'OUTGOING';
      });
      return PF.table(['ID', 'Counterparty', 'Amount', 'Note', 'Status', 'Created', 'Actions'],
        subset.map(function (r) {
          let actions = '<span class="muted">—</span>';
          if (r.status === 'PENDING' && r.direction === 'INCOMING') {
            actions = '<button class="btn btn-sm btn-success" data-approve="' + r.id + '">Approve</button> ' +
              '<button class="btn btn-sm btn-danger" data-reject="' + r.id + '">Reject</button>';
          } else if (r.status === 'PENDING' && r.direction === 'OUTGOING') {
            actions = '<button class="btn btn-sm btn-warning" data-cancel="' + r.id + '">Cancel</button>';
          } else if (r.transaction_id) {
            actions = '<button class="btn btn-sm" data-receipt="' + r.transaction_id + '">Receipt</button>';
          }
          const tone = r.status === 'APPROVED' ? 'green' : r.status === 'PENDING' ? 'amber' : 'grey';
          return '<tr><td class="mono">' + PF.esc(r.id) + '</td>' +
            '<td class="mono">' + PF.esc(tab === 'incoming' ? r.creator_vpa : r.payer_vpa) + '</td>' +
            '<td class="align-right">' + PF.inr(r.amount_paise) + '</td>' +
            '<td>' + PF.esc(r.note) + '</td><td>' + PF.badge(r.status, tone) + '</td>' +
            '<td class="muted text-xs nowrap">' + PF.esc(PF.fmtDate(r.created_at)) + '</td>' +
            '<td class="nowrap">' + actions + '</td></tr>';
        }), 'No ' + tab + ' requests.');
    };

    view.innerHTML = PF.sectionHead('Payment Requests', 'A request never moves money until the payer explicitly approves',
      '<button class="btn btn-primary" id="new-request">+ Create Request</button>') +
      '<div class="card mb-2"><div class="flex gap-1">' +
        '<button class="btn btn-sm" data-tab="incoming">Incoming</button>' +
        '<button class="btn btn-sm" data-tab="outgoing">Outgoing</button></div></div>' +
      '<div class="card" id="req-table">' + render('incoming') + '</div>';

    function bind() {
      view.querySelectorAll('[data-tab]').forEach(function (b) {
        b.onclick = function () { view.querySelector('#req-table').innerHTML = render(b.dataset.tab); bind(); };
      });
      view.querySelectorAll('[data-approve]').forEach(function (b) {
        b.onclick = function () {
          PF.confirm('Approve payment', 'This will debit your wallet and credit the requester.', async function () {
            try { await PF.api('/requests/' + b.dataset.approve + '/approve', { method: 'POST', body: {} });
              PF.toast('Request approved', 'ok'); PF.route(); } catch (err) { PF.showError(err); }
          });
        };
      });
      view.querySelectorAll('[data-reject]').forEach(function (b) {
        b.onclick = async function () {
          try { await PF.api('/requests/' + b.dataset.reject + '/reject', { method: 'POST' }); PF.route(); }
          catch (err) { PF.showError(err); }
        };
      });
      view.querySelectorAll('[data-cancel]').forEach(function (b) {
        b.onclick = async function () {
          try { await PF.api('/requests/' + b.dataset.cancel + '/cancel', { method: 'POST' }); PF.route(); }
          catch (err) { PF.showError(err); }
        };
      });
      view.querySelectorAll('[data-receipt]').forEach(function (b) {
        b.onclick = function () { PF.downloadReceipt(b.dataset.receipt); };
      });
    }
    bind();

    view.querySelector('#new-request').onclick = function () {
      const modal = PF.modal(
        '<div class="modal-head"><h3>Create Collect Request</h3></div>' +
        '<div class="form-grid">' +
          '<div class="field"><label>Payer (VPA / phone / username)</label><input id="r-payer" placeholder="rohit_kumar@payflow"></div>' +
          '<div class="field"><label>Amount (INR)</label><div class="input-prefix"><span>₹</span>' +
            '<input id="r-amount" type="number" min="1" step="0.01"></div></div>' +
          '<div class="field"><label>Note</label><input id="r-note" placeholder="Invoice #123"></div>' +
        '</div><div class="modal-foot"><button class="btn" id="r-cancel">Cancel</button>' +
          '<button class="btn btn-primary" id="r-go">Send Request</button></div>'
      );
      modal.querySelector('#r-cancel').onclick = PF.closeModal;
      modal.querySelector('#r-go').onclick = async function () {
        try {
          await PF.api('/requests', { method: 'POST', body: {
            payer: modal.querySelector('#r-payer').value.trim(),
            amount_paise: PF.toPaise(modal.querySelector('#r-amount').value),
            note: modal.querySelector('#r-note').value || 'Payment request',
          }});
          PF.closeModal(); PF.toast('Request sent', 'ok'); PF.route();
        } catch (err) { PF.showError(err); }
      };
    };
  };

  // -------------------------------------------------------------------------
  // Cards
  // -------------------------------------------------------------------------
  PF.views.cards = async function (view) {
    const cards = await PF.api('/cards');
    const html = cards.map(function (c) {
      return '<div class="card"><div class="card-head"><div class="card-title">' + PF.esc(c.brand) +
        ' · ' + PF.esc(c.status) + '</div>' + PF.badge(c.status, c.frozen ? 'red' : 'green') + '</div>' +
        '<div class="kpi-value blue" style="font-family:var(--font-mono);font-size:19px">' + PF.esc(c.masked_number) + '</div>' +
        '<div class="mt-2 text-xs secondary">Holder: ' + PF.esc(c.holder) + ' · Exp: ' + PF.esc(c.expiry) + '</div>' +
        '<div class="text-xs warning mt-1">' + PF.esc(c.network) + '</div>' +
        '<button class="btn btn-sm mt-2 ' + (c.frozen ? 'btn-success' : 'btn-danger') + '" data-freeze="' + PF.esc(c.id) + '">' +
        (c.frozen ? 'Unfreeze Card' : 'Freeze Card') + '</button></div>';
    }).join('');
    view.innerHTML = PF.sectionHead('Virtual Cards', 'Simulated instruments — no real card data is ever collected') +
      '<div class="grid grid-2">' + html + '</div>';
    view.querySelectorAll('[data-freeze]').forEach(function (b) {
      b.onclick = async function () {
        try { await PF.api('/cards/' + encodeURIComponent(b.dataset.freeze) + '/freeze', { method: 'POST' });
          PF.toast('Card state updated', 'ok'); PF.route(); } catch (err) { PF.showError(err); }
      };
    });
  };

  // -------------------------------------------------------------------------
  // Analytics
  // -------------------------------------------------------------------------
  PF.views.analytics = async function (view) {
    const state = { months: 12, days: 14, tab: 'charts', q: '', filter: 'ALL', sort: 'code', dir: 1 };
    let data = null;
    let charts = [];

    function downloadUri(uri, name) {
      const a = document.createElement('a');
      a.href = uri; a.download = name;
      document.body.appendChild(a); a.click(); a.remove();
    }

    function skeleton() {
      view.innerHTML = '<div class="grid grid-4"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>' +
        '<div class="card skeleton mt-2" style="min-height:300px"></div>';
    }

    async function load() {
      skeleton();
      const [cashflow, categories, velocity, status, recon] = await Promise.all([
        PF.api('/analytics/chart/cashflow?months=' + state.months),
        PF.api('/analytics/chart/categories'),
        PF.api('/analytics/chart/velocity?days=' + state.days),
        PF.api('/analytics/chart/status'),
        PF.api('/analytics/reconciliation'),
      ]);
      data = { cashflow: cashflow, categories: categories, velocity: velocity, status: status, recon: recon };
      charts = [cashflow, categories, velocity, status];
      render();
    }

    function mini(label, value, tone, id) {
      return '<div class="kpi kpi-mini"><div class="kpi-label">' + label + '</div>' +
        '<div class="kpi-value ' + (tone || '') + '" id="' + id + '">' + value + '</div></div>';
    }

    function chartCard(chart, subtitle, idx) {
      const summary = Object.entries(chart.summary || {}).slice(0, 3).map(function (kv) {
        return '<span>' + PF.esc(kv[0].replace(/_/g, ' ')) + ': <b>' + PF.esc(kv[1]) + '</b></span>';
      }).join(' · ');
      return '<div class="card chart-card">' +
        '<div class="card-head"><div><div class="card-title">' + PF.esc(chart.title) + '</div>' +
        '<div class="card-sub">' + subtitle + '</div></div>' +
        '<div class="chart-actions">' +
          '<button class="btn btn-sm" data-zoom="' + idx + '">Expand</button>' +
          '<button class="btn btn-sm" data-dl="' + idx + '">SVG</button>' +
        '</div></div>' +
        '<div class="chart-frame"><img src="' + chart.image + '" alt="' + PF.esc(chart.title) + '"></div>' +
        '<div class="chart-summary">' + summary + '</div></div>';
    }

    function renderRecon() {
      const recon = data.recon;
      let rows = recon.rows.filter(function (r) {
        const q = state.q.toLowerCase();
        const okQ = !q || (r.code + ' ' + r.name + ' ' + r.account_type).toLowerCase().includes(q);
        const okS = state.filter === 'ALL' || r.status === state.filter;
        return okQ && okS;
      });
      rows.sort(function (a, b) {
        const av = a[state.sort], bv = b[state.sort];
        const c = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
        return c * state.dir;
      });
      const cols = [
        ['code', 'Code'], ['name', 'Account'], ['account_type', 'Type'],
        ['opening_balance_paise', 'Opening'], ['debits_paise', 'Debits'], ['credits_paise', 'Credits'],
        ['expected_balance_paise', 'Expected'], ['cached_balance_paise', 'Cached'], ['status', 'Status'],
      ];
      const head = cols.map(function (c) {
        return '<th class="sortable" data-sort="' + c[0] + '">' + c[1] + (state.sort === c[0] ? (state.dir === 1 ? ' ▲' : ' ▼') : '') + '</th>';
      }).join('');
      const body = rows.map(function (r) {
        return '<tr><td class="mono">' + PF.esc(r.code) + '</td><td>' + PF.esc(r.name) + '</td>' +
          '<td>' + PF.esc(r.account_type) + '</td>' +
          '<td class="align-right">' + PF.inr(r.opening_balance_paise) + '</td>' +
          '<td class="align-right">' + PF.inr(r.debits_paise) + '</td>' +
          '<td class="align-right">' + PF.inr(r.credits_paise) + '</td>' +
          '<td class="align-right">' + PF.inr(r.expected_balance_paise) + '</td>' +
          '<td class="align-right">' + PF.inr(r.cached_balance_paise) + '</td>' +
          '<td>' + PF.badge(r.status, r.status === 'BALANCED' ? 'green' : 'red') + '</td></tr>';
      }).join('');
      const area = view.querySelector('#recon-area');
      if (!area) return;
      area.innerHTML = '<div class="table-wrap"><table><thead><tr>' + head + '</tr></thead><tbody>' +
        (body || '<tr><td colspan="9"><div class="empty">No accounts match these filters.</div></td></tr>') +
        '</tbody></table></div>';
      area.querySelectorAll('[data-sort]').forEach(function (th) {
        th.onclick = function () {
          const key = th.dataset.sort;
          if (state.sort === key) state.dir *= -1; else { state.sort = key; state.dir = 1; }
          renderRecon();
        };
      });
      const count = view.querySelector('#recon-count');
      if (count) count.textContent = rows.length + ' / ' + recon.rows.length + ' accounts';
    }

    function render() {
      const recon = data.recon;
      const s = data.status.summary || {};
      const cat = Object.entries(data.categories.summary || {});
      const totalSpend = cat.reduce(function (a, kv) { return a + kv[1]; }, 0);
      const max = cat.reduce(function (m, kv) { return Math.max(m, kv[1]); }, 1);

      view.innerHTML = PF.sectionHead('Financial Analytics',
        'Live figures computed from the immutable journal — adjust ranges, expand charts, drill into reconciliation',
        '<div class="flex gap-1"><button class="btn btn-sm" id="an-refresh">↻ Refresh</button>' +
        '<button class="btn btn-sm" id="an-export">⇩ Export CSV</button></div>') +

        '<div class="analytics-toolbar">' +
          '<span class="toolbar-label">CASH FLOW</span>' +
          '<div class="seg" id="seg-months">' +
            [6, 12].map(function (v) { return '<button data-v="' + v + '" class="' + (state.months === v ? 'active' : '') + '">' + v + 'M</button>'; }).join('') +
          '</div>' +
          '<span class="toolbar-label">VELOCITY</span>' +
          '<div class="seg" id="seg-days">' +
            [7, 14, 30].map(function (v) { return '<button data-v="' + v + '" class="' + (state.days === v ? 'active' : '') + '">' + v + 'D</button>'; }).join('') +
          '</div>' +
          '<span class="toolbar-note">All numbers from raw ledger lines</span>' +
        '</div>' +

        '<div class="grid grid-4 mb-2">' +
          mini('Completed', s.completed || 0, 'green', 'mini-completed') +
          mini('Pending', s.pending || 0, '', 'mini-pending') +
          mini('Rejected / Cancelled', s.rejected || 0, 'red', 'mini-rejected') +
          mini('Categorised Spend', PF.inr(totalSpend), 'blue', 'mini-spend') +
        '</div>' +

        '<div class="tab-bar"><button class="tab-btn ' + (state.tab === 'charts' ? 'active' : '') + '" data-tab="charts">Charts</button>' +
          '<button class="tab-btn ' + (state.tab === 'recon' ? 'active' : '') + '" data-tab="recon">Reconciliation</button></div>' +

        (state.tab === 'charts' ?
          '<div class="grid grid-2 mb-2">' +
            chartCard(charts[0], 'Cumulative received vs spent', 0) +
            chartCard(charts[1], 'Spending distribution by category', 1) +
            chartCard(charts[2], 'Daily transaction count and volume', 2) +
            chartCard(charts[3], 'Completed vs pending vs rejected', 3) +
          '</div>' +
          '<div class="card"><div class="card-head"><div class="card-title">Category breakdown</div>' +
            '<span class="badge blue">' + cat.length + ' categories</span></div>' +
            (cat.length ? cat.map(function (kv) {
              const pct = Math.max(3, Math.round(kv[1] / max * 100));
              return '<div class="breakdown-row"><span>' + PF.esc(kv[0]) + '</span>' +
                '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
                '<b>' + PF.inr(kv[1]) + '</b></div>';
            }).join('') : '<div class="empty">No spending data.</div>') +
          '</div>' :
          '<div class="card"><div class="card-head"><div><div class="card-title">Account Reconciliation</div>' +
            '<div class="card-sub">Expected balance (opening ± movements) must equal cached balance</div></div>' +
            '<span class="badge ' + (recon.discrepancies ? 'red' : 'green') + '">' +
            (recon.discrepancies ? recon.discrepancies + ' discrepancies' : 'ALL BALANCED') + '</span></div>' +
            '<div class="recon-toolbar">' +
              '<input id="recon-search" placeholder="Search account code or name…" value="' + PF.esc(state.q) + '">' +
              '<div class="seg" id="seg-filter">' +
                ['ALL', 'BALANCED', 'DISCREPANCY'].map(function (v) {
                  return '<button data-v="' + v + '" class="' + (state.filter === v ? 'active' : '') + '">' + v + '</button>';
                }).join('') +
              '</div>' +
              '<span class="toolbar-note" id="recon-count"></span>' +
            '</div>' +
            '<div id="recon-area"></div>' +
          '</div>'
        );

      const num = function (id, v) { const n = view.querySelector('#' + id); if (n) PF.animateNumber(n, v, '', ''); };
      num('mini-completed', s.completed || 0);
      num('mini-pending', s.pending || 0);
      num('mini-rejected', s.rejected || 0);
      const spendNode = view.querySelector('#mini-spend');
      if (spendNode) PF.animateNumber(spendNode, totalSpend, 'Rs. ', '');

      view.querySelectorAll('#seg-months button').forEach(function (b) {
        b.onclick = function () { state.months = Number(b.dataset.v); load(); };
      });
      view.querySelectorAll('#seg-days button').forEach(function (b) {
        b.onclick = function () { state.days = Number(b.dataset.v); load(); };
      });
      view.querySelector('#an-refresh').onclick = load;
      view.querySelector('#an-export').onclick = function () {
        const head = 'Code,Name,Type,Opening Paise,Debits Paise,Credits Paise,Expected Paise,Cached Paise,Status\n';
        const body = recon.rows.map(function (r) {
          return [r.code, r.name, r.account_type, r.opening_balance_paise, r.debits_paise,
            r.credits_paise, r.expected_balance_paise, r.cached_balance_paise, r.status]
            .map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(',');
        }).join('\n');
        const uri = URL.createObjectURL(new Blob([head + body], { type: 'text/csv' }));
        downloadUri(uri, 'payflow-reconciliation.csv');
        URL.revokeObjectURL(uri);
      };
      view.querySelectorAll('[data-tab]').forEach(function (b) {
        b.onclick = function () { state.tab = b.dataset.tab; render(); };
      });
      view.querySelectorAll('[data-zoom]').forEach(function (b) {
        b.onclick = function () {
          const c = charts[Number(b.dataset.zoom)];
          const modal = PF.modal('<div class="modal-head"><h3>' + PF.esc(c.title) + '</h3></div>' +
            '<div class="chart-frame"><img src="' + c.image + '" alt="' + PF.esc(c.title) + '"></div>' +
            '<div class="chart-summary mt-2">' + JSON.stringify(c.summary, null, 2).replace(/"/g, '') + '</div>' +
            '<div class="modal-foot"><button class="btn" id="zoom-close">Close</button></div>', true);
          modal.querySelector('#zoom-close').onclick = PF.closeModal;
        };
      });
      view.querySelectorAll('[data-dl]').forEach(function (b) {
        b.onclick = function () { downloadUri(charts[Number(b.dataset.dl)].image, 'payflow-chart-' + b.dataset.dl + '.svg'); };
      });

      if (state.tab === 'recon') {
        renderRecon();
        view.querySelector('#recon-search').oninput = function (e) { state.q = e.target.value; renderRecon(); };
        view.querySelectorAll('#seg-filter button').forEach(function (b) {
          b.onclick = function () { state.filter = b.dataset.v; render(); };
        });
      }
    }

    await load();
  };
})();
