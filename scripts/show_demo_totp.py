#!/usr/bin/env python3
"""Display the locally seeded analyst TOTP, for DEMO use only."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db, security

if os.environ.get('AEGIS_DEMO', '1') != '1':
    raise SystemExit('Available only when AEGIS_DEMO=1.')
row = db.query("SELECT totp_secret FROM users WHERE username='analyst'", one=True)
if not row or not row['totp_secret']:
    raise SystemExit('No seeded analyst TOTP. Run python scripts/bootstrap.py first.')
print('DEMO ONLY - do not share this secret.')
print('Analyst TOTP secret:', row['totp_secret'])
print('Current 30-second code:', security.totp_now(row['totp_secret']))
