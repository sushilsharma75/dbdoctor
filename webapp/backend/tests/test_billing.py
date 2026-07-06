"""T4.3 acceptance: test-mode payment flips job to paid; INR invoice math
correct for intra vs inter-state; webhook signatures enforced."""

import hashlib
import hmac
import json
import time
from pathlib import Path

from webapp.backend.app.billing import (
    Payment,
    compute_gst,
    get_provider_client,
    next_invoice_number,
)
from webapp.backend.tests.conftest import register
from webapp.backend.tests.test_jobs import FIXTURE, _upload

STRIPE_SECRET = "whsec_test_stripe"
RAZORPAY_SECRET = "rzp_test_webhook"


# --------------------------------------------------------------------------
# GST arithmetic (pure)
# --------------------------------------------------------------------------


def test_inr_intra_state_splits_cgst_sgst():
    gst = compute_gst(999900, "INR", buyer_state_code="36", seller_state_code="36")
    assert gst["supply_type"] == "intra_state"
    assert gst["taxable_value"] == 8473.73  # 9999 / 1.18
    assert gst["cgst"] == gst["sgst"] == 762.64  # 9% each
    assert gst["igst"] == 0.0
    assert gst["total"] == 9999.0
    # the parts must reconstruct the total to the paisa
    assert round(gst["taxable_value"] + gst["cgst"] + gst["sgst"], 1) == round(gst["total"], 1)


def test_inr_inter_state_uses_igst():
    gst = compute_gst(999900, "INR", buyer_state_code="27", seller_state_code="36")
    assert gst["supply_type"] == "inter_state"
    assert gst["igst"] == 1525.27  # 18% of taxable
    assert gst["cgst"] == gst["sgst"] == 0.0


def test_inr_unknown_buyer_state_defaults_to_igst():
    gst = compute_gst(999900, "INR", buyer_state_code="", seller_state_code="36")
    assert gst["supply_type"] == "inter_state"


def test_usd_is_zero_rated_export():
    gst = compute_gst(19900, "USD", buyer_state_code="", seller_state_code="36")
    assert gst["supply_type"] == "export"
    assert gst["cgst"] == gst["sgst"] == gst["igst"] == 0.0
    assert gst["total"] == 199.0


# --------------------------------------------------------------------------
# Endpoint + webhook flow
# --------------------------------------------------------------------------


def _billing_env(monkeypatch):
    from webapp.backend.app.config import get_settings

    monkeypatch.setenv("DBDOCTOR_ENABLE_PAYMENTS", "true")
    monkeypatch.setenv("DBDOCTOR_STRIPE_WEBHOOK_SECRET", STRIPE_SECRET)
    monkeypatch.setenv("DBDOCTOR_RAZORPAY_WEBHOOK_SECRET", RAZORPAY_SECRET)
    monkeypatch.setenv("DBDOCTOR_SELLER_GSTIN", "36ABCDE1234F1Z5")
    get_settings.cache_clear()


class FakeProvider:
    def create_checkout(self, payment: Payment) -> str:
        return f"https://pay.test/{payment.provider}/{payment.id}"


def _checkout(client, monkeypatch, provider="razorpay", **body):
    from webapp.backend.app.main import app

    _billing_env(monkeypatch)
    app.dependency_overrides[get_provider_client] = lambda: FakeProvider()
    dev = register(client, "dev@dbdoctor.io")
    job_id = _upload(client, dev, FIXTURE.read_bytes()).json()["id"]
    resp = client.post(
        f"/billing/checkout/{job_id}",
        headers=dev,
        json={"provider": provider, **body},
    )
    assert resp.status_code == 200, resp.text
    app.dependency_overrides.clear()
    return dev, job_id, resp.json()


def _stripe_signed(payload: bytes) -> str:
    t = str(int(time.time()))
    v1 = hmac.new(STRIPE_SECRET.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={v1}"


def test_payments_disabled_by_default(client):
    dev = register(client, "dev@dbdoctor.io")
    job_id = _upload(client, dev, FIXTURE.read_bytes()).json()["id"]
    resp = client.post(f"/billing/checkout/{job_id}", headers=dev, json={"provider": "stripe"})
    assert resp.status_code == 503
    assert "pilot" in resp.json()["detail"]


def test_stripe_webhook_flips_job_to_paid(client, monkeypatch):
    dev, job_id, checkout = _checkout(client, monkeypatch, provider="stripe")
    payload = json.dumps(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "metadata": {"payment_id": checkout["payment_id"]},
                }
            },
        }
    ).encode()

    # bad signature is rejected
    resp = client.post(
        "/billing/webhook/stripe",
        content=payload,
        headers={"Stripe-Signature": "t=1,v1=deadbeef"},
    )
    assert resp.status_code == 400

    resp = client.post(
        "/billing/webhook/stripe",
        content=payload,
        headers={"Stripe-Signature": _stripe_signed(payload)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["invoice"].startswith("DBD-")

    job = client.get(f"/jobs/{job_id}", headers=dev).json()
    assert job["paid"] is True


def test_razorpay_webhook_generates_intra_state_invoice(client, monkeypatch, tmp_path):
    dev, job_id, checkout = _checkout(
        client, monkeypatch, provider="razorpay", buyer_state_code="36", buyer_name="Acme Pvt Ltd"
    )
    payload = json.dumps(
        {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": "plink_test_1",
                        "notes": {"payment_id": checkout["payment_id"]},
                    }
                }
            },
        }
    ).encode()
    signature = hmac.new(RAZORPAY_SECRET.encode(), payload, hashlib.sha256).hexdigest()

    resp = client.post(
        "/billing/webhook/razorpay", content=payload, headers={"X-Razorpay-Signature": signature}
    )
    assert resp.status_code == 200, resp.text
    invoice_number = resp.json()["invoice"]

    from webapp.backend.app.config import get_settings

    invoice = Path(get_settings().data_dir) / "invoices" / f"{invoice_number}.html"
    html = invoice.read_text()
    assert "762.64" in html  # CGST and SGST at 9% each
    assert "Intra-state supply" in html
    assert "998313" in html  # SAC code
    assert "36ABCDE1234F1Z5" in html  # seller GSTIN

    # webhook redelivery is idempotent: same invoice, still paid
    resp2 = client.post(
        "/billing/webhook/razorpay", content=payload, headers={"X-Razorpay-Signature": signature}
    )
    assert resp2.json()["invoice"] == invoice_number

    assert client.get(f"/jobs/{job_id}", headers=dev).json()["paid"] is True


def test_invoice_numbering_series(client, monkeypatch):
    """Sequential numbers within the fiscal-year series."""
    from datetime import UTC, datetime

    from webapp.backend.app.db import get_engine

    _billing_env(monkeypatch)
    get_engine()
    from webapp.backend.app.db import _session_factory

    db = _session_factory()
    apr = datetime(2026, 7, 5, tzinfo=UTC)
    assert next_invoice_number(db, "DBD", apr) == "DBD-2627-0001"
    # numbering follows the Indian fiscal year (Apr–Mar)
    feb = datetime(2027, 2, 1, tzinfo=UTC)
    assert next_invoice_number(db, "DBD", feb) == "DBD-2627-0001"
    db.close()
