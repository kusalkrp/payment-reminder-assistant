# Payment Reminder Assistant

A lightweight rules engine and owner dashboard for payment reminders.

## How to Run

- **Tests:** inside `python/`: `python -m unittest`
- **CLI:** inside `python/`: `python plan.py --invoices ../data/invoices.json --sent ../data/sent.json --today 2026-10-12 --out ../actions.json`
- **Page:** inside `python/`: `python app.py` (serves `http://localhost:8000/`, reads `PORT`, `DATA_DIR`, `TODAY`)

## Decisions Made

- **Standard Library Only:** Used pure Python standard library to ensure 100% offline reliability with zero installation steps.
- **Single Source of Truth:** `app.py` directly reuses `build_plan()` from `plan.py` to avoid rule divergence.
- **Deterministic Templates:** Offline-safe templates enforce exact fields and tone while strictly barring hallucinated numbers, fees, or interest.
- **In-Memory Approval State:** Kept owner decisions in server memory during runtime to satisfy approval tracking without DB complexity.
- **5-Tier Validation Precedence:** Handled data validation in strict priority order and sorted output character-by-character.

## Next Steps With More Time

- **Persistent Storage:** SQLite or PostgreSQL to persist approval decisions and sent history across restarts.
- **Dispatch Integration:** Direct SMTP or API delivery (e.g. SendGrid) for approved reminders.
- **Authentication:** Role-based access control for multiple operators.
- **Accounting Sync:** Webhooks to sync invoice statuses from QuickBooks or Xero in real-time.
