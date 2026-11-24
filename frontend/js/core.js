/* PAYFLOW shell, routing and core payment views. */
(function () {
  const PF = window.PF;
  const state = PF.state = { user: null, permissions: [], section: 'overview' };

  const NAV = [
    { group: 'OVERVIEW', items: [{ id: 'overview', label: 'Overview', icon: '◈' }] },
    { group: 'PAYMENTS', items: [
      { id: 'payments', label: 'Payment Hub', icon: '⌁' },
      { id: 'send', label: 'Send Money', icon: '➤' },
      { id: 'receive', label: 'Receive Money', icon: '⇩' },
      { id: 'scan', label: 'Scan & Pay', icon: '▣' },
      { id: 'requests', label: 'Payment Requests', icon: '⇄', roles: ['Customer', 'Merchant'] },
    ] },
    { group: 'ACCOUNT', items: [
      { id: 'beneficiaries', label: 'Beneficiaries', icon: '♙', roles: ['Customer', 'Merchant'] },
      { id: 'wallets', label: 'Wallets', icon: '▤', roles: ['Customer', 'Merchant'] },
      { id: 'transactions', label: 'Transactions', icon: '≡' },
      { id: 'bills', label: 'Bills & Recharges', icon: '⚡', roles: ['Customer', 'Merchant'] },
      { id: 'cards', label: 'Cards (Simulated)', icon: '▭' },
      { id: 'analytics', label: 'Analytics', icon: '▥' },
    ] },
    { group: 'CONTROL', items: [
      { id: 'security', label: 'Security Centre', icon: '⛨' },
      { id: 'settings', label: 'Settings', icon: '⚙' },
    ] },
    { group: 'ADMINISTRATION', roles: ['Operator', 'Auditor', 'Administrator'], items: [
      { id: 'accounts', label: 'Account Management', icon: '▦', roles: ['Operator', 'Auditor', 'Administrator'] },
      { id: 'ledger', label: 'Ledger Management', icon: '⌗', roles: ['Operator', 'Auditor', 'Administrator'] },
      { id: 'users', label: 'User Management', icon: '♟', roles: ['Administrator'] },
      { id: 'audit', label: 'Audit Logs', icon: '◷', roles: ['Auditor', 'Administrator'] },
      { id: 'monitoring', label: 'System Monitoring', icon: '◉', roles: ['Administrator'] },
    ] },
  ];

  const TITLES = {
    overview: ['Overview', 'Your financial command centre'],
    payments: ['Payment Hub', 'Every way to move money, in one place'],
    send: ['Send Money', 'Transfer instantly using VPA, phone or saved contact'],
    receive: ['Receive Money', 'Your VPA, QR and payment links'],
    scan: ['Scan & Pay', 'Simulated QR checkout at verified merchants'],
    requests: ['Payment Requests', 'Collect money with explicit payer approval'],
    beneficiaries: ['Beneficiaries', 'Saved contacts and favourites'],
    wallets: ['Wallets', 'Balances, funding and internal transfers'],
    transactions: ['Transactions', 'Immutable journal activity and receipts'],
    bills: ['Bills & Recharges', 'Eight simulated utility biller categories'],
    cards: ['Virtual Cards', 'Simulated cards with freeze controls'],
    analytics: ['Analytics', 'Pandas + Matplotlib financial intelligence'],
    security: ['Security Centre', 'Passwords, MFA and active sessions'],
    settings: ['Settings', 'Profile, privacy and preferences'],
    accounts: ['Account Management', 'Chart of accounts'],
    ledger: ['Ledger Management', 'Journal entries, trial balance and corrections'],
    users: ['User Management', 'Roles and account locks'],
    audit: ['Audit Logs', 'Immutable operational and security trail'],
    monitoring: ['System Monitoring', 'JSON store health and integrity checks'],
  };

  function allowed(item) {
    if (!item.roles) return true;
    return item.roles.includes(state.user.role) || state.user.role === 'Administrator';
  }

  PF.buildShell = function () {
    const nav = NAV.filter(function (g) { return !g.roles || g.roles.includes(state.user.role) || state.user.role === 'Administrator'; })
      .map(function (g) {
        return '<div class="nav-section-title">' + g.group + '</div>' + g.items.filter(allowed).map(function (item) {
          return '<div class="nav-item" data-nav="' + item.id + '">' +
            '<span class="nav-icon">' + item.icon + '</span>' +
            '<span class="nav-label">' + item.label + '</span></div>';
        }).join('');
      }).join('');

    const initials = state.user.full_name.split(/\s+/).map(function (p) { return p[0]; }).join('').slice(0, 2).toUpperCase();
    document.getElementById('app').innerHTML =
      '<div class="app-shell">' +
        '<aside class="sidebar" id="sidebar">' +
          '<div class="brand"><div class="brand-mark">P</div><div class="brand-name">PAY<span>FLOW</span></div></div>' +
          '<nav class="nav-scroll">' + nav + '</nav>' +
          '<div class="sidebar-footer">' +
            '<div class="avatar">' + PF.esc(initials) + '</div>' +
            '<div class="profile-meta"><b>' + PF.esc(state.user.full_name) + '</b><small>' + PF.esc(state.user.role) + ' · Simulated</small></div>' +
            '<button class="collapse-btn" id="collapse-btn" title="Collapse sidebar">☰</button>' +
          '</div>' +
        '</aside>' +
        '<div class="overlay" id="nav-overlay"></div>' +
        '<div class="main">' +
          '<header class="topbar">' +
            '<button class="mobile-menu" id="mobile-menu" title="Open menu">☰</button>' +
            '<div><div class="page-title" id="page-title">Overview</div><div class="page-subtitle" id="page-subtitle"></div></div>' +
            '<div class="topbar-right">' +
              '<span class="vpa-chip" id="top-vpa">' + PF.esc(state.user.vpa) + '</span>' +
              '<div class="avatar">' + PF.esc(initials) + '</div>' +
              '<div class="user-meta"><b>' + PF.esc(state.user.full_name) + '</b><small>' + PF.esc(state.user.role) + '</small></div>' +
              '<button class="icon-btn" id="logout-btn" title="Sign out">⇥</button>' +
            '</div>' +
          '</header>' +
          '<main class="view" id="view"></main>' +
        '</div>' +
      '</div>' +
      '<div class="toast-stack" id="toast-stack"></div>';

    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('nav-overlay');
    function closeMobile() { sidebar.classList.remove('open'); overlay.classList.remove('show'); }
    document.getElementById('collapse-btn').onclick = function () {
      if (window.innerWidth <= 860) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('show', sidebar.classList.contains('open'));
      } else {
        sidebar.classList.toggle('collapsed');
      }
    };
    document.getElementById('mobile-menu').onclick = function () {
      sidebar.classList.add('open');
      overlay.classList.add('show');
    };
    overlay.onclick = closeMobile;
    document.getElementById('logout-btn').onclick = async function () {
      await PF.api('/auth/logout', { method: 'POST' });
      location.href = '/login.html';
    };
    document.querySelectorAll('[data-nav]').forEach(function (node) {
      node.onclick = function () { closeMobile(); location.hash = '#/' + node.dataset.nav; };
    });
  };

  PF.setSection = function (id) {
    state.section = id;
    document.querySelectorAll('[data-nav]').forEach(function (n) {
      n.classList.toggle('active', n.dataset.nav === id);
    });
    const meta = TITLES[id] || ['PAYFLOW', ''];
    document.getElementById('page-title').textContent = meta[0];
    document.getElementById('page-subtitle').textContent = meta[1];
  };

  PF.route = async function () {
    let id = (location.hash || '#/overview').replace(/^#\/?/, '') || 'overview';
    if (!TITLES[id]) id = 'overview';
    PF.setSection(id);
    const view = document.getElementById('view');
    view.innerHTML = '<div class="grid grid-4"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div><div class="card skeleton mt-2" style="min-height:260px"></div>';
    try {
      if (PF.views[id]) await PF.views[id](view);
      else view.innerHTML = '<div class="empty">This view is not available for your role.</div>';
    } catch (err) {
      view.innerHTML = '<div class="card"><div class="danger">Unable to load this view.</div><p class="muted">' + PF.esc(err.message) + '</p></div>';
    }
  };

  PF.bindGoto = function (root) {
    root.querySelectorAll('[data-goto]').forEach(function (node) {
      node.onclick = function () { location.hash = '#/' + node.dataset.goto; };
    });
  };

  // -------------------------------------------------------------------------
  // Overview
  // -------------------------------------------------------------------------
  PF.views.overview = async function (view) {
    const [dash, cashflow, categories, status, recon] = await Promise.all([
      PF.api('/analytics/dashboard'),
      PF.api('/analytics/chart/cashflow?months=6'),
      PF.api('/analytics/chart/categories'),
      PF.api('/analytics/chart/status'),
      PF.api('/analytics/reconciliation'),
    ]);
    const kpi = function (label, value, tone, foot) {
      return '<div class="kpi"><div class="kpi-label">' + label + '</div>' +
        '<div class="kpi-value ' + (tone || '') + '">' + value + '</div>' +
        '<div class="kpi-foot">' + (foot || '') + '</div></div>';
    };
    const recent = dash.recent_transactions.map(function (t) {
      const credit = t.direction === 'CREDIT';
      return '<tr><td class="mono">' + PF.esc(t.transaction_id) + '</td>' +
        '<td>' + PF.esc(t.description) + '</td>' +
        '<td>' + PF.esc(t.counterparty) + '</td>' +
        '<td>' + PF.badge(t.category, 'blue') + '</td>' +
        '<td class="align-right ' + (credit ? 'success' : 'danger') + '">' + (credit ? '+' : '−') + PF.inr(t.amount_paise) + '</td>' +
        '<td class="muted text-xs nowrap">' + PF.esc(PF.fmtDate(t.timestamp)) + '</td></tr>';
    });
    const s = status.summary || {};

    view.innerHTML =
      PF.sectionHead('Financial overview', 'Live figures computed from the immutable ledger') +
      '<div class="grid grid-4 mb-2">' +
        kpi('Total Balance', PF.inr(dash.total_balance_paise), 'blue', dash.wallet_count + ' active wallet(s)') +
        kpi('Total Credits', PF.inr(dash.inflow_paise), 'green', 'Money received') +
        kpi('Total Debits', PF.inr(dash.outflow_paise), 'red', 'Money spent') +
        kpi('Transactions', String(dash.transaction_count), '', 'Journal entries recorded') +
      '</div>' +
      '<div class="grid grid-4 mb-2">' +
        kpi('Successful Payments', String(s.completed || 0), 'green', 'Completed entries') +
        kpi('Pending', String(s.pending || 0), '', 'Awaiting approval') +
        kpi('Failed / Rejected', String(s.rejected || 0), 'red', 'Declined or cancelled') +
        kpi('Reconciliation', recon.all_balanced ? 'Balanced' : (recon.discrepancies + ' issues'),
            recon.all_balanced ? 'green' : 'red', 'Cached vs expected balances') +
      '</div>' +
      '<div class="grid grid-2 mb-2">' +
        '<div class="card"><div class="card-head"><div><div class="card-title">Cash Flow Trend</div>' +
          '<div class="card-sub">Cumulative received vs spent · last 6 months</div></div>' +
          '<span class="badge green">LIVE</span></div><div class="chart-frame"><img src="' + cashflow.image + '" alt="Cash flow chart"></div></div>' +
        '<div class="card"><div class="card-head"><div><div class="card-title">Spending Mix</div>' +
          '<div class="card-sub">Computed from immutable ledger lines</div></div>' +
          '<span class="card-action" data-goto="analytics">Full report →</span></div>' +
          '<div class="chart-frame"><img src="' + categories.image + '" alt="Category chart"></div></div>' +
      '</div>' +
      '<div class="grid grid-main">' +
        '<div class="card"><div class="card-head"><div><div class="card-title">Recent Activity</div>' +
          '<div class="card-sub">Latest postings across your accounts</div></div>' +
          '<span class="card-action" data-goto="transactions">View all →</span></div>' +
          PF.table(['TXN ID', 'Description', 'Counterparty', 'Category', 'Amount', 'Time'], recent, 'No transactions yet.') +
        '</div>' +
        '<div class="card"><div class="card-head"><div class="card-title">Quick Actions</div></div>' +
          '<div class="grid" style="gap:12px">' +
            '<button class="btn btn-primary btn-block" data-goto="send">➤ Send Money</button>' +
            '<button class="btn btn-block" data-goto="receive">⇩ Receive / QR</button>' +
            '<button class="btn btn-block" data-goto="scan">▣ Scan & Pay</button>' +
            '<button class="btn btn-block" data-goto="bills">⚡ Pay a Bill</button>' +
          '</div>' +
          '<div class="mt-3 card-sub">All movements are recorded as balanced double-entry journal lines in integer paise.</div>' +
        '</div>' +
      '</div>';
    PF.bindGoto(view);
  };

  // -------------------------------------------------------------------------
  // Payment hub
  // -------------------------------------------------------------------------
  PF.views.payments = async function (view) {
    const tiles = [
      { id: 'send', icon: '➤', title: 'Send Money', sub: 'VPA, phone, username or beneficiary' },
      { id: 'receive', icon: '⇩', title: 'Receive Money', sub: 'Personal VPA & dynamic QR' },
      { id: 'scan', icon: '▣', title: 'Scan & Pay', sub: 'Merchant QR checkout simulator' },
      { id: 'requests', icon: '⇄', title: 'Collect Requests', sub: 'Pull payments with approval' },
      { id: 'beneficiaries', icon: '♙', title: 'Beneficiaries', sub: 'Saved contacts & favourites' },
      { id: 'transactions', icon: '≡', title: 'Transactions', sub: 'Receipts & immutable history' },
    ].filter(function (t) {
      return !['requests', 'beneficiaries'].includes(t.id) || ['Customer', 'Merchant'].includes(state.user.role);
    }).map(function (t) {
      return '<div class="tile" data-goto="' + t.id + '"><div class="tile-icon">' + t.icon + '</div>' +
        '<div class="tile-title">' + t.title + '</div><div class="tile-sub">' + t.sub + '</div></div>';
    }).join('');
    view.innerHTML = PF.sectionHead('Payment Hub', 'Choose a flow to get started') +
      '<div class="grid grid-3">' + tiles + '</div>';
    PF.bindGoto(view);
  };

  // -------------------------------------------------------------------------
  // Send money
  // -------------------------------------------------------------------------
  PF.views.send = async function (view) {
    const [wallets, beneficiaries] = await Promise.all([
      PF.api('/wallets'), PF.api('/beneficiaries').catch(function () { return []; }),
    ]);
    const options = wallets.map(function (w) {
      return '<option value="' + w.id + '">' + PF.esc(w.label) + ' · ' + PF.inr(w.balance_paise) + '</option>';
    }).join('');
    const favs = beneficiaries.filter(function (b) { return b.favorite; }).map(function (b) {
      return '<button class="btn btn-sm" data-pay="' + PF.esc(b.vpa) + '">★ ' + PF.esc(b.nickname) + '</button>';
    }).join('');

    view.innerHTML = PF.sectionHead('Send Money', 'Funds move through a balanced double-entry posting') +
      '<div class="grid grid-main">' +
        '<div class="card"><div class="card-head"><div class="card-title">New Payment</div>' +
          (favs ? '<div class="flex gap-1">' + favs + '</div>' : '') + '</div>' +
          '<form id="send-form" class="form-grid">' +
            '<div class="field"><label>Recipient (VPA / phone / username / beneficiary)</label>' +
              '<input id="recipient" required placeholder="rohit_kumar@payflow" autocomplete="off"></div>' +
            '<div class="form-row">' +
              '<div class="field"><label>Amount (INR)</label><div class="input-prefix"><span>₹</span>' +
                '<input id="amount" type="number" min="1" step="0.01" required placeholder="0.00"></div></div>' +
              '<div class="field"><label>Platform fee (INR)</label><div class="input-prefix"><span>₹</span>' +
                '<input id="fee" type="number" min="0" step="0.01" value="0"></div></div>' +
            '</div>' +
            '<div class="field"><label>Note</label><input id="note" placeholder="What is this for?"></div>' +
            '<div class="form-row">' +
              '<div class="field"><label>Debit wallet</label><select id="wallet">' + options + '</select></div>' +
              '<div class="field"><label>TOTP (required above ₹10,000)</label>' +
                '<input id="totp" placeholder="6-digit code" inputmode="numeric"></div>' +
            '</div>' +
            '<button class="btn btn-primary" type="submit">Review & Pay →</button>' +
          '</form>' +
        '</div>' +
        '<div class="card"><div class="card-title">Pre-flight checks</div>' +
          '<div class="mt-2 text-sm secondary" style="line-height:1.9">' +
            '✓ Recipient resolved &amp; active<br>✓ Sender balance verified<br>' +
            '✓ Daily limit enforced<br>✓ TOTP step-up above ₹10,000<br>' +
            '✓ Atomic locked posting<br>✓ Both parties notified' +
          '</div>' +
          '<div class="mt-3 card-sub">The ledger debits the recipient wallet and credits the sender wallet in one balanced entry.</div>' +
        '</div>' +
      '</div>';

    const prefilled = sessionStorage.getItem('pf_recipient');
    if (prefilled) {
      view.querySelector('#recipient').value = prefilled;
      sessionStorage.removeItem('pf_recipient');
    }
    view.querySelectorAll('[data-pay]').forEach(function (b) {
      b.onclick = function () { view.querySelector('#recipient').value = b.dataset.pay; };
    });
    view.querySelector('#send-form').onsubmit = async function (e) {
      e.preventDefault();
      const body = {
        recipient: view.querySelector('#recipient').value.trim(),
        amount_paise: PF.toPaise(view.querySelector('#amount').value),
        fee_paise: PF.toPaise(view.querySelector('#fee').value || '0'),
        note: view.querySelector('#note').value || 'Payment',
        from_wallet_id: view.querySelector('#wallet').value,
      };
      const totp = view.querySelector('#totp').value.trim();
      if (totp) body.totp_code = totp;
      try {
        const result = await PF.api('/payments/send', { method: 'POST', body: body });
        PF.receiptModal(result.receipt);
      } catch (err) { PF.showError(err); }
    };
  };

  PF.receiptModal = function (receipt) {
    const modal = PF.modal(
      '<div class="modal-head"><div><h3>Payment Successful</h3><div class="card-sub">Digital receipt · ' + PF.esc(receipt.transaction_id) + '</div></div>' + PF.badge(receipt.status, 'green') + '</div>' +
      '<div class="card" style="box-shadow:none"><div class="kpi-value green">' + PF.inr(receipt.total_paise) + '</div>' +
      '<div class="muted text-xs mt-1">' + PF.esc(receipt.description) + '</div></div>' +
      '<div class="mt-2 text-sm secondary" style="line-height:2">' +
        '<div class="between"><span>Reference</span><b class="mono">' + PF.esc(receipt.reference) + '</b></div>' +
        '<div class="between"><span>Counterparty</span><b>' + PF.esc(receipt.counterparty) + '</b></div>' +
        '<div class="between"><span>Fee</span><b>' + PF.inr(receipt.fee_paise) + '</b></div>' +
        '<div class="between"><span>Timestamp</span><b>' + PF.esc(PF.fmtDate(receipt.timestamp)) + '</b></div>' +
      '</div>' +
      '<div class="modal-foot"><button class="btn" id="receipt-close">Close</button>' +
      '<button class="btn btn-primary" id="receipt-download">Download Receipt</button></div>'
    );
    modal.querySelector('#receipt-close').onclick = PF.closeModal;
    modal.querySelector('#receipt-download').onclick = function () { PF.downloadReceipt(receipt.transaction_id); };
  };

  // -------------------------------------------------------------------------
  // Receive money
  // -------------------------------------------------------------------------
  PF.views.receive = async function (view) {
    let lastQr = null;
    const vpa = state.user.vpa;
    view.innerHTML = PF.sectionHead('Receive Money', 'Share your QR, VPA or payment link') +
      '<div class="receive-grid">' +
        '<div class="card qr-card">' +
          '<div class="card-head"><div><div class="card-title">Your payment QR</div>' +
            '<div class="card-sub">Scan with a PAYFLOW app to pay you instantly</div></div>' +
            '<span class="badge blue">UPI-STYLE</span></div>' +
          '<div class="qr-stage"><div class="qr-glow"></div>' +
            '<div class="qr-frame" id="qr-area"><div class="muted">Generating…</div></div></div>' +
          '<div class="qr-identity"><div class="qr-name">' + PF.esc(state.user.full_name) + '</div>' +
            '<div class="mono">' + PF.esc(vpa) + '</div></div>' +
          '<div class="qr-actions">' +
            '<button class="btn btn-sm" id="copy-raw">Copy payload</button>' +
            '<button class="btn btn-sm" id="download-qr">Download QR</button>' +
          '</div>' +
        '</div>' +

        '<div class="card">' +
          '<div class="card-head"><div><div class="card-title">Create a QR</div>' +
            '<div class="card-sub">Add an amount and note to generate a dynamic QR</div></div></div>' +
          '<div class="vpa-display"><span>Your VPA</span><b>' + PF.esc(vpa) + '</b>' +
            '<button class="btn btn-sm" id="copy-vpa">Copy</button></div>' +
          '<div class="field"><label>Quick amount</label><div class="chip-row">' +
            [100, 250, 500, 1000].map(function (n) {
              return '<button type="button" class="chip" data-amount="' + n + '">₹' + n + '</button>';
            }).join('') +
            '<button type="button" class="chip" data-amount="clear">Clear</button>' +
          '</div></div>' +
          '<div class="form-row mt-2">' +
            '<div class="field"><label>Amount (INR, optional)</label><div class="input-prefix"><span>₹</span>' +
              '<input id="qr-amount" type="number" min="1" step="0.01" placeholder="Leave blank for static QR"></div></div>' +
            '<div class="field"><label>Note (optional)</label><input id="qr-note" placeholder="Invoice #123"></div>' +
          '</div>' +
          '<button class="btn btn-primary btn-block mt-2" id="qr-generate">Generate Dynamic QR</button>' +
          '<div id="qr-status" class="receive-status">Static QR ready — share it anywhere.</div>' +
        '</div>' +
      '</div>' +

      '<div class="card mt-2">' +
        '<div class="card-head"><div><div class="card-title">Payment links</div>' +
          '<div class="card-sub">Copy a link or the raw PAYFLOW payload</div></div></div>' +
        '<div class="field"><label>Simulated payment link</label>' +
          '<div class="copy-row"><input id="qr-link" readonly><button class="btn btn-sm" id="copy-link">Copy</button></div></div>' +
        '<div class="field mt-2"><label>Raw payload</label>' +
          '<div class="copy-row"><input id="qr-raw" readonly><button class="btn btn-sm" id="copy-payload">Copy</button></div></div>' +
        '<div class="receive-steps">' +
          '<div class="step-row"><b>01 · Share</b><p>Send your QR, VPA or payment link to the person paying you.</p></div>' +
          '<div class="step-row"><b>02 · Pay</b><p>They scan or paste the payload and confirm the payment in their app.</p></div>' +
          '<div class="step-row"><b>03 · Receive</b><p>The amount is credited to your wallet as a balanced ledger entry.</p></div>' +
        '</div>' +
      '</div>';

    async function loadQr() {
      const amount = view.querySelector('#qr-amount').value;
      const note = view.querySelector('#qr-note').value;
      let url = '/payments/qr?';
      if (amount) url += 'amount_paise=' + PF.toPaise(amount) + '&';
      if (note) url += 'note=' + encodeURIComponent(note);
      try {
        const data = await PF.api(url);
        lastQr = data;
        view.querySelector('#qr-area').innerHTML = data.svg;
        view.querySelector('#qr-link').value = 'https://payflow.local/pay?' + data.payload.split('?')[1];
        view.querySelector('#qr-raw').value = data.payload;
        view.querySelector('#qr-status').textContent = amount
          ? 'Dynamic QR ready for ' + PF.inr(PF.toPaise(amount)) + '.'
          : 'Static QR ready — share it anywhere.';
        view.querySelectorAll('.chip').forEach(function (c) { c.classList.remove('active'); });
        if (amount) {
          const chip = Array.from(view.querySelectorAll('.chip')).find(function (c) {
            return c.dataset.amount === String(Math.round(PF.toPaise(amount) / 100));
          });
          if (chip) chip.classList.add('active');
        }
      } catch (err) { PF.showError(err); }
    }
    view.querySelector('#qr-generate').onclick = loadQr;
    view.querySelectorAll('.chip').forEach(function (chip) {
      chip.onclick = function () {
        view.querySelector('#qr-amount').value = chip.dataset.amount === 'clear' ? '' : chip.dataset.amount;
        loadQr();
      };
    });
    view.querySelector('#copy-vpa').onclick = function () { PF.copy(vpa); };
    view.querySelector('#copy-link').onclick = function () { PF.copy(view.querySelector('#qr-link').value); };
    view.querySelector('#copy-payload').onclick = function () { PF.copy(view.querySelector('#qr-raw').value); };
    view.querySelector('#copy-raw').onclick = function () { PF.copy(view.querySelector('#qr-raw').value); };
    view.querySelector('#download-qr').onclick = function () {
      if (!lastQr) return;
      const blob = new Blob([lastQr.svg], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'payflow-qr-' + vpa.replace(/[^a-z0-9]/gi, '-') + '.svg';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      PF.toast('QR code downloaded', 'ok');
    };
    loadQr();
  };

  // -------------------------------------------------------------------------
  // Scan & Pay
  // -------------------------------------------------------------------------
  PF.views.scan = async function (view) {
    const merchants = await PF.api('/payments/merchants');
    const tiles = merchants.map(function (m, i) {
      return '<div class="tile" data-merchant="' + i + '"><div class="tile-icon">' +
        (m.category === 'Travel' ? '🚇' : m.category === 'Grocery' ? '🛒' : '☕') + '</div>' +
        '<div class="tile-title">' + PF.esc(m.name) + (m.verified ? ' <span class="badge green">✓ VERIFIED</span>' : '') + '</div>' +
        '<div class="tile-sub">' + PF.esc(m.category) + ' · ' + PF.esc(m.vpa) + '</div></div>';
    }).join('');

    view.innerHTML = PF.sectionHead('Scan & Pay', 'Upload a generated QR SVG, paste a payload, or pick a verified merchant') +
      '<div class="grid grid-main">' +
        '<div class="card"><div class="card-head"><div class="card-title">QR Payload</div><span class="badge blue">SIMULATOR</span></div>' +
          '<div class="field"><label>Paste payflow://pay payload</label>' +
            '<textarea id="scan-payload" placeholder="payflow://pay?pa=starbucks@payflow&pn=...&am=150.00&cu=INR"></textarea></div>' +
          '<div class="field mt-2"><label>Or upload a PAYFLOW QR image / SVG</label>' +
            '<input type="file" id="scan-file" accept=".svg,.txt,image/*"></div>' +
          '<div id="scan-parse" class="mt-2 text-sm secondary"></div>' +
          '<button class="btn btn-primary mt-2" id="scan-confirm" disabled>Confirm & Pay</button>' +
        '</div>' +
        '<div class="card"><div class="card-title">Verified Merchants</div>' +
          '<div class="card-sub mb-2">Select a merchant to build a QR payload</div>' +
          '<div class="grid" style="gap:10px">' + tiles + '</div>' +
        '</div>' +
      '</div>';

    let parsed = null;
    const payloadInput = view.querySelector('#scan-payload');
    const confirmBtn = view.querySelector('#scan-confirm');
    const parseArea = view.querySelector('#scan-parse');

    function refresh() {
      const value = payloadInput.value.trim();
      parsed = null;
      confirmBtn.disabled = true;
      if (!value.startsWith('payflow://pay?')) {
        parseArea.innerHTML = '<span class="warning">Enter a valid PAYFLOW payload.</span>';
        return;
      }
      const params = new URLSearchParams(value.split('?')[1]);
      const pa = params.get('pa'), am = params.get('am');
      if (!pa || !am) {
        parseArea.innerHTML = '<span class="danger">Missing pa (VPA) or am (amount).</span>';
        return;
      }
      let amountPaise;
      try { amountPaise = PF.toPaise(am); }
      catch (e) {
        parseArea.innerHTML = '<span class="danger">Invalid amount in QR payload.</span>';
        return;
      }
      parsed = { pa: pa, am: am, tn: params.get('tn') || 'QR checkout' };
      confirmBtn.disabled = false;
      parseArea.innerHTML = '<div class="card" style="box-shadow:none">' +
        '<b>' + PF.esc(params.get('pn') || pa) + '</b>' +
        '<div class="muted text-xs">' + PF.esc(pa) + ' · ' + PF.esc(parsed.tn) + '</div>' +
        '<div class="kpi-value green mt-1">' + PF.inr(amountPaise) + '</div></div>';
    }
    payloadInput.oninput = refresh;

    view.querySelector('#scan-file').onchange = function (e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function () {
        const text = String(reader.result);
        const match = text.match(/payflow:\/\/pay\?[^<"\s]+/);
        if (match) {
          const decoded = match[0].replace(/&amp;/g, '&');
          payloadInput.value = decoded;
          refresh();
          PF.toast('QR payload decoded from file', 'ok');
        } else {
          PF.toast('No PAYFLOW payload found in that file', 'err');
        }
      };
      reader.readAsText(file);
    };

    view.querySelectorAll('[data-merchant]').forEach(function (tile) {
      tile.onclick = function () {
        const m = merchants[Number(tile.dataset.merchant)];
        const modal = PF.modal(
          '<div class="modal-head"><h3>Pay ' + PF.esc(m.name) + '</h3></div>' +
          '<div class="card-sub">' + PF.esc(m.category) + ' · ' + PF.esc(m.vpa) + '</div>' +
          '<div class="field mt-2"><label>Amount (INR)</label><div class="input-prefix"><span>₹</span>' +
            '<input id="m-amount" type="number" min="1" step="0.01" placeholder="0.00"></div></div>' +
          '<div class="field mt-2"><label>Note</label><input id="m-note" value="QR checkout"></div>' +
          '<div class="modal-foot"><button class="btn" id="m-cancel">Cancel</button>' +
          '<button class="btn btn-primary" id="m-build">Build Payload</button></div>'
        );
        modal.querySelector('#m-cancel').onclick = PF.closeModal;
        modal.querySelector('#m-build').onclick = function () {
          const amount = modal.querySelector('#m-amount').value;
          if (!amount || parseFloat(amount) <= 0) { PF.toast('Enter a valid amount', 'err'); return; }
          const note = modal.querySelector('#m-note').value;
          payloadInput.value = 'payflow://pay?pa=' + encodeURIComponent(m.vpa) +
            '&pn=' + encodeURIComponent(m.name) + '&am=' + parseFloat(amount).toFixed(2) +
            '&tn=' + encodeURIComponent(note) + '&cu=INR';
          PF.closeModal();
          refresh();
        };
      };
    });

    confirmBtn.onclick = async function () {
      try {
        const result = await PF.api('/payments/scan-pay', { method: 'POST', body: { payload: payloadInput.value.trim() } });
        PF.receiptModal(result.receipt);
      } catch (err) { PF.showError(err); }
    };
  };

  // -------------------------------------------------------------------------
  // Wallets
  // -------------------------------------------------------------------------
  PF.views.wallets = async function (view) {
    const wallets = await PF.api('/wallets');
    const cards = wallets.map(function (w) {
      return '<div class="card"><div class="card-head"><div>' +
        '<div class="card-title">' + PF.esc(w.label) + (w.is_primary ? ' <span class="badge blue">PRIMARY</span>' : '') + '</div>' +
        '<div class="card-sub mono">' + PF.esc(w.account_id) + '</div></div>' + PF.badge(w.status, 'green') + '</div>' +
        '<div class="kpi-value blue">' + PF.inr(w.balance_paise) + '</div>' +
        '<div class="mt-2 flex gap-1">' +
          '<button class="btn btn-sm btn-primary" data-topup="' + w.id + '">Top up</button>' +
          (wallets.length > 1 ? '<button class="btn btn-sm" data-from="' + w.id + '">Transfer from</button>' : '') +
        '</div></div>';
    }).join('');

    view.innerHTML = PF.sectionHead('Wallets', 'Simulated funding from the platform settlement reserve',
      '<button class="btn btn-primary" id="create-wallet">+ New Wallet</button>') +
      '<div class="grid grid-3 mb-2">' + cards + '</div>' +
      '<div class="grid grid-2">' +
        '<div class="card"><div class="card-title">Internal Transfer</div>' +
          '<form id="internal-form" class="form-grid mt-2">' +
            '<div class="form-row"><div class="field"><label>From</label><select id="int-from">' +
              walletOptions(wallets) + '</select></div>' +
              '<div class="field"><label>To</label><select id="int-to">' + walletOptions(wallets) + '</select></div></div>' +
            '<div class="form-row"><div class="field"><label>Amount (INR)</label><div class="input-prefix"><span>₹</span>' +
              '<input id="int-amount" type="number" min="1" step="0.01" required></div></div>' +
              '<div class="field"><label>Fee (INR)</label><div class="input-prefix"><span>₹</span>' +
              '<input id="int-fee" type="number" min="0" step="0.01" value="0"></div></div></div>' +
            '<button class="btn btn-primary" type="submit">Transfer Between Wallets</button>' +
          '</form></div>' +
        '<div class="card"><div class="card-title">Ledger Note</div>' +
          '<p class="secondary mt-2 text-sm" style="line-height:1.8">All wallet balances are derived from append-only double-entry lines in integer paise. Top-ups increase the wallet (debit) and draw from the settlement reserve (credit), so the global trial balance always sums to zero.</p>' +
        '</div>' +
      '</div>';

    function walletOptions(list) {
      return list.map(function (w) {
        return '<option value="' + w.id + '">' + PF.esc(w.label) + ' · ' + PF.inr(w.balance_paise) + '</option>';
      }).join('');
    }
    function topupModal(walletId) {
      const modal = PF.modal(
        '<div class="modal-head"><h3>Simulated Top-Up</h3></div>' +
        '<div class="field"><label>Amount (INR)</label><div class="input-prefix"><span>₹</span>' +
          '<input id="top-amount" type="number" min="1" step="0.01" placeholder="0.00"></div></div>' +
        '<div class="modal-foot"><button class="btn" id="top-cancel">Cancel</button>' +
          '<button class="btn btn-primary" id="top-go">Add Funds</button></div>'
      );
      modal.querySelector('#top-cancel').onclick = PF.closeModal;
      modal.querySelector('#top-go').onclick = async function () {
        try {
          await PF.api('/wallets/top-up', { method: 'POST', body: {
            wallet_id: walletId,
            amount_paise: PF.toPaise(modal.querySelector('#top-amount').value),
          }});
          PF.closeModal(); PF.toast('Wallet topped up', 'ok'); PF.route();
        } catch (err) { PF.showError(err); }
      };
    }
    view.querySelectorAll('[data-topup]').forEach(function (b) { b.onclick = function () { topupModal(b.dataset.topup); }; });
    view.querySelectorAll('[data-from]').forEach(function (b) {
      b.onclick = function () { view.querySelector('#int-from').value = b.dataset.from; };
    });
    view.querySelector('#create-wallet').onclick = function () {
      const modal = PF.modal(
        '<div class="modal-head"><h3>New Wallet</h3></div>' +
        '<div class="field"><label>Label</label><input id="nw-label" placeholder="Travel Wallet"></div>' +
        '<div class="modal-foot"><button class="btn" id="nw-cancel">Cancel</button>' +
          '<button class="btn btn-primary" id="nw-go">Create</button></div>'
      );
      modal.querySelector('#nw-cancel').onclick = PF.closeModal;
      modal.querySelector('#nw-go').onclick = async function () {
        try {
          await PF.api('/wallets', { method: 'POST', body: { label: modal.querySelector('#nw-label').value } });
          PF.closeModal(); PF.toast('Wallet created', 'ok'); PF.route();
        } catch (err) { PF.showError(err); }
      };
    };
    view.querySelector('#internal-form').onsubmit = async function (e) {
      e.preventDefault();
      try {
        await PF.api('/wallets/transfer', { method: 'POST', body: {
          from_wallet_id: view.querySelector('#int-from').value,
          to_wallet_id: view.querySelector('#int-to').value,
          amount_paise: PF.toPaise(view.querySelector('#int-amount').value),
          fee_paise: PF.toPaise(view.querySelector('#int-fee').value || '0'),
          description: 'Wallet to wallet transfer',
        }});
        PF.toast('Internal transfer complete', 'ok'); PF.route();
      } catch (err) { PF.showError(err); }
    };
  };
})();
