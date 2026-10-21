"""Manual receipt-review records only. No gateway verification or wallet integration."""
import hashlib
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


def money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or number != number.quantize(Decimal('0.01')):
            raise ValueError('Amount must be positive with at most two decimals')
        return format(number, '.2f')
    except (InvalidOperation, ValueError):
        raise ValueError('Invalid monetary amount') from None


def decimal_amount(value):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?', value):
        raise ValueError('Use a positive decimal amount with at most two decimals')
    return money(value)


class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    receipt_no: str = Field(min_length=6, max_length=40, pattern=r'^[A-Za-z0-9]+$')
    customer_name: str = Field(default='', max_length=100)
    # Customer claim only: independent manual reconciliation is still required.
    amount_etb: str = Field(max_length=30)

    @field_validator('amount_etb')
    @classmethod
    def submitted_amount(cls, value):
        return decimal_amount(value)

    @field_validator('receipt_no')
    @classmethod
    def normalize_receipt(cls, value):
        return value.upper()


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    amount_etb: str = Field(max_length=30)
    currency: Literal['ETB']
    receiver: str = Field(min_length=1, max_length=200)
    transaction_status: Literal['completed']
    merchant_account_checked: bool
    payer_order_checked: bool

    @field_validator('amount_etb')
    @classmethod
    def valid_amount(cls, value):
        return money(value)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision: Literal['approve', 'reject']
    reviewer: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=5, max_length=2000)
    evidence: Evidence | None = None


class WithdrawalSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    client_request_id: UUID
    customer_name: str = Field(default='', max_length=100)
    account_reference: str = Field(min_length=3, max_length=100)
    payout_phone: str = Field(min_length=10, max_length=13)
    requested_amount_etb: str = Field(max_length=30)

    @field_validator('payout_phone')
    @classmethod
    def phone(cls, value):
        if re.fullmatch(r'0[79][0-9]{8}', value):
            value = '+251' + value[1:]
        if not re.fullmatch(r'\+251[79][0-9]{8}', value):
            raise ValueError('Use an Ethiopian mobile number: +2519xxxxxxxx or +2517xxxxxxxx')
        return value

    @field_validator('requested_amount_etb')
    @classmethod
    def requested_amount(cls, value):
        return decimal_amount(value)


class WithdrawalEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identity_checked: StrictBool
    balance_checked: StrictBool
    recipient_checked: StrictBool


class WithdrawalDecision(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision: Literal['approve', 'reject']
    reviewer: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=5, max_length=2000)
    evidence: WithdrawalEvidence | None = None


class BodyLimit:
    """Bound request bodies, including chunked transfers, before JSON parsing."""
    def __init__(self, app, maximum=8192):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            total += len(message.get('body', b''))
            if total > self.maximum:
                await send({'type': 'http.response.start', 'status': 413,
                            'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"detail":"Request too large"}'})
                return
            chunks.append(message)
            if not message.get('more_body', False):
                break
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        await self.app(scope, replay, send)


