/* PAYFLOW shared client helpers - vanilla ES6, no external dependencies. */
(function () {
  const PF = window.PF = { views: {} };

  PF.api = async function (path, options = {}) {
    const init = {
      method: options.method || 'GET',
      credentials: 'same-origin',
      headers: Object.assign({ 'Content-Type': 'application/json' }, options.headers || {}),
    };
    if (options.body !== undefined) init.body = JSON.stringify(options.body);
    const response = await fetch('/api' + path, init);
    let data = null;
    try { data = await response.json(); } catch (e) { data = {}; }
    if (!response.ok) {
      const err = new Error(data.detail || ('Request failed (' + response.status + ')'));
      err.status = response.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  // Exact string parsing: no floating-point arithmetic touches monetary values.
  PF.toPaise = function (value) {
    const text = String(value == null ? '' : value).trim();
    if (!/^\d+(\.\d{1,2})?$/.test(text)) throw new Error('Enter a valid amount (max 2 decimals)');
    const parts = text.split('.');
    return Number(parts[0]) * 100 + Number((parts[1] || '').padEnd(2, '0'));
  };

  PF.inr = function (paise) {
    return 'Rs. ' + (Number(paise || 0) / 100).toLocaleString('en-IN', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  };
  PF.esc = function (value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  PF.fmtDate = function (iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };
  PF.badge = function (text, tone) {
    return '<span class="badge ' + (tone || 'grey') + '">' + PF.esc(text) + '</span>';
  };

  PF.toast = function (message, kind) {
    const stack = document.getElementById('toast-stack');
    if (!stack) return;
    const node = document.createElement('div');
    node.className = 'toast ' + (kind || 'info');
    node.innerHTML = '<span>' + (kind === 'ok' ? '✅' : kind === 'err' ? '⛔' : 'ℹ️') + '</span><span>' + PF.esc(message) + '</span>';
    stack.appendChild(node);
    setTimeout(function () { node.remove(); }, 4200);
  };

  PF.modal = function (html, wide) {
    PF.closeModal();
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.id = 'modal-backdrop';
    backdrop.innerHTML = '<div class="modal ' + (wide ? 'wide' : '') + '" id="active-modal">' + html + '</div>';
    backdrop.addEventListener('click', function (e) { if (e.target === backdrop) PF.closeModal(); });
    document.body.appendChild(backdrop);
    return document.getElementById('active-modal');
  };
  PF.closeModal = function () {
    const existing = document.getElementById('modal-backdrop');
    if (existing) existing.remove();
  };
  PF.confirm = function (title, message, onConfirm, danger) {
    const modal = PF.modal(
      '<div class="modal-head"><h3>' + PF.esc(title) + '</h3></div>' +
      '<p class="secondary" style="line-height:1.6">' + PF.esc(message) + '</p>' +
      '<div class="modal-foot"><button class="btn" id="confirm-cancel">Cancel</button>' +
      '<button class="btn ' + (danger ? 'btn-danger' : 'btn-primary') + '" id="confirm-ok">Confirm</button></div>'
    );
    modal.querySelector('#confirm-cancel').onclick = PF.closeModal;
    modal.querySelector('#confirm-ok').onclick = function () { PF.closeModal(); onConfirm(); };
  };

  PF.copy = async function (text) {
    try {
      await navigator.clipboard.writeText(text);
      PF.toast('Copied to clipboard', 'ok');
    } catch (e) {
      const input = document.createElement('textarea');
      input.value = text; document.body.appendChild(input); input.select();
      document.execCommand('copy'); input.remove();
      PF.toast('Copied to clipboard', 'ok');
    }
  };

  PF.downloadReceipt = function (transactionId) {
    const link = document.createElement('a');
    link.href = '/api/payments/receipt/' + encodeURIComponent(transactionId) + '/download';
    link.download = 'payflow-receipt-' + transactionId + '.html';
    document.body.appendChild(link); link.click(); link.remove();
  };

  PF.showError = function (err) {
    PF.toast(err && err.message ? err.message : String(err), 'err');
  };

  PF.table = function (headers, rows, emptyText) {
    if (typeof rows === 'string') rows = [rows]; // tolerate pre-joined markup
    if (!Array.isArray(rows) || !rows.length) {
      return '<div class="empty">' + PF.esc(emptyText || 'No records yet.') + '</div>';
    }
    return '<div class="table-wrap"><table><thead><tr>' +
      headers.map(function (h) { return '<th>' + PF.esc(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + rows.join('') + '</tbody></table></div>';
  };

  PF.sectionHead = function (title, subtitle, actionHtml) {
    return '<div class="section-head"><div><h2>' + PF.esc(title) + '</h2><p>' + PF.esc(subtitle || '') + '</p></div>' +
      (actionHtml || '') + '</div>';
  };

  // Single source of truth for signing out. Even if the API call fails we still
  // clear local state and leave the app, so a stale session can never linger.
  PF.logout = async function () {
    try { await PF.api('/auth/logout', { method: 'POST' }); }
    catch (e) { /* network error must not trap the user inside the app */ }
    try { sessionStorage.clear(); } catch (e) { /* storage may be disabled */ }
    PF.state.user = null;
    PF.state.permissions = [];
    PF.state.loggedOut = true;
    PF.closeModal();
    window.location.replace('/login.html?logged_out=1');
  };

  PF.animateNumber = function (node, target, prefix, suffix) {
    if (!node) return;
    const start = performance.now();
    const duration = 700;
    function step(now) {
      const p = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const value = Math.round(target * eased);
      node.textContent = (prefix || '') + value.toLocaleString('en-IN') + (suffix || '');
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  };
})();
