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
    async function load() {
      const params = new URLSearchParams();
      const cat = view.querySelector('#f-cat').value;
      const start = view.querySelector('#f-start').value;
      const end = view.querySelector('#f-end').value;
      if (cat) params.set('category', cat);
      if (start) params.set('start_date', start);
      if (end) params.set('end_date', end);
      rows = await PF.api('/transactions?' + params.toString());
      view.querySelector('#tx-table').innerHTML = PF.table(
        ['TXN ID', 'Date', 'Description', 'Category', 'Counterparty', 'Type', 'Amount', 'Status', 'Receipt'],
        rows.map(function (t) {
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
      );
      view.querySelectorAll('[data-receipt]').forEach(function (b) {
        b.onclick = function () { PF.downloadReceipt(b.dataset.receipt); };
      });
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
            amount_paise: Math.round(parseFloat(modal.querySelector('#r-amount').value) * 100),
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
    const [cashflow, categories, velocity, status, recon] = await Promise.all([
      PF.api('/analytics/chart/cashflow?months=12'),
      PF.api('/analytics/chart/categories'),
      PF.api('/analytics/chart/velocity?days=14'),
      PF.api('/analytics/chart/status'),
      PF.api('/analytics/reconciliation'),
    ]);
    const chartCard = function (data, subtitle) {
      return '<div class="card"><div class="card-head"><div><div class="card-title">' + PF.esc(data.title) +
        '</div><div class="card-sub">' + subtitle + '</div></div></div>' +
        '<div class="chart-frame"><img src="' + data.image + '" alt="' + PF.esc(data.title) + '"></div></div>';
    };
    const reconRows = recon.rows.map(function (r) {
      return '<tr><td class="mono">' + PF.esc(r.code) + '</td><td>' + PF.esc(r.name) + '</td>' +
        '<td>' + r.account_type + '</td><td class="align-right">' + PF.inr(r.opening_balance_paise) + '</td>' +
        '<td class="align-right">' + PF.inr(r.debits_paise) + '</td>' +
        '<td class="align-right">' + PF.inr(r.credits_paise) + '</td>' +
        '<td class="align-right">' + PF.inr(r.expected_balance_paise) + '</td>' +
        '<td class="align-right">' + PF.inr(r.cached_balance_paise) + '</td>' +
        '<td>' + PF.badge(r.status, r.status === 'BALANCED' ? 'green' : 'red') + '</td></tr>';
    }).join('');
    view.innerHTML = PF.sectionHead('Financial Analytics', 'All figures computed from raw ledger lines with Pandas; rendered by Matplotlib (Agg)',
      PF.badge(recon.all_balanced ? 'RECONCILED' : 'DISCREPANCY', recon.all_balanced ? 'green' : 'red')) +
      '<div class="grid grid-2 mb-2">' +
        chartCard(cashflow, 'Cumulative inflow vs outflow') + chartCard(categories, 'Spending mix by category') +
        chartCard(velocity, 'Daily count and volume') + chartCard(status, 'Completed / pending / rejected') +
      '</div>' +
      '<div class="card"><div class="card-head"><div><div class="card-title">Account Reconciliation</div>' +
        '<div class="card-sub">Opening ± movements must equal cached balance for every account</div></div>' +
        '<span class="badge ' + (recon.discrepancies ? 'red' : 'green') + '">' + recon.discrepancies + ' discrepancies</span></div>' +
        PF.table(['Code', 'Account', 'Type', 'Opening', 'Debits', 'Credits', 'Expected', 'Cached', 'Status'], reconRows, 'No accounts.') +
      '</div>';
  };
})();
