"""Pydantic v2 request/response contracts for every PAYFLOW endpoint."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
class AccountCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)
    account_type: Literal["Asset", "Liability", "Income", "Expense"]
    role: Literal["Wallet", "Cash", "Bank", "Settlement", "Fees", "Utility", "Generic"]
    user_id: Optional[str] = None
    allow_negative: bool = False
    opening_balance_paise: int = 0


class AccountOut(ORMModel):
    id: str
    code: str
    name: str
    account_type: str
    role: str
    user_id: Optional[str] = None
    allow_negative: bool
    opening_balance_paise: int
    active: bool
    created_at: str
    balance_paise: Optional[int] = None


class EntryLine(BaseModel):
    account_id: str
    debit_paise: int = Field(ge=0)
    credit_paise: int = Field(ge=0)


class JournalEntryIn(BaseModel):
    description: str = Field(min_length=2)
    lines: List[EntryLine] = Field(min_length=2)
    category: str = "Manual Journal"
    reference: Optional[str] = None
    transaction_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EntryOut(ORMModel):
    id: str
    date: str
    timestamp: str
    transaction_id: str
    reference: Optional[str] = None
    description: str
    category: str
    total_paise: int
    lines: List[Dict[str, Any]]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_reversal: bool = False
    reversed_entry_id: Optional[str] = None


class TrialAccountLine(ORMModel):
    account_id: str
    code: str
    name: str
    account_type: str
    total_debits: int
    total_credits: int
    balance_paise: int


class TrialBalanceResponse(ORMModel):
    total_debits_paise: int
    total_credits_paise: int
    difference_paise: int
    balanced: bool
    account_count: int
    entries_count: int
    accounts: List[TrialAccountLine]


class RefundIn(BaseModel):
    refund_amount_paise: Optional[int] = Field(default=None, ge=1)
    reason: str = "Merchant Refund"


class ReverseIn(BaseModel):
    reason: str = "Operational Reversal"


# ---------------------------------------------------------------------------
# Identity & auth
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_]+$")
    email: str = Field(min_length=5, max_length=120)
    phone: str = Field(min_length=8, max_length=16)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["Customer", "Merchant"] = "Customer"

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("invalid email")
        return v.lower()


class LoginIn(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None
    recovery_code: Optional[str] = None


class MFASetupOut(ORMModel):
    secret: str
    provisioning_uri: str
    otpauth_url: str
    recovery_codes: List[str]


class MFAVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class SessionOut(ORMModel):
    authenticated: bool
    user: Dict[str, Any]
    permissions: List[str]
    session: Dict[str, Any]


class UserOut(ORMModel):
    id: str
    username: str
    email: str
    phone: str
    full_name: str
    role: str
    vpa: str
    is_active: bool
    mfa_enabled: bool
    failed_login_attempts: int
    locked_until: Optional[str]
    created_at: str
    updated_at: str
    balance_paise: Optional[int] = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class RoleChangeIn(BaseModel):
    role: Literal["Customer", "Merchant", "Operator", "Auditor", "Administrator"]


# ---------------------------------------------------------------------------
# Wallets
# ---------------------------------------------------------------------------
class WalletOut(ORMModel):
    id: str
    user_id: str
    account_id: str
    label: str
    currency: str
    is_primary: bool
    status: str
    created_at: str
    balance_paise: int


class WalletCreateIn(BaseModel):
    label: str = Field(min_length=2, max_length=60)
    code: Optional[str] = None


class TopUpIn(BaseModel):
    wallet_id: Optional[str] = None
    amount_paise: int = Field(gt=0)
    reference: Optional[str] = None


class OwnTransferIn(BaseModel):
    from_wallet_id: str
    to_wallet_id: str
    amount_paise: int = Field(gt=0)
    fee_paise: int = Field(default=0, ge=0)
    description: str = "Wallet to wallet transfer"


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
class SendMoneyIn(BaseModel):
    recipient: str = Field(min_length=2)
    amount_paise: int = Field(gt=0)
    note: str = "Payment"
    from_wallet_id: Optional[str] = None
    fee_paise: int = Field(default=0, ge=0)
    totp_code: Optional[str] = None


class ScanPayIn(BaseModel):
    payload: str = Field(min_length=10)
    from_wallet_id: Optional[str] = None
    totp_code: Optional[str] = None


class QRRequest(BaseModel):
    amount_paise: Optional[int] = Field(default=None, ge=1)
    note: Optional[str] = None


class ReceiptOut(ORMModel):
    transaction_id: str
    reference: str
    date: str
    timestamp: str
    description: str
    category: str
    amount_paise: int
    fee_paise: int
    total_paise: int
    direction: str
    counterparty: str
    status: str
    lines: List[Dict[str, Any]]
    metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# Payment requests
# ---------------------------------------------------------------------------
class RequestCreateIn(BaseModel):
    payer: str = Field(min_length=2)
    amount_paise: int = Field(gt=0)
    note: str = "Payment request"
    from_wallet_id: Optional[str] = None


class PaymentRequestOut(ORMModel):
    id: str
    creator_user_id: str
    creator_vpa: str
    payer_user_id: str
    payer_vpa: str
    amount_paise: int
    note: str
    status: str
    direction: str
    created_at: str
    updated_at: str
    expires_at: str
    transaction_id: Optional[str] = None


class RequestApproveIn(BaseModel):
    totp_code: Optional[str] = None
    from_wallet_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Beneficiaries
# ---------------------------------------------------------------------------
class BeneficiaryIn(BaseModel):
    identifier: str = Field(min_length=2)
    nickname: str = Field(min_length=1, max_length=60)
    category: str = "P2P"
    favorite: bool = False


class BeneficiaryUpdateIn(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=60)
    category: Optional[str] = None
    favorite: Optional[bool] = None


class BeneficiaryOut(ORMModel):
    id: str
    user_id: str
    beneficiary_user_id: str
    vpa: str
    nickname: str
    category: str
    favorite: bool
    created_at: str


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------
class BillFetchIn(BaseModel):
    category: str
    provider: str
    consumer_id: str = Field(min_length=3)


class BillPayIn(BaseModel):
    bill_id: str
    from_wallet_id: Optional[str] = None
    totp_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class DashboardOut(ORMModel):
    total_balance_paise: int
    inflow_paise: int
    outflow_paise: int
    transaction_count: int
    wallet_count: int
    monthly_spend_paise: int
    recent_transactions: List[Dict[str, Any]]


class ChartOut(ORMModel):
    format: str
    image: str
    title: str
    summary: Dict[str, Any] = Field(default_factory=dict)


class ReconciliationRow(ORMModel):
    account_id: str
    code: str
    name: str
    account_type: str
    opening_balance_paise: int
    debits_paise: int
    credits_paise: int
    expected_balance_paise: int
    cached_balance_paise: int
    difference_paise: int
    status: str


class ReconciliationOut(ORMModel):
    generated_at: str
    rows: List[ReconciliationRow]
    all_balanced: bool
    discrepancies: int
