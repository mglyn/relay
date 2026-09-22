"""Run on the server, never copy secrets into the repository.

Usage: python3 scripts/init_env.py <PUBLIC_IP> [GATEWAY_DOMAIN]
"""
import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    raise SystemExit('.env already exists; refusing to overwrite secrets')
public_ip = sys.argv[1]
gateway = sys.argv[2] if len(sys.argv) > 2 else ''
env = {'CADDY_CONFIG': 'Caddyfile.ip', 'PUBLIC_IP': public_ip, 'GATEWAY_DOMAIN': gateway,
       'SUB2API_ADMIN_EMAIL': 'admin@relay.local', 'SUB2API_ADMIN_KEY': '',
       'SUB2API_IMAGE': 'ghcr.io/wei-shaw/sub2api@sha256:4c5dffab6e5ba4d3bd5382f19aad9654847b4e23de1a3d48e190146a3e6eb977'}
for key in ('POSTGRES_PASSWORD', 'SUB2API_ADMIN_PASSWORD', 'JWT_SECRET', 'TOTP_ENCRYPTION_KEY'):
    env[key] = secrets.token_hex(32)
fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(''.join(k+'='+v+'\n' for k, v in env.items()))
print('Created .env with private generated credentials (not displayed).')
