# Your Telebirr review package: Render setup

## What is ready

The separate deposit page displays the supplied merchant name **Anwar** and **+251995877887** from `MERCHANT_PAYMENT_REFERENCE`. Anwar is a supplied name, not independently verified; verify it against the merchant's own account statement before any real use. Customers choose a deposit amount of at least **20.00 ETB**, with no business-defined maximum. Withdrawals accept **200.00–30,000.00 ETB inclusive**. The page says the owner aims to review submitted deposit receipts **within about two minutes when available**. This is a target, not guaranteed approval. There is no timer that approves anything.

The supplied `public/Game.html` is unchanged byte-for-byte. Its Keno UI, scripts and external demo connections are untouched. Payment requests remain on `/requests`; they are not connected to the game.

**Nothing has been deployed.** This package is ready to configure for a Render staging test, not a production real-money gaming/payment service. No automatic approval, wallet credit/debit, game settlement, actual transfer or payout is implemented. An `approved_manual` record is only a recorded review decision; `verified` remains false.

## Owner input still needed

| Input or decision | Where it goes |
| --- | --- |
| Independent verification of the supplied merchant name `Anwar` | Check the exact account-holder name against the merchant's own Telebirr account statement before any real use; the app cannot verify the name. |
| Exact website origin(s) you will actually use, such as `https://your-selected-service.onrender.com` and any custom domain | Set `ALLOWED_ORIGINS` in Render with `sync: false`; enter the exact comma-separated HTTPS origins, no trailing slash or URL path. Include the origin serving `/requests`. The forms use same-origin API URLs; this setting alone does not enable hosting the forms on another domain. No production origin has been supplied. |
| Explicit approval for paid hosting and service details | Choose the Render account, repository/service name and region when deploying later. This package specifies a paid `starter` instance and a 1 GB persistent disk; it does not purchase them. Paid hosting approval is still missing. |
| Who monitors receipts and how customers reach you if review takes longer | Use the private admin API workflow below; add your approved support contact and availability to `MERCHANT_INSTRUCTIONS`. No SMS, push notification, background queue watcher or admin dashboard is included. |
| Confirmation you control the supplied number and have the required provider/game permissions and applicable legal authorization | Required before any real-money operation. The app cannot verify these. |

A random `ADMIN_TOKEN` must also exist and stay private. The Blueprint generates it; for dashboard/manual setup, generate one yourself. Do not send the token, Telebirr PIN, password or OTP to customers. No Telebirr login/API credentials are needed for this manual-only build. The supplied `+251995877887` and about-two-minute non-guaranteed review target remain configured; separately confirm control of the number and required provider/game permissions and legal authorization before real-money use.

Before accepting real customer funds, account authentication/binding, trusted balance records, abuse controls, privacy/retention, tamper-resistant auditing and reconciliation still need separate implementation and review. Owner configuration alone does not supply these missing production controls. Keep the testing-only/no-real-money warning until that work and the required permissions are complete.

## 1. Prepare the repository

Unzip the package. Upload the **contents of `telebirr-manual-review/`** to a private Git repository so `app.py`, `render.yaml`, `.python-version` and `requirements-tested.txt` sit at the repository root. Include the `public/` folder unchanged. Do not upload `.env`, a database, `.venv`, or customer decision/evidence files.

No connector, login or deployment has been performed for you. The following are steps to take later, not actions already completed.

## 2. Choose one Render setup method

### Blueprint

In Render, create a Blueprint from the repository and review `render.yaml` before creating resources. It requests a paid web-service instance plus persistent storage. Use `EXPECTED_RECEIVER=Anwar` and the configured limits `MIN_DEPOSIT_ETB=20.00`, `MIN_WITHDRAWAL_ETB=200.00`, and `MAX_WITHDRAWAL_ETB=30000.00`. `ALLOWED_ORIGINS` is required as a `sync: false` variable: provide the exact production HTTPS origin in the Render Environment page; that origin is not yet supplied. The Blueprint generates `ADMIN_TOKEN` and sets the supplied number, two-minute target and disk path.

Use a service name you actually control. If you do not know its final URL yet, let startup fail closed, then set `ALLOWED_ORIGINS` to the exact assigned URL and manually deploy again. Do not use a wildcard or placeholder to make it pass. For an existing Blueprint, `sync: false` variables must be set in its Environment page; later syncs do not prompt for them. Do not substitute localhost, a wildcard, or a placeholder for the actual production origin.

### Manual web service

Create a Python web service from the same repository and use:

| Setting | Value |
| --- | --- |
| Runtime | Python 3.12, selected by `.python-version` |
| Build command | `pip install -r requirements-tested.txt` |
| Start command | `python render_start.py` |
| Health check path | `/health` |
| Instances | 1 |
| Auto deploy | Off; deploy manually |
| Persistent disk mount | `/var/data` |
| Persistent disk size | 1 GB in the supplied Blueprint |

Set these environment variables in Render (not a committed `.env` file). `ALLOWED_ORIGINS` must be configured in Render as `sync: false` and set to the exact actual HTTPS origin; do not use the local origin shown in README.md.

