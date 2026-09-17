"""Run on the Docker host: python3 scripts/bootstrap.py. Secrets never printed."""
import json
import os
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / '.env'
env = dict(line.split('=',1) for line in path.read_text().splitlines() if line and not line.startswith('#'))
cid = subprocess.check_output(['docker','compose','ps','-q','sub2api'],cwd=root,text=True).strip()
info = json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
ip = next(iter(info['NetworkSettings']['Networks'].values()))['IPAddress']
base = 'http://'+ip+':8080/api/v1'
token = ''


def call(endpoint, method='GET', data=None):
    headers = {'Content-Type':'application/json'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    req = urllib.request.Request(base+endpoint,method=method,headers=headers,
        data=json.dumps(data).encode() if data is not None else None)
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            obj=json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 423:
            raise SystemExit('请先在 sub2api 管理台阅读并自行确认首次部署承诺，然后重新运行 bootstrap.py。') from None
        raise SystemExit('Bootstrap API failed: HTTP '+str(exc.code)+' '+endpoint) from None
    if obj.get('code') != 0:
        raise SystemExit('Bootstrap API failed: '+endpoint)
    return obj['data']


token = call('/auth/login','POST',{'email':env['SUB2API_ADMIN_EMAIL'],'password':env['SUB2API_ADMIN_PASSWORD']})['access_token']
settings=call('/admin/settings')
settings['registration_enabled']=False
call('/admin/settings','PUT',settings)
if call('/admin/settings').get('registration_enabled') is not False:
    raise SystemExit('Could not verify private registration setting')
if not env.get('SUB2API_ADMIN_KEY'):
    status=call('/admin/settings/admin-api-key')
    if status['exists']:
        raise SystemExit('Admin API key already exists; set existing key in .env instead of rotating it')
    env['SUB2API_ADMIN_KEY']=call('/admin/settings/admin-api-key/regenerate','POST',{})['key']
    # Atomic replacement with mode 0600.
    tmp=path.with_suffix('.env.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write(''.join(k+'='+v+'\n' for k,v in env.items()))
    tmp.replace(path)
print('Verified: public registration disabled; private dashboard admin key configured.')
