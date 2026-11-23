/* PAYFLOW control views: security, settings and role-gated administration. */
(function () {
  const PF = window.PF;

  // -------------------------------------------------------------------------
  // Security centre
  // -------------------------------------------------------------------------
  PF.views.security = async function (view) {
    const sessions = await PF.api('/security/sessions');
    const sessionRows = sessions.map(function (s) {
      return '<tr><td class="mono">' + PF.esc(s.token_hash.slice(0, 18)) + '…</td>' +
        '<td>' + PF.esc(s.mfa_verified ? 'MFA verified' : 'Password only') + '</td>' +
        '<td class="muted text-xs">' + PF.esc(PF.fmtDate(s.created_at)) + '</td>' +
        '<td class="muted text-xs">' + PF.esc(PF.fmtDate(s.last_seen_at)) + '</td>' +
        '<td><button class="btn btn-sm btn-danger" data-revoke="' + PF.esc(s.token_hash) + '">Revoke</button></td></tr>';
    }).join('');

    view.innerHTML = PF.sectionHead('Security Centre', 'Argon2id passwords · TOTP MFA · server-side sessions') +
      '<div class="grid grid-2 mb-2">' +
        '<div class="card"><div class="card-title">Change Password</div>' +
          '<form id="pw-form" class="form-grid mt-2">' +
            '<div class="field"><label>Current password</label><input type="password" id="pw-old" required></div>' +
            '<div class="field"><label>New password (min 8 chars)</label><input type="password" id="pw-new" minlength="8" required></div>' +
            '<button class="btn btn-primary" type="submit">Update Password</button>' +
          '</form></div>' +
        '<div class="card"><div class="card-title">Multi-Factor Authentication</div>' +
          '<div class="mt-2">' + PF.badge(state.user.mfa_enabled ? 'MFA ENABLED' : 'MFA DISABLED', state.user.mfa_enabled ? 'green' : 'amber') + '</div>' +
          '<div class="card-sub mt-2">TOTP (RFC 6238) secrets are encrypted at rest with AES-256-GCM. Eight single-use recovery codes are issued on setup.</div>' +
          '<div class="flex gap-1 mt-2">' +
            '<button class="btn btn-sm btn-primary" id="mfa-setup">Set up / Rotate MFA</button>' +
            '<button class="btn btn-sm btn-danger" id="mfa-disable">Disable MFA</button>' +
          '</div></div>' +
      '</div>' +
      '<div class="card"><div class="card-head"><div><div class="card-title">Active Sessions</div>' +
        '<div class="card-sub">Only SHA-256 token digests are stored on the server</div></div></div>' +
        PF.table(['Token digest', 'Context', 'Created', 'Last seen', 'Action'], sessionRows, 'No active sessions.') +
      '</div>';

    view.querySelector('#pw-form').onsubmit = async function (e) {
      e.preventDefault();
      try {
        await PF.api('/auth/change-password', { method: 'POST', body: {
          current_password: view.querySelector('#pw-old').value,
          new_password: view.querySelector('#pw-new').value,
        }});
        PF.toast('Password updated', 'ok'); view.querySelector('#pw-form').reset();
      } catch (err) { PF.showError(err); }
    };

    view.querySelector('#mfa-setup').onclick = async function () {
      try {
        const data = await PF.api('/auth/mfa/setup', { method: 'POST' });
        const modal = PF.modal(
          '<div class="modal-head"><div><h3>Set up Authenticator</h3>' +
            '<div class="card-sub">Scan the URI in your authenticator app, then verify a code</div></div></div>' +
          '<div class="field"><label>Secret (base32)</label><input id="mfa-secret" readonly value="' + PF.esc(data.secret) + '"></div>' +
          '<div class="field mt-2"><label>Provisioning URI</label><input id="mfa-uri" readonly value="' + PF.esc(data.provisioning_uri) + '"></div>' +
          '<button class="btn btn-sm mt-1" id="mfa-copy">Copy secret</button>' +
          '<div class="card mt-2" style="box-shadow:none"><div class="card-title">Recovery codes (save these now)</div>' +
            '<div class="mono mt-1 secondary">' + data.recovery_codes.map(PF.esc).join('<br>') + '</div></div>' +
          '<div class="field mt-2"><label>Verification code from app</label><input id="mfa-code" placeholder="000000" inputmode="numeric"></div>' +
          '<div class="modal-foot"><button class="btn" id="mfa-cancel">Cancel</button>' +
            '<button class="btn btn-primary" id="mfa-verify">Verify & Enable</button></div>'
        );
        modal.querySelector('#mfa-copy').onclick = function () { PF.copy(data.secret); };
        modal.querySelector('#mfa-cancel').onclick = PF.closeModal;
        modal.querySelector('#mfa-verify').onclick = async function () {
          try {
            await PF.api('/auth/mfa/verify', { method: 'POST', body: { code: modal.querySelector('#mfa-code').value.trim() } });
            PF.closeModal(); PF.toast('MFA enabled', 'ok'); PF.route();
          } catch (err) { PF.showError(err); }
        };
      } catch (err) { PF.showError(err); }
    };
    view.querySelector('#mfa-disable').onclick = function () {
      const modal = PF.modal(
        '<div class="modal-head"><h3>Disable MFA</h3></div>' +
        '<div class="field"><label>Current TOTP code</label><input id="mfa-off-code" placeholder="000000"></div>' +
        '<div class="modal-foot"><button class="btn" id="off-cancel">Cancel</button>' +
          '<button class="btn btn-danger" id="off-go">Disable</button></div>'
      );
      modal.querySelector('#off-cancel').onclick = PF.closeModal;
      modal.querySelector('#off-go').onclick = async function () {
        try {
          await PF.api('/auth/mfa/disable', { method: 'POST', body: { code: modal.querySelector('#mfa-off-code').value.trim() } });
          PF.closeModal(); PF.toast('MFA disabled', 'ok'); PF.route();
        } catch (err) { PF.showError(err); }
      };
    };
    view.querySelectorAll('[data-revoke]').forEach(function (b) {
      b.onclick = function () {
        PF.confirm('Revoke session', 'That device will be signed out immediately.', async function () {
          try {
            await PF.api('/security/sessions/' + encodeURIComponent(b.dataset.revoke), { method: 'DELETE' });
            PF.toast('Session revoked', 'ok'); PF.route();
          } catch (err) { PF.showError(err); }
        }, true);
      };
    });
  };

  // -------------------------------------------------------------------------
  // Settings
  // -------------------------------------------------------------------------
  PF.views.settings = async function (view) {
    const s = await PF.api('/settings');
    document.body.classList.toggle('theme-light', s.theme === 'light');
    view.innerHTML = PF.sectionHead('Settings', 'Profile and preferences stored per user') +
      '<div class="grid grid-2">' +
        '<div class="card"><div class="card-title">Profile</div>' +
          '<div class="mt-2 text-sm secondary" style="line-height:2">' +
            '<div class="between"><span>Full name</span><b>' + PF.esc(state.user.full_name) + '</b></div>' +
            '<div class="between"><span>Username</span><b>' + PF.esc(state.user.username) + '</b></div>' +
            '<div class="between"><span>Email</span><b>' + PF.esc(state.user.email) + '</b></div>' +
            '<div class="between"><span>Phone</span><b>' + PF.esc(state.user.phone) + '</b></div>' +
            '<div class="between"><span>VPA</span><b class="success mono">' + PF.esc(state.user.vpa) + '</b></div>' +
            '<div class="between"><span>Role</span><b>' + PF.esc(state.user.role) + '</b></div>' +
          '</div></div>' +
        '<div class="card"><div class="card-title">Preferences</div>' +
          '<form id="settings-form" class="form-grid mt-2">' +
            '<div class="field"><label>Theme</label><select id="s-theme">' +
              '<option value="dark"' + (s.theme === 'dark' ? ' selected' : '') + '>Obsidian Dark</option>' +
              '<option value="light"' + (s.theme === 'light' ? ' selected' : '') + '>Light</option></select></div>' +
            '<div class="field"><label>Currency format</label><select id="s-currency">' +
              ['INR'].map(function (c) { return '<option' + (s.currency_format === c ? ' selected' : '') + '>' + c + '</option>'; }).join('') +
              '</select></div>' +
            '<div class="field"><label>Daily transaction limit (INR)</label><div class="input-prefix"><span>₹</span>' +
              '<input id="s-limit" type="number" min="1000" step="1000" value="' + (s.daily_limit_paise / 100) + '"></div></div>' +
            '<div class="field"><label class="checkline"><input type="checkbox" id="s-payments"' +
              (s.notifications.payments ? ' checked' : '') + '> Payment notifications</label></div>' +
            '<div class="field"><label class="checkline"><input type="checkbox" id="s-security"' +
              (s.notifications.security ? ' checked' : '') + '> Security alerts</label></div>' +
            '<div class="field"><label class="checkline"><input type="checkbox" id="s-balance"' +
              (s.privacy.show_balance ? ' checked' : '') + '> Show balances on dashboard</label></div>' +
            '<button class="btn btn-primary" type="submit">Save Preferences</button>' +
          '</form></div>' +
      '</div>';
    view.querySelector('#settings-form').onsubmit = async function (e) {
      e.preventDefault();
      const theme = view.querySelector('#s-theme').value;
      try {
        await PF.api('/settings', { method: 'PUT', body: {
          theme: theme,
          currency_format: view.querySelector('#s-currency').value,
          daily_limit_paise: Math.round(parseFloat(view.querySelector('#s-limit').value) * 100),
          notifications: {
            payments: view.querySelector('#s-payments').checked,
            security: view.querySelector('#s-security').checked,
            product: false,
          },
          privacy: { show_balance: view.querySelector('#s-balance').checked, activity_visibility: 'contacts' },
        }});
        document.body.classList.toggle('theme-light', theme === 'light');
        PF.toast('Preferences saved', 'ok');
      } catch (err) { PF.showError(err); }
    };
  };

  // -------------------------------------------------------------------------
  // Account management
  // -------------------------------------------------------------------------
  PF.views.accounts = async function (view) {
    const accounts = await PF.api('/ledger/accounts');
    const canWrite = ['Operator', 'Administrator'].includes(state.user.role);
    const rows = accounts.map(function (a) {
      return '<tr><td class="mono">' + PF.esc(a.code) + '</td><td>' + PF.esc(a.name) + '</td>' +
        '<td>' + PF.badge(a.account_type, a.account_type === 'Asset' ? 'blue' :
          a.account_type === 'Liability' ? 'purple' : a.account_type === 'Income' ? 'green' : 'amber') + '</td>' +
        '<td>' + PF.esc(a.role) + '</td>' +
        '<td class="align-right">' + PF.inr(a.balance_paise) + '</td>' +
        '<td>' + PF.badge(a.active ? 'ACTIVE' : 'FROZEN', a.active ? 'green' : 'red') + '</td>' +
        '<td>' + (canWrite ? '<button class="btn btn-sm" data-toggle="' + a.id + '" data-active="' + a.active + '">' +
          (a.active ? 'Freeze' : 'Activate') + '</button>' : '—') + '</td></tr>';
    }).join('');
    view.innerHTML = PF.sectionHead('Account Management', 'Chart of accounts · ' + accounts.length + ' accounts',
      canWrite ? '<button class="btn btn-primary" id="new-account">+ New Account</button>' : '') +
      '<div class="card">' + PF.table(['Code', 'Name', 'Type', 'Role', 'Balance', 'Status', 'Action'], rows, 'No accounts.') + '</div>';
    view.querySelectorAll('[data-toggle]').forEach(function (b) {
      b.onclick = async function () {
        try {
          await PF.api('/ledger/accounts/' + b.dataset.toggle + '/toggle?active=' + (b.dataset.active !== 'true'),
            { method: 'POST' });
          PF.toast('Account status updated', 'ok'); PF.route();
        } catch (err) { PF.showError(err); }
      };
    });
    if (canWrite) {
      view.querySelector('#new-account').onclick = function () {
        const modal = PF.modal(
          '<div class="modal-head"><h3>Create Ledger Account</h3></div>' +
          '<div class="form-grid">' +
            '<div class="field"><label>Code</label><input id="a-code" placeholder="WLT-NEW-001"></div>' +
            '<div class="field"><label>Name</label><input id="a-name" placeholder="Travel Wallet"></div>' +
            '<div class="form-row"><div class="field"><label>Account type</label><select id="a-type">' +
              ['Asset', 'Liability', 'Income', 'Expense'].map(function (t) { return '<option>' + t + '</option>'; }).join('') +
              '</select></div><div class="field"><label>Role</label><select id="a-role">' +
              ['Wallet', 'Cash', 'Bank', 'Settlement', 'Fees', 'Utility', 'Generic'].map(function (t) { return '<option>' + t + '</option>'; }).join('') +
              '</select></div></div>' +
            '<div class="field"><label>Opening balance (paise, integer)</label><input id="a-open" type="number" value="0" step="1"></div>' +
          '</div><div class="modal-foot"><button class="btn" id="a-cancel">Cancel</button>' +
            '<button class="btn btn-primary" id="a-go">Create Account</button></div>'
        );
        modal.querySelector('#a-cancel').onclick = PF.closeModal;
        modal.querySelector('#a-go').onclick = async function () {
          try {
            await PF.api('/ledger/accounts', { method: 'POST', body: {
              code: modal.querySelector('#a-code').value.trim(),
              name: modal.querySelector('#a-name').value.trim(),
              account_type: modal.querySelector('#a-type').value,
              role: modal.querySelector('#a-role').value,
              opening_balance_paise: parseInt(modal.querySelector('#a-open').value, 10) || 0,
            }});
            PF.closeModal(); PF.toast('Account created', 'ok'); PF.route();
          } catch (err) { PF.showError(err); }
        };
      };
    }
  };

  // -------------------------------------------------------------------------
  // Ledger management
  // -------------------------------------------------------------------------
  PF.views.ledger = async function (view) {
    const [tb, accounts] = await Promise.all([PF.api('/ledger/trial-balance'), PF.api('/ledger/accounts')]);
    const canWrite = ['Operator', 'Administrator'].includes(state.user.role);
    const rows = accounts.map(function (a) {
      return '<tr><td class="mono">' + PF.esc(a.code) + '</td><td>' + PF.esc(a.name) + '</td>' +
        '<td>' + a.account_type + '</td><td class="align-right">' + PF.inr(a.total_debits) + '</td>' +
        '<td class="align-right">' + PF.inr(a.total_credits) + '</td>' +
        '<td class="align-right">' + PF.inr(a.balance_paise) + '</td></tr>';
    }).join('');

    view.innerHTML = PF.sectionHead('Ledger Management', 'Immutable journal · append-only · integer paise',
      canWrite ? '<button class="btn btn-primary" id="new-entry">+ Post Journal Entry</button>' : '') +
      '<div class="grid grid-4 mb-2">' +
        '<div class="kpi"><div class="kpi-label">Total Debits</div><div class="kpi-value blue">' + PF.inr(tb.total_debits_paise) + '</div></div>' +
        '<div class="kpi"><div class="kpi-label">Total Credits</div><div class="kpi-value">' + PF.inr(tb.total_credits_paise) + '</div></div>' +
        '<div class="kpi"><div class="kpi-label">Difference</div><div class="kpi-value ' + (tb.balanced ? 'green' : 'red') + '">' + PF.inr(tb.difference_paise) + '</div></div>' +
        '<div class="kpi"><div class="kpi-label">Entries / Accounts</div><div class="kpi-value">' + tb.entries_count + ' / ' + tb.account_count + '</div></div>' +
      '</div>' +
      '<div class="card mb-2"><div class="card-head"><div class="card-title">Trial Balance by Account</div>' +
        PF.badge(tb.balanced ? 'ZERO-SUM VERIFIED' : 'IMBALANCED', tb.balanced ? 'green' : 'red') + '</div>' +
        PF.table(['Code', 'Account', 'Type', 'Debits', 'Credits', 'Balance'], rows, 'No accounts.') + '</div>' +
      '<div class="card"><div class="card-head"><div class="card-title">Journal Entries</div>' +
        '<div class="flex gap-1"><input id="entry-category" placeholder="Filter category" style="width:180px">' +
        '<button class="btn btn-sm" id="entry-filter-btn">Filter</button></div></div>' +
        '<div id="entries-area"><div class="empty">Loading…</div></div></div>';

    async function loadEntries() {
      const cat = view.querySelector('#entry-category').value.trim();
      const entries = await PF.api('/ledger/entries' + (cat ? '?category=' + encodeURIComponent(cat) : ''));
      view.querySelector('#entries-area').innerHTML = PF.table(
        ['Transaction ID', 'Date', 'Description', 'Category', 'Amount', 'Lines', 'Actions'],
        entries.slice(0, 100).map(function (e) {
          let actions = PF.badge(e.is_reversal ? 'REVERSAL' : 'POSTED', e.is_reversal ? 'amber' : 'green');
          if (canWrite && !e.is_reversal) {
            actions += '<br><button class="btn btn-sm btn-danger mt-1" data-rev="' + PF.esc(e.transaction_id) + '">Reverse</button> ' +
              '<button class="btn btn-sm mt-1" data-ref="' + PF.esc(e.transaction_id) + '">Refund</button>';
          }
          return '<tr><td class="mono">' + PF.esc(e.transaction_id) + '</td>' +
            '<td class="muted text-xs nowrap">' + PF.esc(e.timestamp) + '</td>' +
            '<td>' + PF.esc(e.description) + '</td><td>' + PF.badge(e.category, 'blue') + '</td>' +
            '<td class="align-right">' + PF.inr(e.total_paise) + '</td><td>' + e.lines.length + '</td>' +
            '<td class="nowrap">' + actions + '</td></tr>';
        }), 'No journal entries.'
      );
      view.querySelectorAll('[data-rev]').forEach(function (b) {
        b.onclick = function () {
          PF.confirm('Reverse entry', 'A balanced, linked reversal entry will be appended. The original stays immutable.', async function () {
            try { await PF.api('/ledger/reverse/' + b.dataset.rev, { method: 'POST', body: { reason: 'Operator reversal' } });
              PF.toast('Reversal posted', 'ok'); PF.route(); } catch (err) { PF.showError(err); }
          }, true);
        };
      });
      view.querySelectorAll('[data-ref]').forEach(function (b) {
        b.onclick = function () {
          const modal = PF.modal(
            '<div class="modal-head"><h3>Issue Refund</h3></div>' +
            '<div class="field"><label>Amount (INR, blank = full remaining)</label><div class="input-prefix"><span>₹</span>' +
              '<input id="ref-amount" type="number" min="1" step="0.01"></div></div>' +
            '<div class="field mt-2"><label>Reason</label><input id="ref-reason" value="Merchant Refund"></div>' +
            '<div class="modal-foot"><button class="btn" id="ref-cancel">Cancel</button>' +
              '<button class="btn btn-primary" id="ref-go">Issue Refund</button></div>'
          );
          modal.querySelector('#ref-cancel').onclick = PF.closeModal;
          modal.querySelector('#ref-go').onclick = async function () {
            const body = { reason: modal.querySelector('#ref-reason').value };
            const val = modal.querySelector('#ref-amount').value;
            if (val) body.refund_amount_paise = Math.round(parseFloat(val) * 100);
            try { await PF.api('/ledger/refund/' + b.dataset.ref, { method: 'POST', body: body });
              PF.closeModal(); PF.toast('Refund posted', 'ok'); PF.route(); } catch (err) { PF.showError(err); }
          };
        };
      });
    }
    view.querySelector('#entry-filter-btn').onclick = loadEntries;
    await loadEntries();

    if (canWrite) {
      view.querySelector('#new-entry').onclick = function () {
        const options = accounts.map(function (a) {
          return '<option value="' + a.id + '">' + PF.esc(a.code) + ' · ' + PF.esc(a.name) + '</option>';
        }).join('');
        const lineHtml = function (idx) {
          return '<div class="form-row line-row" data-line="' + idx + '">' +
            '<div class="field"><label>Account</label><select class="line-acc">' + options + '</select></div>' +
            '<div class="form-row"><div class="field"><label>Debit (paise)</label><input class="line-dr" type="number" min="0" value="0"></div>' +
            '<div class="field"><label>Credit (paise)</label><input class="line-cr" type="number" min="0" value="0"></div></div></div>';
        };
        const modal = PF.modal(
          '<div class="modal-head"><h3>Post Manual Journal Entry</h3></div>' +
          '<div class="field"><label>Description</label><input id="j-desc" placeholder="Adjustment entry"></div>' +
          '<div class="form-row mt-2"><div class="field"><label>Category</label><input id="j-cat" value="Manual Journal"></div>' +
            '<div class="field"><label>Reference (optional)</label><input id="j-ref"></div></div>' +
          '<div id="j-lines" class="mt-2">' + lineHtml(0) + lineHtml(1) + '</div>' +
          '<button class="btn btn-sm mt-1" id="j-add-line">+ Add line</button>' +
          '<div class="card-sub mt-2">Debits must equal credits. Unbalanced entries are rejected before any disk write.</div>' +
          '<div class="modal-foot"><button class="btn" id="j-cancel">Cancel</button>' +
            '<button class="btn btn-primary" id="j-go">Post Entry</button></div>', true
        );
        modal.querySelector('#j-cancel').onclick = PF.closeModal;
        modal.querySelector('#j-add-line').onclick = function () {
          modal.querySelector('#j-lines').insertAdjacentHTML('beforeend',
            lineHtml(modal.querySelectorAll('.line-row').length));
        };
        modal.querySelector('#j-go').onclick = async function () {
          const lines = Array.from(modal.querySelectorAll('.line-row')).map(function (row) {
            return { account_id: row.querySelector('.line-acc').value,
              debit_paise: parseInt(row.querySelector('.line-dr').value, 10) || 0,
              credit_paise: parseInt(row.querySelector('.line-cr').value, 10) || 0 };
          });
          try {
            await PF.api('/ledger/entries', { method: 'POST', body: {
              description: modal.querySelector('#j-desc').value,
              category: modal.querySelector('#j-cat').value,
              reference: modal.querySelector('#j-ref').value || undefined,
              lines: lines,
            }});
            PF.closeModal(); PF.toast('Journal entry posted', 'ok'); PF.route();
          } catch (err) { PF.showError(err); }
        };
      };
    }
  };

  // -------------------------------------------------------------------------
  // User management
  // -------------------------------------------------------------------------
  PF.views.users = async function (view) {
    const users = await PF.api('/admin/users');
    const rows = users.map(function (u) {
      const select = ['Customer', 'Merchant', 'Operator', 'Auditor', 'Administrator'].map(function (r) {
        return '<option' + (u.role === r ? ' selected' : '') + '>' + r + '</option>';
      }).join('');
      return '<tr><td class="mono">' + PF.esc(u.username) + '</td><td>' + PF.esc(u.full_name) + '</td>' +
        '<td>' + PF.esc(u.vpa) + '</td>' +
        '<td><select class="user-role" data-user="' + u.id + '"' + (u.id === state.user.id ? ' disabled' : '') + '>' + select + '</select></td>' +
        '<td class="align-right">' + PF.inr(u.balance_paise) + '</td>' +
        '<td>' + (u.locked_until ? PF.badge('LOCKED', 'red') : PF.badge('ACTIVE', 'green')) + '</td>' +
        '<td><button class="btn btn-sm" data-unlock="' + u.id + '">Unlock</button></td></tr>';
    }).join('');
    view.innerHTML = PF.sectionHead('User Management', 'Role assignment, lockout release and status control') +
      '<div class="card">' + PF.table(['Username', 'Name', 'VPA', 'Role', 'Balance', 'Status', 'Action'], rows, 'No users.') + '</div>';
    view.querySelectorAll('.user-role').forEach(function (sel) {
      sel.onchange = async function () {
        try {
          await PF.api('/admin/users/' + sel.dataset.user + '/role', { method: 'PUT', body: { role: sel.value } });
          PF.toast('Role updated', 'ok');
        } catch (err) { PF.showError(err); }
      };
    });
    view.querySelectorAll('[data-unlock]').forEach(function (b) {
      b.onclick = async function () {
        try { await PF.api('/admin/users/' + b.dataset.unlock + '/unlock', { method: 'POST' });
          PF.toast('Account unlocked', 'ok'); PF.route(); } catch (err) { PF.showError(err); }
      };
    });
  };

  // -------------------------------------------------------------------------
  // Audit logs
  // -------------------------------------------------------------------------
  PF.views.audit = async function (view) {
    const [logs, events] = await Promise.all([PF.api('/admin/audit-logs'), PF.api('/admin/security-events')]);
    const render = function (rows) {
      return PF.table(['Timestamp', 'Actor', 'Action / Event', 'Resource', 'Outcome', 'Details'],
        rows.slice(0, 150).map(function (r) {
          return '<tr><td class="muted text-xs nowrap">' + PF.esc(PF.fmtDate(r.timestamp)) + '</td>' +
            '<td class="mono">' + PF.esc(r.actor_id || r.actor || '—') + '</td>' +
            '<td>' + PF.esc(r.action || r.event_type) + '</td>' +
            '<td class="mono">' + PF.esc(r.resource || '—') + '</td>' +
            '<td>' + PF.badge(r.outcome, r.outcome === 'SUCCESS' ? 'green' : 'amber') + '</td>' +
            '<td class="muted text-xs">' + PF.esc(JSON.stringify(r.detail || {})) + '</td></tr>';
        }), 'No records.');
    };
    view.innerHTML = PF.sectionHead('Audit Logs', 'Immutable chronological operational and security trail') +
      '<div class="card mb-2"><div class="flex gap-1">' +
        '<button class="btn btn-sm" data-log="audit">Operational Audit</button>' +
        '<button class="btn btn-sm" data-log="security">Security Events</button></div></div>' +
      '<div class="card" id="log-table">' + render(logs) + '</div>';
    view.querySelectorAll('[data-log]').forEach(function (b) {
      b.onclick = function () {
        view.querySelector('#log-table').innerHTML = render(b.dataset.log === 'audit' ? logs : events);
      };
    });
  };

  // -------------------------------------------------------------------------
  // System monitoring
  // -------------------------------------------------------------------------
  PF.views.monitoring = async function (view) {
    const h = await PF.api('/admin/system-health');
    const fileRows = h.files.map(function (f) {
      return '<tr><td class="mono">' + PF.esc(f.file) + '</td>' +
        '<td>' + PF.badge(f.exists ? 'PRESENT' : 'MISSING', f.exists ? 'green' : 'red') + '</td>' +
        '<td class="align-right">' + f.size_bytes + ' bytes</td></tr>';
    }).join('');
    view.innerHTML = PF.sectionHead('System Monitoring', 'JSON store health, advisory locks and integrity checks',
      PF.badge(h.status, h.status === 'HEALTHY' ? 'green' : 'red')) +
      '<div class="grid grid-4 mb-2">' +
        '<div class="kpi"><div class="kpi-label">Ledger entries</div><div class="kpi-value blue">' + h.ledger.entries + '</div></div>' +
        '<div class="kpi"><div class="kpi-label">Accounts</div><div class="kpi-value">' + h.ledger.accounts + '</div></div>' +
        '<div class="kpi"><div class="kpi-label">Trial difference</div><div class="kpi-value ' + (h.ledger.balanced ? 'green' : 'red') + '">' + h.ledger.difference_paise + ' paise</div></div>' +
        '<div class="kpi"><div class="kpi-label">Active sessions</div><div class="kpi-value">' + h.active_sessions + '</div></div>' +
      '</div>' +
      '<div class="grid grid-2">' +
        '<div class="card"><div class="card-title">JSON Store Files</div>' +
          PF.table(['File', 'Status', 'Size'], fileRows, 'No files.') + '</div>' +
        '<div class="card"><div class="card-title">Runtime Details</div>' +
          '<div class="text-sm secondary mt-2" style="line-height:2">' +
            '<div class="between"><span>Data directory</span><b class="mono">' + PF.esc(h.data_directory) + '</b></div>' +
            '<div class="between"><span>Lock directory</span><b class="mono">' + PF.esc(h.lock_directory) + '</b></div>' +
            '<div class="between"><span>Total debits</span><b>' + PF.inr(h.ledger.total_debits_paise) + '</b></div>' +
            '<div class="between"><span>Total credits</span><b>' + PF.inr(h.ledger.total_credits_paise) + '</b></div>' +
            '<div class="between"><span>Reconciliation</span><b>' + PF.esc(h.reconciliation.all_balanced ? 'ALL BALANCED' : h.reconciliation.discrepancies + ' DISCREPANCIES') + '</b></div>' +
          '</div></div>' +
      '</div>';
  };

  // -------------------------------------------------------------------------
  // Bootstrap
  // -------------------------------------------------------------------------
  async function init() {
    try {
      const session = await PF.api('/auth/session');
      PF.state.user = session.user;
      PF.state.permissions = session.permissions;
    } catch (e) {
      location.replace('/login.html');
      return;
    }
    PF.buildShell();
    PF.route();
    window.addEventListener('hashchange', PF.route);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
