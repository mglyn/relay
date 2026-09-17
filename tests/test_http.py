import http.cookiejar
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        os.environ.update(DATA_DIR=self.tmp.name,ADMIN_PASSWORD='test-admin-password-123',
            VIEWER_PASSWORD='test-viewer-password-123',SESSION_SECRET='test-session-secret-123',COOKIE_SECURE='false')
        import server
        self.s=importlib.reload(server);self.s.init()
        self.http=self.s.ThreadingHTTPServer(('127.0.0.1',0),self.s.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.http.server_port)
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,data=None,header=True):
        headers={'Content-Type':'application/json'}
        if header:headers['X-Relay-Request']='1'
        req=urllib.request.Request(self.url+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
        try:
            r=self.client.open(req)
        except urllib.error.HTTPError as e:r=e
        with r:return r.status,json.load(r)

    def test_viewer_cannot_edit_or_read_private_data(self):
        self.assertEqual(self.request('/api/overview')[0],401)
        self.assertEqual(self.request('/api/login',{'password':'bad'})[0],401)
        self.assertEqual(self.request('/api/login',{'password':'test-viewer-password-123'})[0],200)
        self.assertEqual(self.request('/api/overview')[1]['role'],'viewer')
        self.assertEqual(self.request('/api/cycles',{})[0],403)
        self.request('/api/logout',{})
        self.assertEqual(self.request('/api/overview')[0],401)

    def test_cross_origin_simple_post_rejected(self):
        self.assertEqual(self.request('/api/login',{'password':'test-admin-password-123'},header=False)[0],403)

    def test_duplicate_member_rolls_back_whole_cycle(self):
        self.request('/api/login',{'password':'test-admin-password-123'})
        c={'name':'test','start':'2026-09-17','end':'2026-10-16','account':1,
           'members':[{'user_id':2,'name':'A'},{'user_id':2,'name':'B'}]}
        self.assertEqual(self.request('/api/cycles',c)[0],400)
        self.assertEqual(self.request('/api/overview')[1]['cycles'],[])

    def test_invalid_adjustment_rolls_back_reset(self):
        self.request('/api/login',{'password':'test-admin-password-123'})
        _,v=self.request('/api/cycles',{'name':'test','start':'2026-09-17','end':'2026-10-16','account':1,
          'members':[{'user_id':2,'name':'A'}]})
        cid=v['cycles'][0]['id']
        self.assertEqual(self.request('/api/adjust',{'cycle':cid,'resets':1,'corrections':{'2':201},'note':'invalid total'})[0],400)
        c=self.request('/api/overview')[1]['cycles'][0]
        self.assertEqual(c['resets'],0)
        self.assertEqual(c['usage'],{'2':0})

if __name__=='__main__': unittest.main()
