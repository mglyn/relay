"""One-off: find provider nodes whose exit passes OpenAI region checks."""
import json
import os
import subprocess
import sys
import urllib.request

MIP = os.environ['MIP']
PROXY = 'http://127.0.0.1:7890'
GROUP = 'PROXY'
HK = ('香港', '港', 'hongkong', 'hong kong', '澳门', 'macau', '🇭🇰', '🇲🇴')
PRIORITY = ('家宽', '台湾', '美国', '日本', '新加坡', '韩国', '加拿大', '英国', '德国')


def ctl(path, data=None):
    req = urllib.request.Request('http://%s:9090%s' % (MIP, path),
                                 method='PUT' if data else 'GET',
                                 data=json.dumps(data).encode() if data else None,
                                 headers={'Content-Type': 'application/json'})
    body = urllib.request.urlopen(req, timeout=10).read()
    return json.loads(body) if body.strip() else {}


names = [p['name'] for p in ctl('/providers/proxies/sub')['proxies']]
cand = [n for n in names if not any(k in n.lower() for k in HK)]
cand.sort(key=lambda n: next((i for i, k in enumerate(PRIORITY) if k in n), len(PRIORITY)))
print('candidates (in test order):')
for n in cand:
    print('  ', n)

CHECKS = [
    ('api', 'https://api.openai.com/v1/models'),
    ('auth', 'https://auth.openai.com/'),
    ('chatgpt', 'https://chatgpt.com/backend-api/models'),
]


def probe(url):
    try:
        r = subprocess.run(['curl', '-sx', PROXY, '--max-time', '10', '-o', '/tmp/probe_body',
                            '-w', '%{http_code}', url], capture_output=True, text=True, timeout=15)
        status = r.stdout.strip()
        try:
            body = open('/tmp/probe_body', encoding='utf-8', errors='ignore').read(4000)
        except OSError:
            body = ''
        return status or '000', body
    except subprocess.TimeoutExpired:
        return '000', ''


good = []
print('\nnode                          api    auth   chatgpt')
for n in cand:
    ctl('/proxies/' + GROUP, {'name': n})
    row = {}
    for key, url in CHECKS:
        status, body = probe(url)
        blocked = status == '000' or 'unsupported_country' in body
        row[key] = 'CUT' if status == '000' else ('R403' if blocked and status == '403' else status)
    ok = row['api'] == '401' and row['auth'] not in ('CUT', 'R403')
    print('%-30s %-6s %-6s %-6s %s' % (n[:30], row['api'], row['auth'], row['chatgpt'], '<== OK' if ok else ''))
    if ok:
        good.append(n)
        if len(good) >= 3:
            break

print('\ngood nodes:', good)
if good:
    ctl('/proxies/' + GROUP, {'name': good[0]})
    print('pinned', GROUP, 'to', good[0])
sys.exit(0 if good else 1)
