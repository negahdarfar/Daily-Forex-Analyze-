import unittest
from itertools import combinations
import pandas as pd
from src.analysis.fx_strength_mtf import CURRENCIES,HORIZONS,score_matrix,observation

class StrengthTests(unittest.TestCase):
    def setUp(self):
        self.pairs = [a+b for a,b in combinations(CURRENCIES,2)]
        self.data = {p:{tf:{"return":(CURRENCIES.index(p[:3])-CURRENCIES.index(p[3:]))/1000,"end":"2026-01-01T12:00:00Z","start":"2026-01-01T11:00:00Z"} for tf in HORIZONS} for p in self.pairs}

    def test_full_matrix(self):
        s,c,rows=score_matrix(self.data,self.pairs)
        self.assertEqual(len(rows),28)
        self.assertEqual(len(s),13)
        self.assertTrue(all(r["coverage"]==13 for r in rows))
        self.assertEqual(s["H1"]["USD"],0)
        self.assertEqual(s["H1"]["NZD"],100)
        self.assertEqual(rows[0]["score"],100)

    def test_missing_blocks_rank(self):
        del self.data[self.pairs[0]]["M5"]
        s,c,rows=score_matrix(self.data,self.pairs)
        self.assertEqual(c["M5"],27)
        self.assertTrue(all(r["rank"] is None and r["cells"]["M5"] is None for r in rows))

    def test_stale_rejected(self):
        cutoff=pd.Timestamp("2026-01-01T12:00:00Z")
        close=pd.Series([1,2],index=pd.DatetimeIndex([cutoff-pd.Timedelta("1h"),cutoff-pd.Timedelta("30min")]))
        self.assertIsNone(observation(close,cutoff,"5min","5min"))

if __name__=="__main__":
    unittest.main()
