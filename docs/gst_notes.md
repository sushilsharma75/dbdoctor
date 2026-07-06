# GST notes — what my CA must verify (T4.3)

> **This code is not tax advice.** The billing module implements the rules
> below as I understand them; every item must be confirmed by a chartered
> accountant before invoices go to real customers.

## What the code does today

- Product: "DB Performance Audit", SAC **998313** (IT consulting & support).
- INR price ₹9,999 treated as **GST-inclusive**; taxable value = amount / 1.18.
- **Intra-state** (buyer state code == seller state code, default `36`
  Telangana): CGST 9% + SGST 9%.
- **Inter-state** (different or unknown buyer state): IGST 18%.
- **USD payments (Stripe)**: treated as **export of services, zero-rated
  under LUT** — no GST charged, invoice marked accordingly.
- Invoice numbering: `DBD-<FY>-<seq>` per Indian fiscal year (Apr–Mar),
  sequential, no gaps by construction.
- Invoices are generated as HTML+PDF on webhook confirmation and stored under
  `data/invoices/`.

## Questions for the CA

1. Is inclusive pricing correct for the Razorpay flow, or should GST be added
   on top of ₹9,999 at checkout?
2. Export under LUT: confirm the LUT is filed and the invoice wording
   ("export of services without payment of IGST") is sufficient; do we need
   the buyer's country and place of supply on the invoice?
3. Buyer state determination: we currently ask the buyer for their state code
   at checkout. Is a Razorpay-provided address authoritative instead?
4. B2C vs B2B: for buyers without a GSTIN, is the current invoice format
   compliant? Any e-invoicing (IRN/QR) threshold we must watch as revenue grows?
5. Registration thresholds and composition-scheme applicability at current
   projected revenue.
6. GSTR-1/GSTR-3B filing: what export documentation (FIRC/BRC from Stripe
   payouts) must be retained?

## Operational rules until sign-off

- Payments stay **feature-flagged off** (`DBDOCTOR_ENABLE_PAYMENTS=false`) for
  pilot customers; pilots are invoiced manually.
- `DBDOCTOR_SELLER_GSTIN` must be set before enabling payments in production.