```text
ADMIN_TOKEN=<generate a random secret with at least 32 characters>
EXPECTED_RECEIVER=Anwar
MIN_DEPOSIT_ETB=20.00
MIN_WITHDRAWAL_ETB=200.00
MAX_WITHDRAWAL_ETB=30000.00
ALLOWED_ORIGINS=https://<actual-service-name>.onrender.com
MERCHANT_PAYMENT_REFERENCE=+251995877887
REVIEW_TARGET_MINUTES=2
MERCHANT_INSTRUCTIONS=Submit the receipt number for manual review. Testing only: do not send real money. Approval is not guaranteed.
DB_PATH=/var/data/reviews.sqlite3
```

Paste environment values without the `<...>` placeholders and without shell quote characters. Render supplies `PORT`; the entry point binds `0.0.0.0:$PORT`, using one Uvicorn worker. Startup rejects missing/placeholder owner settings, non-HTTPS website origins, an invalid phone, an ephemeral database path and a missing disk mount. The app also validates the token, limits and review target.

When upgrading an existing Render service, delete the obsolete `EXPECTED_AMOUNT_ETB` environment variable before restarting or deploying; the application fails startup if that key exists. Existing SQLite deposit rows keep their original amount and receiver snapshots.

## 3. Test before opening it to customers

After you intentionally deploy later:

1. Visit `/health`. It should return `{"status":"ok","mode":"manual_review_only"}`. This is service/database health, not proof of payment.
2. Open `/requests`. Confirm the supplied name `Anwar`, the deposit minimum **20.00 ETB**, **+251995877887** and the about-two-minute review target. Deposit amounts are customer-selected and have no business-defined maximum; withdrawal input is limited to **200.00–30,000.00 ETB inclusive**. Keep the no-real-money warning while testing.
3. Submit a clearly synthetic receipt number and a deposit amount of at least 20.00 ETB. It must return `pending_review` and a reference, not payment success. Do not send money or use someone else's receipt.
4. Check the protected queue. Requests without a valid admin token must receive 401. Use synthetic evidence for tests only and never misrepresent it as a real transaction.
5. Restart/redeploy the same service with the same attached disk, then confirm the test record remains. Do not delete the disk.
6. Open `/Game.html` separately. Its appearance and behavior are inherited from the original file, including external CDN/demo dependencies; this package does not guarantee their availability or licensing.

Disk-backed services are single-instance and have deployment downtime. Free web services do not support the required persistent disk. Without it, SQLite records can disappear on restart/redeploy. The startup script intentionally refuses that unsafe fallback. Use SQLite's backup API or a stopped, consistent database backup; copying only the main file while WAL writes are active can miss records. Keep a protected backup outside the service and test restoration.

## 4. How your two-minute manual review works

You must watch the queue yourself. No alert is sent when a receipt arrives, and no record automatically changes after two minutes. The app has no customer status lookup; customers retain a reference and follow up through your chosen support process.

On a trusted terminal, set `BASE` to your actual HTTPS service URL and load `ADMIN_TOKEN` privately (do not paste it into browser code):

```bash
BASE='https://YOUR_ACTUAL_SERVICE.onrender.com'
read -r -s -p 'Admin token: ' ADMIN_TOKEN; echo
export ADMIN_TOKEN
curl -sS "$BASE/admin/submissions?status=pending_review&limit=50&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
curl -sS "$BASE/admin/withdrawals?status=pending_review&limit=50&offset=0" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

See [README.md](README.md#admin-review-server-side-only) for exact detail and approve/reject payloads. Use the submitted amount claim and receiver snapshotted on the actual request. Before recording deposit approval, independently compare the receipt, completed ETB amount, exact receiver, payer/order relationship and the transaction in your **own Telebirr account statement**. The approval evidence amount and receiver must match the snapshot; the submitted claim itself is untrusted and is not proof of payment. A submitted receipt number, customer name or public receipt page alone is not proof.

For withdrawals, independently check identity, available funds in your separate trusted records and recipient ownership before recording any approval. The app neither checks a real wallet nor sends a transfer. Review decisions are final and cannot be overwritten. If checks fail, reject or leave pending. An owner decision does not add game credits or change the preserved Keno UI.

## Important operating limits

The application distrusts forwarded IP headers. On Render, traffic may therefore share a proxy peer-IP rate-limit bucket (10 intake attempts per 10 minutes), so unrelated customers can affect one another. Do not solve this by blindly trusting all forwarded headers. Establish a verified proxy/edge abuse-control design before public customer use. CORS is not authentication or a submission access-control boundary.

The admin bearer token authorizes all reviewers; it is not a per-person account or a tamper-proof audit trail. Public intake is unauthenticated and its names, account references and claimed withdrawal balances are untrusted. Store and retain the SQLite database as sensitive customer data. These are reasons to stage/test first, not a complete production security design.

## Official Render references

[FastAPI deployment](https://render.com/docs/deploy-fastapi) · [Port binding](https://render.com/docs/web-services#port-binding) · [Persistent disks](https://render.com/docs/disks) · [Health checks](https://render.com/docs/health-checks) · [Blueprint environment settings](https://render.com/docs/blueprint-spec) · [Python version selection](https://render.com/docs/python-version)
