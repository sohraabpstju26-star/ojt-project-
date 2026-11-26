# PAYFLOW — Unified Digital Payments & Immutable Financial Ledger

A self-contained, simulated FinTech platform: UPI-style VPAs, dynamic QR, Scan & Pay,
collect requests, utility billers, wallet management, administrative controls, and an
**append-only, integer-paise, double-entry ledger** with Pandas/Matplotlib analytics.

> **Simulation boundary:** PAYFLOW never connects to NPCI, banks, or card rails. It never
> asks for real UPI PINs, banking passwords, or card CVVs. All money is simulated.

---

## 1. Quick start

```bash
# From the project root (Python 3.10+; verified on Python 3.14)
cd "/Users/sohraabsheikh/Documents/Default Project"

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Run the full automated suite (27 tests)
python3 -m pytest backend/tests -q

# Launch the platform
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open:

| URL | Purpose |
|-----|---------|
| `http://127.0.0.1:8000/` | Public landing page |
| `http://127.0.0.1:8000/index.html` | Application UI |
| `http://127.0.0.1:8000/login.html` | Sign in |
| `http://127.0.0.1:8000/docs` | Interactive Swagger UI |
| `http://127.0.0.1:8000/api/health` | Health probe / ledger balance |

Optional environment variables:

```bash
export PAYFLOW_DATA_DIR=/absolute/path/to/isolated/data   # test isolation
export PAYFLOW_SECURE_COOKIES=1                          # secure cookies behind HTTPS
```

### Default demo credentials

| Role | Username | Password |
|------|----------|----------|
| Customer | `aditi_sharma` | `Customer@123` |
| Customer | `rohit_kumar` | `Customer@123` |
| Merchant | `starbucks` | `Merchant@123` |
| Merchant | `blue_tokai` | `Merchant@123` |
| Operator | `operator` | `Oper@12345` |
| Auditor | `auditor` | `Audit@12345` |
| Administrator | `admin` | `Admin@12345` |
| Customer | `priya_verma` | `Customer@123` |
| Customer | `vikram_singh` | `Customer@123` |
| Customer | `meera_iyer` | `Customer@123` |
| Customer | `arjun_mehta` | `Customer@123` |
| Merchant | `croma` | `Merchant@123` |
| Merchant | `dominos` | `Merchant@123` |
| Merchant | `uber_rides` | `Merchant@123` |
| Merchant | `nature_basket` | `Merchant@123` |
| Operator | `operator2` | `Oper@12345` |
| Auditor | `auditor2` | `Audit@12345` |

Demo data is seeded idempotently on first boot (system accounts, funded wallets, and six
months of backdated journal activity). New users can self-register as Customer or Merchant.

---

## 2. Architecture

```
PAYFLOW/
├── requirements.txt
├── data/                          # JSON stores (created on first boot)
│   ├── .secrets/app_secret.key    # AES-256-GCM key, mode 0600
│   ├── .locks/*.lock              # fcntl advisory lock files
│   ├── users.json  accounts.json  entries.json  balances.json
│   ├── wallets.json  beneficiaries.json  payment_requests.json
│   ├── merchants.json  sessions.json  notifications.json
│   ├── settings.json  audit_logs.json  security_events.json
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, routers, static UI, error mapping
│   │   ├── config.py              # dynamic paths + policy constants
│   │   ├── core/
│   │   │   ├── file_lock.py       # fcntl.flock + process/thread reentrant lock
│   │   │   ├── json_store.py      # .tmp → fsync → os.replace → dir fsync
│   │   │   ├── security.py        # Argon2id, TOTP, AES-GCM, session digests
│   │   │   └── bootstrap.py       # system accounts + demo identity seeding
│   │   ├── models/schemas.py      # all Pydantic v2 contracts
│   │   ├── services/
│   │   │   ├── ledger_service.py      # Ledger class (core engine)
│   │   │   ├── auth_service.py        # identity, MFA, sessions, lockout
│   │   │   ├── wallet_service.py      # wallets, top-up, internal transfers
│   │   │   ├── payment_service.py     # VPA resolution, QR, Scan & Pay, receipts
│   │   │   ├── request_service.py     # collect request state machine
│   │   │   ├── bill_service.py        # 8 simulated biller categories
│   │   │   ├── beneficiary_service.py
│   │   │   ├── audit_service.py       # audit, security events, notifications
│   │   │   └── analytics_service.py   # Pandas + Matplotlib (Agg → base64 SVG)
│   │   └── api/
│   │       ├── deps.py            # session + RBAC dependencies
│   │       └── routers/           # 10 routers, 59 documented paths
│   └── tests/                     # 27 Pytest tests across 5 suites
└── frontend/
    ├── index.html  login.html  register.html
    ├── css/{variables,styles}.css
    └── js/{api,core,manage,admin}.js
```

