# Keno + Telebirr manual requests — Render-ready staging package

One local app serves your **unchanged Atlas-V Keno page** alongside a **separate deposit and withdrawal request interface**. Requests are stored in SQLite for a person to review. Nothing is deployed.

**This is request intake, not a payment or wallet system.** No automatic payment approval, receipt scraping, wallet credit/debit, balance reservation, game settlement, or actual withdrawal exists. Even an admin approval is only a final review record: `verified` remains `false` and withdrawals always return `funds_moved: false`.

## Render setup and owner inputs

Start with [RENDER_SETUP.md](RENDER_SETUP.md) for the Blueprint, persistent disk, exact environment settings and pre-live checklist. Nothing has been deployed. The supplied merchant display name is `Anwar`; independently verify it against the merchant's own account statement before any real use. The exact HTTPS origin and approval for paid hosting are still missing.

The deposit number is **+251995877887** in `.env.example` and `render.yaml`. Customers choose a deposit claim of at least **20.00 ETB**; there is no business-defined maximum. Withdrawals are limited to **200.00–30,000.00 ETB inclusive**. The separate request page displays an **about two-minute manual-review target when available**, never guaranteed approval. No approval timer, alert service or automatic crediting exists. The exact HTTPS website origin and approval for paid hosting remain owner inputs. Local placeholders and Render startup validation intentionally block missing configuration.

## Start locally

Requires Python 3.10+ and internet access to install dependencies. Commands below use Bash on Linux/macOS (on Windows, use WSL).

```bash
cd telebirr-manual-review
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Edit `.env`, replacing `ADMIN_TOKEN` with the generated token. Use the supplied `EXPECTED_RECEIVER=Anwar` (not independently verified), and configure the limits and local origin as follows:

```text
EXPECTED_RECEIVER=Anwar
MIN_DEPOSIT_ETB=20.00
MIN_WITHDRAWAL_ETB=200.00
MAX_WITHDRAWAL_ETB=30000.00
ALLOWED_ORIGINS=http://localhost:8000
```

Remove any obsolete `EXPECTED_AMOUNT_ETB` line from the copied or existing `.env`; the application refuses startup while that key remains. For synthetic local testing use unmistakably synthetic records and never send real money. The number **+251995877887** is already supplied; `REVIEW_TARGET_MINUTES=2` is display-only. Keep the testing-only warning in `MERCHANT_INSTRUCTIONS`.

```bash
chmod 600 .env
bash run.sh
```

Open **http://localhost:8000/**. The landing page links to:

- `/Game.html` — the original game in a separate tab.
- `/requests` — deposit and withdrawal request forms.
- `/health` — service/database health, not payment status.

`run.sh` binds only to `127.0.0.1:8000`, uses one worker, and does not trust forwarded IP headers. It loads `.env` as trusted shell input; never source an untrusted file. Stop with Ctrl+C. The SQLite file survives restarts. Do not open the request HTML directly with `file://`; it needs the local server.

Without `run.sh`, export the variables yourself and run `.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers`. The Python application does not load `.env` itself.

## Use the request forms

### Deposit review

The interface displays the configured merchant identity, payment reference, instructions, and minimum deposit amount. Choose and submit an amount of at least **20.00 ETB** (up to two decimal places); there is no business-defined maximum. Enter a receipt number (6–40 alphanumeric characters) and optionally a name. The server normalizes the receipt and queues the untrusted amount claim as `pending_review`. A duplicate receipt is rejected even after a decision.

`POST /verify` requires `amount_etb` as a decimal string of at most 30 characters. The legacy `expected_amount` field is rejected, not accepted or ignored. The stored `expected_amount_etb` database column is retained for compatibility with existing databases: newly submitted rows use it for the customer's untrusted amount claim, not an expected or verified payment amount; existing rows retain their original amount and receiver snapshots unchanged. A receipt number or displayed payer name alone is not proof of payment. There is no upload facility and no automatic receipt fetching.

### Withdrawal review

Enter an account reference, optional name, Ethiopian mobile recipient number, and requested amount. Use `+2519xxxxxxxx`, `+2517xxxxxxxx`, or the equivalent local `09xxxxxxxx` / `07xxxxxxxx` form. The server normalizes phone numbers; this is syntax validation only, not proof of ownership or Telebirr availability.

