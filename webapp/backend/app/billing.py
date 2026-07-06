"""Billing: Stripe (USD) + Razorpay (INR) checkout, webhooks, GST invoices.

Payments are feature-flagged off for pilot customers. Webhook signatures are
verified with plain HMAC (both providers document the scheme), so no provider
SDK is needed server-side; checkout-link creation goes through an injectable
provider client. GST arithmetic lives in pure functions — see
docs/gst_notes.md for what a CA must verify before this invoices real money.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from webapp.backend.app.auth import get_current_user
from webapp.backend.app.config import get_settings
from webapp.backend.app.db import AuditJob, Base, User, get_db

router = APIRouter(prefix="/billing", tags=["billing"])

PRODUCT_NAME = "DB Performance Audit"
SAC_CODE = "998313"  # IT consulting & support services


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    job_id: Mapped[str] = mapped_column(ForeignKey("audit_jobs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))  # stripe | razorpay
    amount_minor: Mapped[int] = mapped_column()  # cents / paise
    currency: Mapped[str] = mapped_column(String(3))  # USD | INR
    status: Mapped[str] = mapped_column(String(16), default="created")  # created | paid
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    buyer_name: Mapped[str] = mapped_column(String(200), default="")
    buyer_gstin: Mapped[str] = mapped_column(String(20), default="")
    buyer_state_code: Mapped[str] = mapped_column(String(2), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# --------------------------------------------------------------------------
# GST arithmetic (pure; INR prices are GST-inclusive)
# --------------------------------------------------------------------------


def compute_gst(
    amount_minor: int,
    currency: str,
    buyer_state_code: str,
    seller_state_code: str,
    gst_rate_pct: int = 18,
) -> dict:
    """Split a GST-inclusive INR amount into taxable value + CGST/SGST or IGST.

    USD payments are exports of service (zero-rated under LUT): no GST is
    charged and the full amount is the taxable value.
    """
    amount = Decimal(amount_minor) / 100

    def money(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    if currency != "INR":
        return {
            "supply_type": "export",
            "taxable_value": money(amount),
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": 0.0,
            "total": money(amount),
        }

    rate = Decimal(gst_rate_pct) / 100
    taxable = amount / (1 + rate)
    tax = amount - taxable
    intra_state = bool(buyer_state_code) and buyer_state_code == seller_state_code
    if intra_state:
        half = tax / 2
        return {
            "supply_type": "intra_state",
            "taxable_value": money(taxable),
            "cgst": money(half),
            "sgst": money(half),
            "igst": 0.0,
            "total": money(amount),
        }
    return {
        "supply_type": "inter_state",
        "taxable_value": money(taxable),
        "cgst": 0.0,
        "sgst": 0.0,
        "igst": money(tax),
        "total": money(amount),
    }


def _fiscal_year(now: datetime) -> str:
    """Indian fiscal year label, e.g. '2627' for Apr 2026 – Mar 2027."""
    start = now.year if now.month >= 4 else now.year - 1
    return f"{start % 100:02d}{(start + 1) % 100:02d}"


def next_invoice_number(db: Session, prefix: str, now: datetime) -> str:
    fy = _fiscal_year(now)
    series = f"{prefix}-{fy}-"
    count = db.scalar(
        select(func.count()).select_from(Payment).where(Payment.invoice_number.like(f"{series}%"))
    )
    return f"{series}{(count or 0) + 1:04d}"


INVOICE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Invoice {number}</title>
<style>body{{font-family:Georgia,serif;font-size:11pt;margin:40px}}
table{{border-collapse:collapse;width:100%;margin:12px 0}}
td,th{{border:1px solid #999;padding:6px 10px;text-align:left}}
.right{{text-align:right}}</style></head><body>
<h1>Tax Invoice</h1>
<p><strong>dbdoctor</strong> · GSTIN: {seller_gstin} · State code: {seller_state}<br>
Invoice no: <strong>{number}</strong> · Date: {date}</p>
<p>Billed to: {buyer_name} {buyer_gstin_line}</p>
<table>
<tr><th>Description</th><th>SAC</th><th class="right">Taxable value</th>
<th class="right">CGST</th><th class="right">SGST</th><th class="right">IGST</th>
<th class="right">Total ({currency})</th></tr>
<tr><td>{product}</td><td>{sac}</td><td class="right">{taxable:.2f}</td>
<td class="right">{cgst:.2f}</td><td class="right">{sgst:.2f}</td>
<td class="right">{igst:.2f}</td><td class="right">{total:.2f}</td></tr>
</table>
<p>{supply_note}</p>
<p style="color:#777;font-size:9pt">Payment reference: {provider} {provider_ref}</p>
</body></html>"""

_SUPPLY_NOTES = {
    "intra_state": "Intra-state supply: CGST + SGST @ half rate each.",
    "inter_state": "Inter-state supply: IGST @ full rate.",
    "export": "Export of services without payment of IGST (under LUT). Zero-rated supply.",
}