### Key invariants enforced

1. **Integer paise only.** No `float` is used in any balance, posting, limit, or receipt
   computation. Display formatting divides by 100 only at the presentation layer.
2. **Immutable append-only journal.** `entries.json` is never rewritten with modified
   entries; there is no update/delete route. Corrections are new balanced reversal/refund
   entries linked by `reversed_entry_id` / `metadata.original_transaction_id`.
3. **Balanced postings.** `validate_entry()` rejects entries with fewer than 2 lines,
   zero lines, mixed debit+credit on one line, or `Σdebits ≠ Σcredits` *before* any write.
4. **Zero-sum trial balance.** `Σ all debits − Σ all credits ≡ 0`, verifiable at
   `/api/ledger/trial-balance` and on the Analytics → Reconciliation report.
5. **No silent overdrafts.** Projected asset balances are checked inside the locked
   validation; concurrent spends are serialised by `fcntl.flock` + an in-process RLock.
6. **Crash-safe writes.** Every mutation writes a temporary file, `fsync`s it, atomically
   `os.replace`s it, and `fsync`s the parent directory.

### Accounting polarity

| Account type | Balance formula |
|--------------|-----------------|
| Asset / Expense | `opening + Σdebits − Σcredits` |
| Liability / Income | `opening + Σcredits − Σdebits` |

For a wallet (Asset), receiving money **debits** the wallet and paying **credits** it.
Platform fees are collected into an Asset "Fees clearing" account so `(receiver debit +
fee debit) = sender credit`, preserving global balance.

---

### UI design
The frontend uses a premium matte-black (`#080808`) and vibrant-orange (`#FF7900`) design
system with larger typography and spacious layouts. The public landing page is at `/`,
the application shell at `/index.html` (or `/app`), and the sign-in page at `/login.html`.

---

## 3. Security

- Passwords: Argon2id, `m=65536 KiB, t=3, p=1`, 16-byte salt, unique per hash.
- MFA: RFC 6238 TOTP, 32-char base32 secret encrypted at rest with AES-256-GCM; key in
  `data/.secrets/app_secret.key` (mode 0600, outside the web root). Eight SHA-256-hashed
  single-use recovery codes issued per enrolment.
- Sessions: 256-bit random token, only its SHA-256 digest persisted; `HttpOnly`,
  `SameSite=Strict`, `Secure` when `PAYFLOW_SECURE_COOKIES=1`; sliding 24 h / absolute 7 d;
  rotated on login and on MFA completion.
- RBAC enforced on the server by FastAPI dependencies (UI hiding is cosmetic only):

| Group | Customer | Merchant | Operator | Auditor | Admin |
|---|:---:|:---:|:---:|:---:|:---:|
| Own profile / settings | ✅ | ✅ | ✅ | ✅ | ✅ |
| P2P send / receive | ✅ | ✅ | ❌ | ❌ | ❌* |
| Scan & Pay / QR | ✅ | ❌ | ❌ | ❌ | ❌* |
| Beneficiaries / top-up / collect | ✅ | ✅ | ❌ | ❌ | ❌* |
| Merchant dashboard | ❌ | ✅ | ❌ | ❌ | ✅* |
| Manual journals / reversals / refunds | ❌ | ❌ | ✅ | ❌ | ✅ |
| Ledger + trial balance (read) | ❌ | ❌ | ✅ | ✅ | ✅ |
| Audit logs / security events | ❌ | ❌ | ❌ | ✅ | ✅ |
| Role management / locks / monitoring | ❌ | ❌ | ❌ | ❌ | ✅ |