def create_app(config=None):
    env = os.environ if config is None else config
    token = env.get('ADMIN_TOKEN', '')
    if len(token) < 32 or token.lower().startswith(('change', 'replace', 'example')):
        raise RuntimeError('Set ADMIN_TOKEN to a random secret of at least 32 characters')
    receiver = env.get('EXPECTED_RECEIVER', '').strip()
    if not receiver or len(receiver) > 200:
        raise RuntimeError('Set EXPECTED_RECEIVER to your merchant identity')
    if 'EXPECTED_AMOUNT_ETB' in env:
        raise RuntimeError('Remove obsolete EXPECTED_AMOUNT_ETB; use MIN_DEPOSIT_ETB and submit amount_etb')
    try:
        min_deposit = decimal_amount(env.get('MIN_DEPOSIT_ETB', '20.00'))
        min_withdrawal = decimal_amount(env.get('MIN_WITHDRAWAL_ETB', '200.00'))
        max_withdrawal = decimal_amount(env.get('MAX_WITHDRAWAL_ETB', '30000.00'))
        if Decimal(min_withdrawal) > Decimal(max_withdrawal):
            raise ValueError('Withdrawal minimum exceeds maximum')
    except (ValueError, TypeError):
        raise RuntimeError('Set valid positive ETB limits with at most two decimals and minimum <= maximum') from None
    origins = [s.strip() for s in env.get('ALLOWED_ORIGINS', '').split(',') if s.strip()]
    if not origins or any(not re.fullmatch(r'https?://[^/\s]+', s) or '*' in s for s in origins):
        raise RuntimeError('Set ALLOWED_ORIGINS to comma-separated exact http(s) origins (no slash)')
    try:
        review_minutes = int(env.get('REVIEW_TARGET_MINUTES', '2'))
        if not 1 <= review_minutes <= 1440:
            raise ValueError
    except (TypeError, ValueError):
        raise RuntimeError('Set REVIEW_TARGET_MINUTES to an integer from 1 to 1440') from None
    path = env.get('DB_PATH', './data/reviews.sqlite3')

    @contextmanager
    def db():
        connection = sqlite3.connect(path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @asynccontextmanager
    async def lifespan(app):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with db() as connection:
            connection.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY, receipt_no TEXT NOT NULL UNIQUE,
                    customer_name TEXT NOT NULL, expected_amount_etb TEXT NOT NULL,
                    expected_receiver TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending_review',
                    created_at TEXT NOT NULL, decided_at TEXT, reviewer TEXT, note TEXT, evidence TEXT
                );
                CREATE INDEX IF NOT EXISTS submission_queue ON submissions(status,created_at);
                CREATE TABLE IF NOT EXISTS rate_limits (
                    peer_hash TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id TEXT PRIMARY KEY, client_request_id TEXT NOT NULL UNIQUE,
                    customer_name TEXT NOT NULL, account_reference TEXT NOT NULL,
                    payout_phone TEXT NOT NULL, requested_amount_etb TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review', created_at TEXT NOT NULL,
                    decided_at TEXT, reviewer TEXT, note TEXT, evidence TEXT
                );
                CREATE INDEX IF NOT EXISTS withdrawal_queue ON withdrawals(status,created_at);
            ''')
        yield

    app = FastAPI(title='Keno and Telebirr Manual Requests', version='2.2.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET', 'POST'],
                       allow_headers=['Content-Type', 'Authorization'], allow_credentials=False)

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        # The supplied game is intentionally unchanged and keeps its original CDN assets.
        # Isolate the new request UI with a strict policy; no game scripts run here.
        if request.url.path != '/Game.html':
            response.headers['Content-Security-Policy'] = (
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                "form-action 'self'; frame-ancestors 'none'")
        return response

    public = Path(__file__).resolve().parent / 'public'

    @app.get('/')
    def landing():
        return FileResponse(public / 'index.html')

    @app.get('/requests')
    def requests_page():
        return FileResponse(public / 'requests.html')

    @app.get('/Game.html')
    def game():
        return FileResponse(public / 'Game.html')

    @app.get('/assets/{filename}')
    def asset(filename: str):
        if filename not in {'styles.css', 'requests.js'}:
            raise HTTPException(404, 'Not found')
        return FileResponse(public / filename)

    @app.get('/api/config')
    def public_config():
        return {'mode': 'manual_review_only', 'min_deposit_etb': min_deposit,
                'min_withdrawal_etb': min_withdrawal, 'max_withdrawal_etb': max_withdrawal,
                'expected_receiver': receiver,
                'review_target_minutes': review_minutes,
                'merchant_payment_reference': env.get('MERCHANT_PAYMENT_REFERENCE', 'NOT_CONFIGURED'),
                'merchant_instructions': env.get('MERCHANT_INSTRUCTIONS',
                    'Local manual-review demonstration. Do not send real money.')}

    def admin(authorization: str | None = Header(default=None)):
        supplied = authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
        if not secrets.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(401, 'Admin authentication required', headers={'WWW-Authenticate': 'Bearer'})

    def rate_limit(request):
        # Uses the server's resolved peer IP, never an unchecked X-Forwarded-For header.
        peer = request.client.host if request.client else 'unknown'
        digest = hashlib.sha256(peer.encode()).hexdigest()
        window = int(time.time()) // 600
        with db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('DELETE FROM rate_limits WHERE window < ?', (window - 1,))
            connection.execute('''INSERT INTO rate_limits VALUES (?, ?, 1)
                ON CONFLICT(peer_hash) DO UPDATE SET
                count=CASE WHEN window=excluded.window THEN count+1 ELSE 1 END,
                window=excluded.window''', (digest, window))
            count = connection.execute('SELECT count FROM rate_limits WHERE peer_hash=?', (digest,)).fetchone()[0]
        if count > 10:
            raise HTTPException(429, 'Too many submissions; try later', headers={'Retry-After': '600'})

    def record(row):
        import json
        data = dict(row)
        data['receipt_url'] = 'https://transactioninfo.ethiotelecom.et/receipt/' + data['receipt_no']
        data['customer_name_is_untrusted'] = True
        data['amount_is_untrusted'] = True
        data['submitted_amount_etb'] = data['expected_amount_etb']  # retain legacy DB column
        if data['evidence']:
            data['evidence'] = json.loads(data['evidence'])
        return data

    @app.get('/health')
    def health():
        with db() as connection:
            connection.execute('SELECT 1 FROM submissions LIMIT 1')
        return {'status': 'ok', 'mode': 'manual_review_only'}

    @app.post('/verify', status_code=202)
    def submit(payload: Submission, request: Request):
        if Decimal(payload.amount_etb) < Decimal(min_deposit):
            raise HTTPException(422, f'Minimum deposit is {min_deposit} ETB')
        rate_limit(request)
        submission_id = str(uuid4())
        try:
            with db() as connection:
                connection.execute('''INSERT INTO submissions
                    (id,receipt_no,customer_name,expected_amount_etb,expected_receiver,created_at)
                    VALUES (?,?,?,?,?,?)''', (submission_id, payload.receipt_no, payload.customer_name,
                    payload.amount_etb, receiver, datetime.now(timezone.utc).isoformat()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Receipt already submitted; contact support if needed') from None
        return {'verified': False, 'status': 'pending_review', 'submission_id': submission_id,
                'reason': 'Receipt submitted for manual review. Payment is not yet confirmed.'}

    @app.get('/admin/submissions', dependencies=[Depends(admin)])
    def queue(status: Literal['pending_review', 'approved_manual', 'rejected'] = 'pending_review',
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        with db() as connection:
            rows = connection.execute('SELECT * FROM submissions WHERE status=? ORDER BY created_at,id LIMIT ? OFFSET ?',
                                      (status, limit, offset)).fetchall()
        return {'items': [record(row) for row in rows]}

    @app.get('/admin/submissions/{submission_id}', dependencies=[Depends(admin)])
    def detail(submission_id: str):
        with db() as connection:
            row = connection.execute('SELECT * FROM submissions WHERE id=?', (submission_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Submission not found')
        return record(row)

    @app.post('/admin/submissions/{submission_id}/decision', dependencies=[Depends(admin)])
    def decide(submission_id: str, payload: Decision):
        import json
        with db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM submissions WHERE id=?', (submission_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Submission not found')
            if row['status'] != 'pending_review':
                raise HTTPException(409, 'Decision already recorded; cannot overwrite')
            evidence = payload.evidence
            if payload.decision == 'approve':
                if not evidence or not evidence.merchant_account_checked or not evidence.payer_order_checked:
                    raise HTTPException(422, 'Approval requires merchant account reconciliation and payer/order checks')
                if evidence.amount_etb != row['expected_amount_etb'] or evidence.receiver != row['expected_receiver']:
                    raise HTTPException(422, 'Evidence does not match submitted amount snapshot and receiver')
            status = 'approved_manual' if payload.decision == 'approve' else 'rejected'
            connection.execute('''UPDATE submissions SET status=?,decided_at=?,reviewer=?,note=?,evidence=? WHERE id=?''',
                (status, datetime.now(timezone.utc).isoformat(), payload.reviewer, payload.note,
                 json.dumps(evidence.model_dump()) if evidence else None, submission_id))
        return {'submission_id': submission_id, 'status': status, 'verified': False,
                'reason': 'Manual decision recorded only. No wallet credit or game settlement performed.'}

    def withdrawal_record(row):
        import json
        data = dict(row)
        data['withdrawal_id'] = data['id']
        data['verified'] = False
        data['request_data_is_untrusted'] = True
        data['funds_moved'] = False
        if data['evidence']:
            data['evidence'] = json.loads(data['evidence'])
        return data

    @app.post('/withdrawals', status_code=202)
    def request_withdrawal(payload: WithdrawalSubmission, request: Request):
        if not Decimal(min_withdrawal) <= Decimal(payload.requested_amount_etb) <= Decimal(max_withdrawal):
            raise HTTPException(422, f'Withdrawal amount must be {min_withdrawal}–{max_withdrawal} ETB inclusive')
        rate_limit(request)
        values = (payload.customer_name, payload.account_reference,
                  payload.payout_phone, payload.requested_amount_etb)
        key = str(payload.client_request_id)
        with db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT * FROM withdrawals WHERE client_request_id=?', (key,)).fetchone()
            if existing:
                previous = tuple(existing[field] for field in
                    ('customer_name', 'account_reference', 'payout_phone', 'requested_amount_etb'))
                if previous != values:
                    raise HTTPException(409, 'Request ID already used for different details')
                withdrawal_id, status = existing['id'], existing['status']
            else:
                withdrawal_id, status = str(uuid4()), 'pending_review'
                connection.execute('''INSERT INTO withdrawals
                    (id,client_request_id,customer_name,account_reference,payout_phone,requested_amount_etb,created_at)
                    VALUES (?,?,?,?,?,?,?)''', (withdrawal_id, key, *values,
                        datetime.now(timezone.utc).isoformat()))
        return {'withdrawal_id': withdrawal_id, 'status': status, 'verified': False,
                'funds_moved': False,
                'reason': 'Request recorded for manual review only. No funds moved or reserved.'}

    @app.get('/admin/withdrawals', dependencies=[Depends(admin)])
    def withdrawal_queue(status: Literal['pending_review', 'approved_manual', 'rejected'] = 'pending_review',
                         limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        with db() as connection:
            rows = connection.execute('SELECT * FROM withdrawals WHERE status=? ORDER BY created_at,id LIMIT ? OFFSET ?',
                                      (status, limit, offset)).fetchall()
        return {'items': [withdrawal_record(row) for row in rows]}

    @app.get('/admin/withdrawals/{withdrawal_id}', dependencies=[Depends(admin)])
    def withdrawal_detail(withdrawal_id: str):
        with db() as connection:
            row = connection.execute('SELECT * FROM withdrawals WHERE id=?', (withdrawal_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Withdrawal request not found')
        return withdrawal_record(row)

    @app.post('/admin/withdrawals/{withdrawal_id}/decision', dependencies=[Depends(admin)])
    def withdrawal_decide(withdrawal_id: str, payload: WithdrawalDecision):
        import json
        with db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM withdrawals WHERE id=?', (withdrawal_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Withdrawal request not found')
            if row['status'] != 'pending_review':
                raise HTTPException(409, 'Decision already recorded; cannot overwrite')
            evidence = payload.evidence
            if payload.decision == 'approve' and (
                not evidence or not all(evidence.model_dump().values())
            ):
                raise HTTPException(422, 'Manual approval requires independent identity, balance and recipient checks')
            status = 'approved_manual' if payload.decision == 'approve' else 'rejected'
            connection.execute('''UPDATE withdrawals SET status=?,decided_at=?,reviewer=?,note=?,evidence=? WHERE id=?''',
                (status, datetime.now(timezone.utc).isoformat(), payload.reviewer, payload.note,
                 json.dumps(evidence.model_dump()) if evidence else None, withdrawal_id))
        return {'withdrawal_id': withdrawal_id, 'status': status, 'verified': False,
                'funds_moved': False,
                'reason': 'Manual decision recorded only. No payout, reservation or wallet change performed.'}

    return app


# Startup configuration is intentionally validated immediately and fails closed.
app = create_app()
