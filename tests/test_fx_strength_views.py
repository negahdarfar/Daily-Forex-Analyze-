import unittest
import pandas as pd
from src.analysis.fx_strength_views import stochastic,candles,scenario
from src.data.dukascopy_fx import decode_candles
import struct,lzma

class ViewTests(unittest.TestCase):
    def test_stochastic(self):
        self.assertEqual(stochastic(list(range(14))),100)
        self.assertIsNone(stochastic([50]*14))
        self.assertIsNone(stochastic([1]*13))
    def test_missing_bar(self):
        idx=pd.date_range("2026-01-01T00:01Z",periods=5,freq="min")
        data=pd.DataFrame({c:[1.0]*5 for c in ("Open","High","Low","Close")},index=idx)
        self.assertEqual(len(candles(data,"5min","1min",idx[-1])),1)
        self.assertTrue(candles(data.drop(idx[2]),"5min","1min",idx[-1]).empty)
    def test_decoder(self):
        payload=lzma.compress(struct.pack(">5If",0,100000,100010,99990,100020,1.0))
        f=decode_candles(payload,pd.Timestamp("2026-01-01T00:00Z"),"1min","EURUSD")
        self.assertAlmostEqual(f.Close.iloc[0],1.0001)
        self.assertEqual(f.index[0],pd.Timestamp("2026-01-01T00:01Z"))
    def test_no_target(self):
        idx=pd.date_range("2026-01-01",periods=25,freq="h",tz="UTC")
        f=pd.DataFrame({"Open":[1.0+i*.01 for i in range(25)],"High":[1.01+i*.01 for i in range(25)],"Low":[.99+i*.01 for i in range(25)],"Close":[1.005+i*.01 for i in range(25)]},index=idx)
        self.assertIsNone(scenario(f,"buy",idx[-1],"1h"))

if __name__=="__main__":
    unittest.main()
