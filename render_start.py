"""Render entry point. Validate deployment settings, then run one Uvicorn worker.

No payment, wallet, approval timer, or game integration is implemented here.
"""
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def validate_render_settings(env):
    required = ('ADMIN_TOKEN', 'EXPECTED_RECEIVER', 'MIN_DEPOSIT_ETB',
                'MIN_WITHDRAWAL_ETB', 'MAX_WITHDRAWAL_ETB',
                'ALLOWED_ORIGINS', 'MERCHANT_PAYMENT_REFERENCE', 'DB_PATH')
    for key in required:
        value = env.get(key, '').strip()
        if not value or value.upper().startswith(('REPLACE', 'YOUR_', 'CHANGE', 'EXAMPLE', 'NOT_CONFIGURED')):
            raise RuntimeError(f'Set {key} to the actual owner-approved value before starting Render')
    receiver = env['EXPECTED_RECEIVER'].strip()
    if receiver.lower() in {'demo merchant', 'local_test_merchant'}:
        raise RuntimeError('EXPECTED_RECEIVER must be the exact Telebirr account name, not a demo identity')
    if not re.fullmatch(r'\+251[79][0-9]{8}', env['MERCHANT_PAYMENT_REFERENCE'].strip()):
        raise RuntimeError('MERCHANT_PAYMENT_REFERENCE must be an Ethiopian mobile number in +251 format')
    for origin in env['ALLOWED_ORIGINS'].split(','):
        origin = origin.strip()
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query
                or parsed.fragment or parsed.username or parsed.password or '*' in origin
                or any(c.isspace() for c in origin)
                or parsed.hostname in {'localhost', '127.0.0.1', 'example.com'}
                or parsed.hostname.endswith(('.example', '.invalid'))):
            raise RuntimeError('ALLOWED_ORIGINS must contain actual exact HTTPS website origins without trailing slashes')
    database = Path(env['DB_PATH'])
    if not database.is_absolute() or not database.resolve().is_relative_to(Path('/var/data')):
        raise RuntimeError('DB_PATH must be an absolute file path beneath the /var/data persistent disk')
    if database.resolve() == Path('/var/data'):
        raise RuntimeError('DB_PATH must include a database filename under /var/data')
    port = env.get('PORT', '10000')
    if not re.fullmatch(r'[0-9]+', port) or not 1 <= int(port) <= 65535:
        raise RuntimeError('PORT must be an integer from 1 to 65535')
    return port


def main():
    port = validate_render_settings(os.environ)
    # Do not silently create an ephemeral replacement when the disk was omitted.
    if not Path('/var/data').is_mount():
        raise RuntimeError('Attach the Render persistent disk at /var/data before starting')
    # app.py validates amount limits, token length, receiver and review target on import.
    # Keep forwarded headers untrusted; see the shared-proxy rate-limit caveat.
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app:app',
                            '--host', '0.0.0.0', '--port', port,
                            '--workers', '1', '--no-proxy-headers'])


if __name__ == '__main__':
    main()
