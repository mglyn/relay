"""Run on the server, never copy secrets into the repository."""
import os
import secrets
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    raise SystemExit('.env already exists; refusing to overwrite secrets')
dashboard, gateway = sys.argv[1:3]
env = {'DASHBOARD_DOMAIN': dashboard, 'GATEWAY_DOMAIN': gateway,
       'SUB2API_ADMIN_EMAIL': 'admin@relay.local', 'SUB2API_ADMIN_KEY': '',
       'SUB2API_IMAGE': 'ghcr.io/wei-shaw/sub2api:latest'}
for key in ('DASHBOARD_ADMIN_PASSWORD','VIEWER_PASSWORD','SESSION_SECRET',
            'POSTGRES_PASSWORD','SUB2API_ADMIN_PASSWORD','JWT_SECRET','TOTP_ENCRYPTION_KEY'):
    env[key] = secrets.token_hex(24)
fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(''.join(k+'='+v+'\n' for k,v in env.items()))
print('Created .env with private generated credentials (not displayed).')