\* Administrators inherit all endpoint permissions by design.

- Step-up: transfers above ₹10,000 require a valid TOTP when MFA is enabled (403 otherwise).

---

## 4. REST API (all mounted under `/api`, documented at `/docs`)

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`, `POST /auth/mfa/setup`, `POST /auth/mfa/verify`, `POST /auth/mfa/disable`, `POST /auth/change-password` |
| Wallets | `GET/POST /wallets`, `POST /wallets/top-up`, `POST /wallets/transfer` |
| Payments | `POST /payments/send`, `POST /payments/scan-pay`, `GET /payments/qr`, `GET /payments/qr/image`, `GET /payments/merchants`, `GET /payments/receipt/{id}`, `GET /payments/receipt/{id}/download` |
| Requests | `GET/POST /requests`, `POST /requests/{id}/approve`, `/reject`, `/cancel` |
| Beneficiaries | `GET/POST /beneficiaries`, `PUT/DELETE /beneficiaries/{id}`, `POST /beneficiaries/{id}/favorite`, `GET /beneficiaries/{id}/history` |
| Bills | `GET /bills/categories`, `POST /bills/fetch`, `POST /bills/pay` |
| Ledger | `GET/POST /ledger/accounts`, `GET /ledger/accounts/{id}`, `POST /ledger/accounts/{id}/toggle`, `GET/POST /ledger/entries`, `GET /ledger/trial-balance`, `POST /ledger/reverse/{txn}`, `POST /ledger/refund/{txn}`, `POST /ledger/recalculate-balances` |
| Analytics | `GET /analytics/dashboard`, `/chart/cashflow`, `/chart/categories`, `/chart/velocity`, `/chart/status`, `/reconciliation` |
| Admin | `GET /admin/users`, `PUT /admin/users/{id}/role`, `POST /admin/users/{id}/unlock`, `GET /admin/audit-logs`, `GET /admin/security-events`, `GET /admin/system-health` |
| Self service | `GET /transactions`, `GET /notifications`, `POST /notifications/{id}/read`, `GET/PUT /settings`, `GET /cards`, `POST /cards/{id}/freeze`, `GET /security/sessions`, `DELETE /security/sessions/{hash}` |

---

## 5. Test suite

```bash
python3 -m pytest backend/tests -v
```

| File | Coverage |
|------|----------|
| `test_ledger_invariants.py` | 2/3/multi-line postings, unbalanced rejection (HTTP 400), 100 random balanced transfers with zero-sum trial balance, overdraft rejection, immutability, four account types + unique codes |
| `test_auth_and_security.py` | Argon2id parameters/verification, TOTP, AES-GCM envelope, 5-attempt lockout, session rotation/revocation, MFA secret never plaintext at rest, step-up login |
| `test_permissions_rbac.py` | Customer blocked from admin/auditor routes, Auditor read-only, Operator reversals allowed but role changes denied, Admin full access |
| `test_payments_and_wallets.py` | P2P movement, insufficient funds, duplicate reference prevention, request approve/reject, full + partial refunds, reversal + double-reversal prevention, wallet transfer with fee |
| `test_concurrency_and_locks.py` | 8 simultaneous spends against one wallet (exactly 5 succeed), 120 atomic concurrent JSON appends |

**Result:** 27 passed.

---

## 6. Phase 1 note (repository audit)

The target workspace was empty at the start of implementation — there were no pre-existing
files, legacy journals, or accounts to migrate. No `_legacy_backup/` was necessary, and
backward compatibility is provided for the PAYFLOW schemas defined in this specification.
