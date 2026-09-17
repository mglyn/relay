"""Small, private quota ledger. No OpenAI credentials reach this application."""
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from billing import shares, allocate

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('DATA_DIR', str(ROOT.parent / 'data')))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'relay.db'
LOCK = threading.RLock()
SECRET = os.environ.get('SESSION_SECRET', '')
ADMIN = os.environ.get('ADMIN_PASSWORD', '')
VIEWER = os.environ.get('VIEWER_PASSWORD', '')
SECURE = os.environ.get('COOKIE_SECURE', 'true') == 'true'
BASE = os.environ.get('SUB2API_URL', 'http://sub2api:8080').rstrip('/')
KEY = os.environ.get('SUB2API_ADMIN_KEY', '')
ATTEMPTS = {}


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect():
    db = sqlite3.connect(DB, timeout=20, factory=Connection)
    db.row_factory = sqlite3.Row
    return db


def init():
    with connect() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS cycles(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
          start TEXT NOT NULL, end TEXT NOT NULL, account INTEGER NOT NULL, closed INTEGER NOT NULL DEFAULT 0,
          baseline TEXT, issue TEXT NOT NULL DEFAULT '', sampled TEXT);
        CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY, cycle INTEGER NOT NULL,
          user_id INTEGER NOT NULL, name TEXT NOT NULL, UNIQUE(cycle,user_id));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, cycle INTEGER NOT NULL,
          kind TEXT NOT NULL, payload TEXT NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL);
        ''')


def now():
    return datetime.now(timezone.utc).isoformat()


def event(db, cycle, kind, payload, note):
    db.execute('INSERT INTO events(cycle,kind,payload,note,created) VALUES(?,?,?,?,?)',
               (cycle, kind, json.dumps(payload), note, now()))


def ledger(db, cycle):
    members = [dict(m) for m in db.execute('SELECT * FROM members WHERE cycle=? ORDER BY id', (cycle,))]
    usage = {str(m['user_id']): 0.0 for m in members}
    resets = 0
    for e in db.execute('SELECT kind,payload FROM events WHERE cycle=? ORDER BY id', (cycle,)):
        p = json.loads(e['payload'])
        if e['kind'] == 'reset':
            resets += p['count']
        elif e['kind'] in ('usage', 'correction'):
            for uid, amount in p.items():
                if uid not in usage:
                    raise ValueError('账本存在未登记成员')
                usage[uid] += amount
    return members, usage, resets


def overview(admin=False):
    with connect() as db:
        cycles = []
        for row in db.execute('SELECT * FROM cycles ORDER BY id DESC'):
            c = dict(row)
            members, usage, resets = ledger(db, c['id'])
            ratios = shares(list(usage.values()), resets)
            out = {k: c[k] for k in ('id', 'name', 'start', 'end', 'closed', 'sampled')}
            out['needs_review'] = bool(c['issue'])
            out['initialized'] = bool(c['baseline'])
            out['members'] = [{'name': m['name'], 'share': ratios[i]} for i, m in enumerate(members)]
            if admin:
                out.update(account=c['account'], issue=c['issue'], resets=resets,
                           usage=usage, member_config=members)
                out['events'] = [dict(e) for e in db.execute('SELECT * FROM events WHERE cycle=? ORDER BY id DESC LIMIT 100', (c['id'],))]
            cycles.append(out)
    return {'cycles': cycles, 'role': 'admin' if admin else 'viewer',
            'gateway_url': os.environ.get('GATEWAY_PUBLIC_URL', ''), 'estimated': True}


def upstream(path, query=None):
    if not KEY:
        raise ValueError('尚未配置 sub2api 管理 API Key')
    url = BASE + '/api/v1' + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={'x-api-key': KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            obj = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError('sub2api 请求失败，请检查连接、上游账号和管理 API Key') from exc
    if obj.get('code', 0) != 0:
        raise ValueError('sub2api 返回失败，未更新账本')
    return obj['data']


def snapshot(c, members):
    # The window is identified by duration, never by primary/secondary position.
    q = upstream(f"/admin/openai/accounts/{c['account']}/quota")
    windows = [v for k, v in (q.get('rate_limit') or {}).items()
               if k.endswith('_window') and isinstance(v, dict) and v.get('limit_window_seconds') == 604800]
    if len(windows) != 1:
        raise ValueError('没有找到唯一的 7 天主额度窗口；未使用其他额度替代')
    w = windows[0]
    percent = float(w['used_percent'])
    deadline = int(w['reset_at'])
    if not math.isfinite(percent) or not 0 <= percent <= 100 or deadline <= time.time():
        raise ValueError('周额度数据无效或已过期，等待上游更新')
    query = {'account_id': c['account'], 'start_date': c['start'], 'end_date': c['end'],
             'timezone': 'Asia/Shanghai', 'nocache': 1}
    costs = {}
    for m in members:
        stats = upstream('/admin/usage/stats', dict(query, user_id=m['user_id']))
        cost = float(stats['total_cost'])  # Original model cost, before per-user multipliers.
        if not math.isfinite(cost) or cost < 0:
            raise ValueError('sub2api 计费用量异常')
        costs[str(m['user_id'])] = cost
    overall = float(upstream('/admin/usage/stats', query)['total_cost'])
    if abs(overall - sum(costs.values())) > max(0.00001, overall * 0.001):
        raise ValueError('账号总用量与成员用量不一致：可能有未登记用户或并发请求，请重试核对')
    return {'percent': percent, 'reset_at': deadline, 'costs': costs, 'time': now()}


def sample(cycle, rebaseline=False):
    with LOCK, connect() as db:
        c = db.execute('SELECT * FROM cycles WHERE id=?', (cycle,)).fetchone()
        if not c or c['closed']:
            raise ValueError('周期不存在或已经封账')
        c = dict(c)
        # Dates are local calendar dates, inclusive, matching sub2api stats API.
        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        if not c['start'] <= today <= c['end']:
            raise ValueError('当前时间不在该订阅月内；历史周期请人工核对后封账')
        members, usage, resets = ledger(db, cycle)
        try:
            s = snapshot(c, members)
            old = json.loads(c['baseline']) if c['baseline'] else None
            if old and not rebaseline:
                if c['issue'].startswith('需要核对：'):
                    raise ValueError(c['issue'])
                if s['reset_at'] != old['reset_at'] or s['percent'] < old['percent'] or time.time() >= old['reset_at']:
                    raise ValueError('需要核对：检测到周重置或重置卡。请补记重置次数、核对空档用量，再建立新基线。')
                delta = s['percent'] - old['percent']
                weights = {uid: s['costs'][uid] - old['costs'][uid] for uid in s['costs']}
                if any(v < -0.00000001 for v in weights.values()):
                    raise ValueError('需要核对：历史计费用量减少，请核对日志后建立新基线')
                if delta > 0:
                    parts = allocate(delta, {k: max(0,v) for k,v in weights.items()})
                    shares([usage[k] + parts[k] for k in usage], resets)
                    event(db, cycle, 'usage', parts, '自动估算：周额度变化按原始模型计费用量分配')
                else:
                    # Retain cost baseline until quota rounding reveals consumption.
                    s['costs'] = old['costs']
            else:
                event(db, cycle, 'baseline', {'percent': s['percent'], 'reset_at': s['reset_at']},
                      '建立采样基线；此前消耗不自动归属，需管理员补录')
            db.execute('UPDATE cycles SET baseline=?,sampled=?,issue=? WHERE id=?',
                       (json.dumps(s), s['time'], '', cycle))
        except (ValueError, KeyError, TypeError) as exc:
            message = str(exc) if isinstance(exc, ValueError) else '上游接口格式不匹配，账本未更新'
            db.execute('UPDATE cycles SET issue=? WHERE id=?', (message, cycle))
            db.commit()
            raise ValueError(message) from exc


def collector():
    while True:
        try:
            with connect() as db:
                ids = [r['id'] for r in db.execute('SELECT id FROM cycles WHERE closed=0')]
            for cid in ids:
                try:
                    sample(cid)
                except ValueError:
                    pass
        except Exception as exc:
            print('collector error:', type(exc).__name__, flush=True)
        time.sleep(max(30, int(os.environ.get('POLL_SECONDS', '60'))))


def token(role):
    body = base64.urlsafe_b64encode(json.dumps({'role': role, 'exp': int(time.time()) + 43200}).encode()).decode()
    sig = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + '.' + sig


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Never log query strings, credentials, or POST bodies.
        pass

    def role(self):
        from http.cookies import SimpleCookie
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))['relay_session'].value
            body, sig = cookie.split('.')
            expected = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            data = json.loads(base64.urlsafe_b64decode(body))
            return data['role'] if data['exp'] > time.time() else None
        except (KeyError, ValueError, TypeError):
            return None

    def send(self, status, content, kind='application/json; charset=utf-8', cookie=None):
        raw = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/health':
            return self.send(200, {'ok': True})
        if path in ('/', '/app.js', '/style.css'):
            file, mime = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                          '/style.css': ('style.css', 'text/css')}[path]
            return self.send(200, (ROOT/'static'/file).read_bytes(), mime+'; charset=utf-8')
        if not self.role():
            return self.send(401, {'error': '请先登录'})
        if path == '/api/overview':
            with LOCK:
                return self.send(200, overview(self.role() == 'admin'))
        return self.send(404, {'error': '页面不存在'})

    def do_POST(self):
        if self.headers.get('X-Relay-Request') != '1' or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(403, {'error': '请求来源校验失败'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32768:
                raise ValueError('请求大小无效')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求格式无效')
            path = urllib.parse.urlsplit(self.path).path
            if path == '/api/login':
                # Single private group: a global throttle is independent of spoofed proxy headers.
                with LOCK:
                    stamp, failures = ATTEMPTS.get('login', (time.time(), 0))
                    if time.time() - stamp > 300:
                        stamp, failures = time.time(), 0
                    if failures >= 20:
                        return self.send(429, {'error': '尝试次数过多，请五分钟后重试'})
                    password = str(data.get('password', ''))
                    role = 'admin' if hmac.compare_digest(password.encode(), ADMIN.encode()) else 'viewer' if hmac.compare_digest(password.encode(), VIEWER.encode()) else None
                    if not role:
                        ATTEMPTS['login'] = (stamp, failures + 1)
                        return self.send(401, {'error': '访问密码不正确'})
                cookie = 'relay_session='+token(role)+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'+('; Secure' if SECURE else '')
                return self.send(200, {'role': role}, cookie=cookie)
            if path == '/api/logout':
                return self.send(200, {'ok': True}, cookie='relay_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'+('; Secure' if SECURE else ''))
            if self.role() != 'admin':
                return self.send(403, {'error': '仅管理员可修改账本'})
            with LOCK:
                self.mutate(path, data)
            return self.send(200, overview(True))
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as exc:
            return self.send(400, {'error': str(exc) if isinstance(exc, ValueError) else '输入格式或成员 ID 无效'})
        except Exception as exc:
            print('request error:', type(exc).__name__, flush=True)
            return self.send(500, {'error': '服务暂时不可用，未完成操作'})

    def mutate(self, path, data):
        with connect() as db:
            if path == '/api/cycles':
                start, end = data['start'], data['end']
                datetime.strptime(start, '%Y-%m-%d')
                datetime.strptime(end, '%Y-%m-%d')
                if start > end or (datetime.fromisoformat(end)-datetime.fromisoformat(start)).days > 40:
                    raise ValueError('周期应为不超过 41 天的订阅月；结束日期包含当天')
                if db.execute('SELECT 1 FROM cycles WHERE NOT(end<? OR start>?)', (start, end)).fetchone():
                    raise ValueError('订阅周期不能重叠')
                if db.execute('SELECT 1 FROM cycles WHERE closed=0').fetchone():
                    raise ValueError('请先封账当前周期')
                members = data['members']
                if not isinstance(members, list) or not 1 <= len(members) <= 30:
                    raise ValueError('成员数量须为 1–30 人')
                name = str(data['name']).strip()
                account = int(data['account'])
                if not name or len(name) > 60 or account <= 0:
                    raise ValueError('周期名称或上游账号 ID 无效')
                cid = db.execute('INSERT INTO cycles(name,start,end,account) VALUES(?,?,?,?)', (name,start,end,account)).lastrowid
                for m in members:
                    uid, label = int(m['user_id']), str(m['name']).strip()
                    if uid <= 0 or not label or len(label) > 40:
                        raise ValueError('成员昵称或 sub2api 用户 ID 无效')
                    db.execute('INSERT INTO members(cycle,user_id,name) VALUES(?,?,?)', (cid,uid,label))
                event(db,cid,'created',{},'创建周期，成员名单在本周期内固定')
                return
            cid = int(data['cycle'])
            c = db.execute('SELECT * FROM cycles WHERE id=?', (cid,)).fetchone()
            if not c or c['closed']:
                raise ValueError('周期不存在或已封账')
            if path in ('/api/sample', '/api/rebaseline'):
                # Release this read connection before the sampler writes.
                pass
            elif path == '/api/adjust':
                note = str(data.get('note', '')).strip()
                if len(note) < 3 or len(note) > 500:
                    raise ValueError('请填写 3–500 字的核对说明')
                members, usage, resets = ledger(db,cid)
                count = data.get('resets',0)
                if isinstance(count,bool) or not isinstance(count,int) or not 0 <= count <= 100:
                    raise ValueError('新增重置次数应为 0–100 的整数')
                corrections = data.get('corrections', {})
                if not isinstance(corrections,dict) or any(k not in usage for k in corrections):
                    raise ValueError('修正用量包含未知成员')
                corrections = {k: float(v) for k,v in corrections.items()}
                shares([usage[k]+corrections.get(k,0) for k in usage], resets+count)
                if count:
                    event(db,cid,'reset',{'count':count},note)
                if corrections:
                    event(db,cid,'correction',corrections,note)
                return
            elif path == '/api/close':
                if c['issue'] or not c['baseline']:
                    raise ValueError('请先核对异常并完成采样，再封账')
                if data.get('confirmed') is not True:
                    raise ValueError('请明确确认本周期账单')
                event(db,cid,'closed',{},'管理员核对并封账；比例不再变化')
                db.execute('UPDATE cycles SET closed=1 WHERE id=?', (cid,))
                return
            else:
                raise ValueError('未知操作')
        if path == '/api/rebaseline' and data.get('confirmed') is not True:
            raise ValueError('建立新基线前请确认已补记重置及空档消耗')
        sample(cid, path == '/api/rebaseline')


if __name__ == '__main__':
    if min(len(SECRET),len(ADMIN),len(VIEWER)) < 16 or ADMIN == VIEWER:
        raise SystemExit('配置至少 16 位的独立 ADMIN_PASSWORD、VIEWER_PASSWORD 和 SESSION_SECRET')
    init()
    threading.Thread(target=collector,daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8090'))),Handler)
    server.daemon_threads = True
    server.serve_forever()
