# webapp/frontend

Next.js 14 (app router) + Tailwind. No component library — plain, fast, boring.

| Route | Purpose |
|---|---|
| `/` | Public landing page (T4.4): positioning, how-it-works, sample PDFs, pricing, security FAQ |
| `/login` | Sign in / sign up |
| `/new-audit` | Wizard: pick engine → download collector + run command → upload snapshot.json |
| `/dashboard` | Job list with status polling ("expert review in progress" → "ready"); admins see inspect/approve |

```bash
npm install
npm run dev        # against a local backend on :8000
npm run build      # production build (NEXT_PUBLIC_API_URL is baked in here)
```

Set `NEXT_PUBLIC_API_URL` at build time to point at the deployed API.
Sample report PDFs live in `public/samples/` (regenerate with `make report-sample`).

The e2e happy-path test lives in `tests/integration/test_frontend_e2e.py`
(Python Playwright, drives a real browser against uvicorn + `next start`).
