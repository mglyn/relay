import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from billing import shares, allocate


class BillingTests(unittest.TestCase):
    def test_partial_refill_is_shared(self):
        self.assertEqual(shares([80,40,20],1),[50,30,20])

    def test_zero_consumption_and_cent_rounding(self):
        self.assertEqual(shares([0,0,0],4),[33.34,33.33,33.33])
        self.assertEqual(sum(shares([0]*7,0)),100)

    def test_full_consumption(self):
        self.assertEqual(shares([150,50,0],1),[75,25,0])

    def test_reject_impossible_usage(self):
        for usage,resets in [([-1,1],0),([101,0],0),([float('nan')],0),([1],-1),([1],1.2)]:
            with self.assertRaises(ValueError): shares(usage,resets)

    def test_weighted_quota(self):
        self.assertEqual(allocate(12,{'2':3,'3':1}),{'2':9,'3':3})
        with self.assertRaises(ValueError): allocate(5,{'2':0})
        with self.assertRaises(ValueError): allocate(5,{'2':-1})

if __name__ == '__main__': unittest.main()