def render_invoice_html(payment: Payment, gst: dict, settings) -> str:
    return INVOICE_TEMPLATE.format(
        number=payment.invoice_number,
        seller_gstin=settings.seller_gstin or "(unregistered — set DBDOCTOR_SELLER_GSTIN)",
        seller_state=settings.seller_state_code,
        date=payment.created_at.strftime("%d %b %Y"),
        buyer_name=payment.buyer_name or "Retail customer",
        buyer_gstin_line=f"· GSTIN: {payment.buyer_gstin}" if payment.buyer_gstin else "",
        product=PRODUCT_NAME,
        sac=SAC_CODE,
        currency=payment.currency,
        supply_note=_SUPPLY_NOTES[gst["supply_type"]],
        provider=payment.provider,
        provider_ref=payment.provider_ref or "",
        taxable=gst["taxable_value"],
        cgst=gst["cgst"],
        sgst=gst["sgst"],
        igst=gst["igst"],
        total=gst["total"],
    )


# --------------------------------------------------------------------------
# Webhook signature verification (documented HMAC schemes, no SDK needed)
# --------------------------------------------------------------------------


def verify_stripe_signature(payload: bytes, header: str, secret: str) -> bool:
    """Stripe-Signature: t=<ts>,v1=<hmac_sha256(f"{t}.{payload}")>."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        signed = f"{parts['t']}.".encode() + payload
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, parts["v1"])
    except (KeyError, ValueError):
        return False


def verify_razorpay_signature(payload: bytes, header: str, secret: str) -> bool:
    """X-Razorpay-Signature: hmac_sha256(payload) hex."""
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header or "")


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    provider: str = Field(pattern="^(stripe|razorpay)$")
    buyer_name: str = ""
    buyer_gstin: str = ""
    buyer_state_code: str = Field("", max_length=2)


class CheckoutOut(BaseModel):
    payment_id: str
    checkout_url: str
    amount_minor: int
    currency: str


class ProviderClient:
    """Creates hosted checkout links. Replaced by a fake in tests; the real
    implementation calls the provider REST APIs with keys from the env."""

    def create_checkout(self, payment: Payment) -> str:
        raise HTTPException(
            503,
            "payment provider keys are not configured on this deployment",
        )


_provider_client = ProviderClient()


def get_provider_client() -> ProviderClient:
    return _provider_client


@router.post("/checkout/{job_id}", response_model=CheckoutOut)
def create_checkout(
    job_id: str,
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider_client: ProviderClient = Depends(get_provider_client),
):
    settings = get_settings()
    if not settings.enable_payments:
        raise HTTPException(503, "payments are not enabled on this deployment (pilot mode)")
    job = db.get(AuditJob, job_id)
    if job is None or (job.user_id != user.id and not user.is_admin):
        raise HTTPException(404, "job not found")
    if job.paid:
        raise HTTPException(409, "job is already paid")

    if body.provider == "stripe":
        amount, currency = settings.price_usd_cents, "USD"
    else:
        amount, currency = settings.price_inr_paise, "INR"

    payment = Payment(
        job_id=job.id,
        provider=body.provider,
        amount_minor=amount,
        currency=currency,
        buyer_name=body.buyer_name[:200],
        buyer_gstin=body.buyer_gstin[:20],
        buyer_state_code=body.buyer_state_code,
    )
    db.add(payment)
    db.commit()
    url = provider_client.create_checkout(payment)
    return CheckoutOut(
        payment_id=payment.id, checkout_url=url, amount_minor=amount, currency=currency
    )


def _mark_paid(payment: Payment, provider_ref: str, db: Session) -> None:
    from pathlib import Path

    settings = get_settings()
    if payment.status == "paid":
        return  # idempotent: providers redeliver webhooks
    payment.status = "paid"
    payment.provider_ref = provider_ref[:120]
    payment.invoice_number = next_invoice_number(db, settings.invoice_prefix, datetime.now(UTC))
    job = db.get(AuditJob, payment.job_id)
    if job is not None:
        job.paid = True

    gst = compute_gst(
        payment.amount_minor,
        payment.currency,
        payment.buyer_state_code,
        settings.seller_state_code,
        settings.gst_rate_pct,
    )
    invoice_dir = Path(settings.data_dir) / "invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    html = render_invoice_html(payment, gst, settings)
    (invoice_dir / f"{payment.invoice_number}.html").write_text(html)
    if settings.enable_pdf:
        from report.pdf import html_to_pdf

        html_to_pdf(html, invoice_dir / f"{payment.invoice_number}.pdf")
    db.commit()


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header("", alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    payload = await request.body()
    if not verify_stripe_signature(payload, stripe_signature, settings.stripe_webhook_secret):
        raise HTTPException(400, "invalid webhook signature")
    event = json.loads(payload)
    if event.get("type") != "checkout.session.completed":
        return {"status": "ignored"}
    session = event["data"]["object"]
    payment = db.get(Payment, session.get("metadata", {}).get("payment_id", ""))
    if payment is None:
        raise HTTPException(404, "unknown payment")
    _mark_paid(payment, session.get("id", ""), db)
    return {"status": "ok", "invoice": payment.invoice_number}


@router.post("/webhook/razorpay")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header("", alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    payload = await request.body()
    if not verify_razorpay_signature(
        payload, x_razorpay_signature, settings.razorpay_webhook_secret
    ):
        raise HTTPException(400, "invalid webhook signature")
    event = json.loads(payload)
    if event.get("event") != "payment_link.paid":
        return {"status": "ignored"}
    entity = event["payload"]["payment_link"]["entity"]
    payment = db.get(Payment, entity.get("notes", {}).get("payment_id", ""))
    if payment is None:
        raise HTTPException(404, "unknown payment")
    _mark_paid(payment, entity.get("id", ""), db)
    return {"status": "ok", "invoice": payment.invoice_number}
