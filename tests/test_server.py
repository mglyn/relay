import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        os.environ['DATA_DIR']=self.temp.name
        import server
        self.s=importlib.reload(server)
        self.s.init()
        with self.s.connect() as db:
            day=datetime.now(timezone.utc)
            self.cid=db.execute('INSERT INTO cycles(name,start,end,account) VALUES(?,?,?,?)',
                ('test',(day-timedelta(days=1)).date().isoformat(),(day+timedelta(days=28)).date().isoformat(),1)).lastrowid
            db.executemany('INSERT INTO members(cycle,user_id,name) VALUES(?,?,?)',[(self.cid,2,'Alice'),(self.cid,3,'Bob')])
        self.deadline=int(time.time())+86400

    def tearDown(self):
        # sqlite context managers commit but do not close until GC; close via GC for Windows cleanup.
        import gc
        gc.collect()
        self.temp.cleanup()

    def sample(self,p,costs,deadline=None):
        with patch.object(self.s,'snapshot',return_value={'percent':p,'costs':costs,'reset_at':deadline or self.deadline,'time':self.s.now()}):
            self.s.sample(self.cid)

    def test_initial_baseline_no_fabricated_usage(self):
        self.sample(40,{'2':10,'3':5})
        self.assertEqual([m['share'] for m in self.s.overview()['cycles'][0]['members']],[50,50])

    def test_weighted_deltas_idempotence_and_privacy(self):
        self.sample(20,{'2':10,'3':5})
        self.sample(40,{'2':13,'3':6})
        self.sample(40,{'2':13,'3':6})
        c=self.s.overview(True)['cycles'][0]
        self.assertEqual(c['usage'],{'2':15,'3':5})
        public=self.s.overview()['cycles'][0]
        self.assertNotIn('usage',public)
        self.assertNotIn('events',public)
        self.assertEqual([m['share'] for m in public['members']],[55,45])

    def test_rounding_retains_weight_since_last_increase(self):
        self.sample(20,{'2':10,'3':5})
        self.sample(20,{'2':13,'3':5})
        self.sample(24,{'2':13,'3':6})
        self.assertEqual(self.s.overview(True)['cycles'][0]['usage'],{'2':3,'3':1})

    def test_reset_blocks_until_review_and_does_not_guess(self):
        self.sample(70,{'2':10,'3':5})
        with self.assertRaises(ValueError):self.sample(20,{'2':13,'3':6},self.deadline+604800)
        c=self.s.overview(True)['cycles'][0]
        self.assertTrue(c['needs_review'])
        self.assertEqual(c['resets'],0)
        self.assertEqual(c['usage'],{'2':0,'3':0})
        with self.assertRaises(ValueError):self.sample(25,{'2':14,'3':6},self.deadline+604800)

    def test_missing_attribution_does_not_advance_baseline(self):
        self.sample(10,{'2':0,'3':0})
        with self.assertRaises(ValueError):self.sample(20,{'2':0,'3':0})
        self.sample(20,{'2':5,'3':0})
        self.assertEqual(self.s.overview(True)['cycles'][0]['usage'],{'2':10,'3':0})

    def test_upstream_contract_selects_weekly_not_primary(self):
        self.s.KEY='test'
        def fake(path,query=None):
            if path.endswith('/quota'):
                return {'rate_limit':{'primary_window':{'used_percent':90,'limit_window_seconds':18000,'reset_at':self.deadline},'secondary_window':{'used_percent':12,'limit_window_seconds':604800,'reset_at':self.deadline}}}
            return {'total_cost':{2:3,3:1}.get(query.get('user_id'),4)}
        with self.s.connect() as db:
            c=dict(db.execute('SELECT * FROM cycles').fetchone())
            members,_,_=self.s.ledger(db,self.cid)
        with patch.object(self.s,'upstream',side_effect=fake):
            snap=self.s.snapshot(c,members)
        self.assertEqual(snap['percent'],12)
        self.assertEqual(snap['costs'],{'2':3,'3':1})

if __name__=='__main__': unittest.main()
