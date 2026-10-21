# Anwar package: test results

**50 automated backend, API-contract, amount-policy and Render-preflight tests passed.** The mobile-sized Chromium smoke test also passed. All checks used synthetic local data; nothing was deployed and no real payment or game service was contacted.

## Confirmed behavior

- Merchant/account display: **Anwar**. Existing public deposit number: **+251995877887**. Manual-review target remains about two minutes when available, not guaranteed approval.
- Deposits require a customer-entered `amount_etb` decimal string, **ETB 20.00 or above**. Tests accepted 20, 20.01, 52.25, 30000.01 and 1000000.01, demonstrating that withdrawal limits do not cap deposits. There is no business maximum on deposits; input is bounded to 30 characters and supported monetary precision, not arbitrary precision.
- Missing amounts, below-minimum deposits, numeric rather than string amounts, excess decimal places, scientific notation, NaN and Infinity are rejected.
- Withdrawals accept **ETB 200.00–30000.00 inclusive**. 199.99 and 30000.01 are rejected, including in the browser.
- Amount limits are enforced by the server, published in public configuration and used by the separate forms. Failed configuration loading disables both forms, including after reset.
- Legacy `expected_amount` payloads are rejected. A stale `EXPECTED_AMOUNT_ETB` environment variable fails startup with an explicit migration message; remove it and use the three new limit variables.
- Manual deposit approval evidence must match the submitted amount snapshot and receiver; evidence of 500.00 cannot approve a claim of 52.25. Reviewer reconciliation and payer/order checks remain required.
- Manual approvals remain review records only: `verified: false`; withdrawal responses remain `funds_moved: false`. No automatic payment approval, wallet credit/debit, reservation, Keno settlement, transfer or payout was added.
- Duplicate receipts, withdrawal retry IDs, immutable decisions, admin authorization, shared intake rate limits, body limits, CORS, protected file routes, persistence and Render disk guards passed regression checks.
- Existing deposit rows keep their original amount and receiver snapshots; startup does not rewrite them to Anwar or the new minimum.

## Original game preserved

`public/Game.html` was compared byte-for-byte against the separately attached original and checked through the served route. SHA-256:

```text
a739d64254de246f3882586cec6211ca59f18c4395fe5dd5b17fb6a9319731b2
```

The original game was not modified or opened against its external demo backend. Its inherited external dependencies and demo behavior have not been validated or authorized for real-money use.

## Reproduce

From the package directory after creating `.venv`:

```bash
.venv/bin/python -m pip install -r requirements-tested.txt
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install playwright
.venv/bin/python tests/browser_smoke.py
node --check public/requests.js
.venv/bin/python -m pip check
```

Browser checks require Chromium on PATH or `CHROMIUM_PATH`. The browser script starts and stops a loopback server with a temporary database. Both forms were tested with optional names blank, local phone normalization, returned references, disabled resubmission, reset controls and private hashed retry metadata. It also tested a selected 52.25 deposit and failed config loading. No JavaScript page errors occurred in the normal form flows.

Verified runtime: Python 3.12.3; FastAPI 0.157.0; Uvicorn 0.54.0; Pydantic 2.14.1; Starlette 1.9.0; HTTPX 0.28.1; Playwright 1.64.0. Dependency consistency and JavaScript syntax checks passed.

Raw results are included in `verification/backend-tests.log` and `verification/browser-tests.log`.

## Not validated or authorized

No Render account, repository, service or domain was accessed or created. Render tests exercised the startup command and disk guard locally, not actual hosted disk persistence. No hosting payment was authorized. The exact HTTPS website origin remains unset. See [RENDER_SETUP.md](RENDER_SETUP.md) for remaining owner inputs and pre-deployment requirements.