The requested amount is an **untrusted claim**, not a balance or entitlement. Intake accepts amounts from **200.00 through 30,000.00 ETB inclusive** (up to two decimal places); these are validation limits, not a payout promise. No account login or wallet exists in this starter. Reviewers must independently establish identity, available funds, and recipient ownership before recording any approval. If they cannot, leave pending or reject.

A UUID request key prevents a retry with the same details from creating another record. A reused key with different details receives `409`. The form retains its key across retries for the same payload. After success, use its reset/new-request control to start another request. Do not assume a failed network response means the server did not record a request. Deposit retries are protected by the unique receipt number.

Both forms show a request reference, not a payment success message. Do not share personal request details publicly. There is no public request listing or public lookup endpoint; follow-up is through your own trusted operator process.

## Admin review (server-side only)

There is deliberately **no admin token in browser code and no browser admin screen**. Run these commands in a second local Bash terminal from this directory. `.env` must be your own trusted file.

```bash
set -a; source .env; set +a
BASE='http://127.0.0.1:8000'

# Deposit queue and single-record detail
curl -sS "$BASE/admin/submissions?status=pending_review&limit=50&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
curl -sS "$BASE/admin/submissions/DEPOSIT_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Withdrawal queue and detail
curl -sS "$BASE/admin/withdrawals?status=pending_review&limit=50&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
curl -sS "$BASE/admin/withdrawals/WITHDRAWAL_ID" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Replace the ID placeholders with returned IDs. List filters accept `pending_review`, `approved_manual`, or `rejected`; `limit` is 1–100 and `offset` supports pagination. All admin endpoints require a valid bearer token. Keep it private; it grants access to all request details and decisions.

### Record a deposit decision

Review the merchant's **own account statement**, exact receiver and claimed ETB amount, receipt, and payer/account relationship independently. Anwar is only the supplied display name; verify it independently against the account statement before any real use. The admin record includes a receipt URL for reference only; the server never opens it. A public receipt page is not sufficient evidence.

For approval, create a local `deposit-decision.json` with your actual review evidence:

```json
{
  "decision": "approve",
  "reviewer": "YOUR_REVIEWER_ID",
  "note": "Explain the independent checks performed.",
  "evidence": {
    "amount_etb": "THE_SUBMITTED_AMOUNT_CLAIM",
    "currency": "ETB",
    "receiver": "YOUR_EXACT_MERCHANT_IDENTITY",
    "transaction_status": "completed",
    "merchant_account_checked": true,
    "payer_order_checked": true
  }
}
```

The evidence amount and receiver must exactly match the submitted claim and receiver snapshotted by the server when the deposit request was submitted. The amount claim remains untrusted until independently confirmed in the merchant's own statement. Then:

```bash
curl -sS -X POST "$BASE/admin/submissions/DEPOSIT_ID/decision" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @deposit-decision.json
```

### Record a withdrawal decision

Create `withdrawal-decision.json` only after independently checking the claimed account, available funds in your separate trusted records, and recipient ownership:

```json
{
  "decision": "approve",
  "reviewer": "YOUR_REVIEWER_ID",
  "note": "Explain the independent identity, balance and recipient checks.",
  "evidence": {
    "identity_checked": true,
    "balance_checked": true,
    "recipient_checked": true
  }
}
```

```bash
curl -sS -X POST "$BASE/admin/withdrawals/WITHDRAWAL_ID/decision" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @withdrawal-decision.json
```

These fields are reviewer attestations, not checks the application can carry out. **Approval does not send money, reserve funds, or change a wallet.** No payout credentials or payment gateway integration exist.

For either type, reject using `{"decision":"reject","reviewer":"YOUR_REVIEWER_ID","note":"Reason for rejection."}` instead; evidence is optional for rejection. Decisions are final and cannot be overwritten (`409` on a second decision). Review notes require at least 5 characters and reviewer IDs at least 2. Do not commit local decision files containing personal data.

## What was preserved and changed

`public/Game.html` is copied byte-for-byte from the supplied file. Its SHA-256 is:

```text
a739d64254de246f3882586cec6211ca59f18c4395fe5dd5b17fb6a9319731b2
```

No game HTML, CSS, controls, scripts, wallet display, or game listener was modified. There is no iframe, message bridge, or injected payment button. Navigate back to the landing page or use separate tabs.

The original page still uses Atlas-V CDN assets and the external demo server `keno-demo.atlas-v.com`, and contains its original demo identifiers. The supplied file's preservation does not guarantee that external service is available, licensed, or fully functional. It is **not an offline game**. This package does not control its external demo behavior or connect it to real money.

The starter's deposit API, evidence checks, duplicate protection, and admin decision semantics remain. Added: a separate withdrawal table/API, public config allowlist, exact static routes, request forms, and local startup script. The old `frontend-submit.js` game-injection snippet has been removed; **do not patch it into the original page**. The new `public/requests.js` operates only on the separate interface.

Existing SQLite deposit databases can be reused: startup creates the new withdrawal table without dropping deposit records; existing deposit amount and receiver snapshots remain unchanged. Back up before changing versions. The archive includes the owner-supplied public deposit number but no database, secret token, private payment credentials or installed virtual environment.

## API summary and boundaries

- `GET /api/config`: public merchant display configuration, `min_deposit_etb`, `min_withdrawal_etb`, `max_withdrawal_etb`, and review target in minutes; it does not expose `expected_amount_etb`, the admin token, or the database path. If config cannot be loaded, both request forms fail closed and are disabled.
- `POST /verify`: `{ "receipt_no": "ABC123456", "amount_etb": "20.00", "customer_name": "Optional name" }` → `202`, pending review of the submitted claim. `amount_etb` must be a decimal string of at most 30 characters; legacy `expected_amount` is rejected. Deposit claims have a 20.00 ETB minimum and no business-defined maximum.
- `POST /withdrawals`: `{ "client_request_id": "a-valid-uuid", "account_reference": "YOUR_ACCOUNT_REFERENCE", "payout_phone": "+2519xxxxxxxx", "requested_amount_etb": "200.00", "customer_name": "Optional name" }` → `202`, untrusted request intake (200.00–30,000.00 ETB inclusive). Replace the phone/UUID placeholders with syntactically valid test data. A replay returns the original ID and its current review status, never a payout status.
- Admin list/detail/decision endpoints are shown above. Deposit detail includes `submitted_amount_etb` and `amount_is_untrusted: true`; reviewers must verify the claim independently. No user-supplied wallet IDs, approval statuses, or balance fields are accepted.
- Shared SQLite-backed intake limit: 10 valid-schema submission attempts per peer IP per 10-minute window, including retries. Excess returns `429`; request bodies over 8192 bytes return `413`; invalid inputs return `422`. Unknown files/routes return `404`.

This is a **local manual-review starter, not production financial infrastructure**. Requester identity, claimed funds and contact details are untrusted. CORS is not authentication. The shared admin token is not per-person identity, notes are not a tamper-proof audit log, SQLite data is not encrypted by this app, and repeated deliberate requests using new UUIDs are not account-level duplicate protection. Protect the database, restrict machine access, apply retention rules, and never place `.env` or SQLite under a public file server.

Before any real-world use, independently address authentication/account binding, authorization, privacy, tamper-resistant auditing, abuse controls, operational reconciliation, and applicable gambling/payment laws and provider permissions. Do not open this starter to real customer payments or treat it as authority to debit or pay anyone. Render configuration is for controlled staging first; see RENDER_SETUP.md for operational limits and missing production controls.

## Run tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Tests use temporary databases and synthetic data and never contact payment or game services. `requirements-tested.txt` records the dependency versions used for this package; install it for the tested runtime, then install `requirements-dev.txt` for the test client. Tests cover the inherited receipt flow plus withdrawal validation, admin authentication, duplicate handling, review-only decisions, static-file boundaries, and exact game preservation.

See [TEST_RESULTS.md](TEST_RESULTS.md) for the new test results. Tests use synthetic data; no real payment was sent or verified.

Optional browser test (requires a locally installed Chromium browser):

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python tests/browser_smoke.py
```

Set `CHROMIUM_PATH=/path/to/chromium` if it is not on your PATH. The browser test starts and stops its own loopback server with a temporary database and synthetic data. It does not open the game or contact its external services. Withdrawal retry storage contains only a SHA-256 payload fingerprint and a random request ID, not the submitted name, phone, or account reference; explicit reset after success clears that retry metadata.
