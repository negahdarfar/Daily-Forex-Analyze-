"""Research-only multi-horizon FX strength, with explicit coverage and timestamps."""
from __future__ import annotations
import math
import json
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
CURRENCIES = ("USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD")
HORIZONS = {"M5":"5min","M15":"15min","M30":"30min","M45":"45min","H1":"1h","H2":"2h","H4":"4h","H6":"6h","H8":"8h","H12":"12h","D1":"1d","W1":"7d","MN":"30d"}

def clean_close(frame, interval, cutoff):
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    close = frame["Close"]
    if isinstance(close, pd.DataFrame):
        if close.shape[1] != 1:
            raise ValueError("ambiguous close")
        close = close.iloc[:,0]
    close = pd.to_numeric(close, errors="coerce")
    close.index = pd.to_datetime(close.index, utc=True)
    close.index += pd.Timedelta(interval)
    close = close[~close.index.duplicated(keep="last")].sort_index()
    return close[(close.index <= cutoff) & np.isfinite(close) & (close > 0)]

def observation(close, cutoff, horizon, tolerance):
    if close.empty:
        return None
    end = close.index[-1]
    if cutoff - end > pd.Timedelta("15min"):
        return None
    target = end - pd.Timedelta(horizon)
    i = close.index.searchsorted(target, side="right") - 1
    if i < 0 or target - close.index[i] > pd.Timedelta(tolerance):
        return None
    return {"return":float(math.log(close.iloc[-1]/close.iloc[i])), "end":end.isoformat(), "start":close.index[i].isoformat()}

def fetch_yahoo(assets, cutoff):
    result, errors = {}, {}
    for asset in assets:
        pair = asset["symbol"]
        try:
            # Hourly history is used only for horizons >= H2; no upsampling.
            short = clean_close(yf.Ticker(asset["yahoo"]).history(period="5d", interval="5m", timeout=15), "5min", cutoff)
            long = clean_close(yf.Ticker(asset["yahoo"]).history(period="60d", interval="1h", timeout=15), "1h", cutoff)
            # Use the same recent 5m endpoint for the long series.
            combined = pd.concat([long, short]).sort_index()
            combined = combined[~combined.index.duplicated(keep="last")]
            result[pair] = {tf:observation(short if tf in ("M5","M15","M30","M45","H1") else combined, cutoff, duration, "5min" if tf in ("M5","M15","M30","M45","H1") else "65min") for tf,duration in HORIZONS.items()}
        except Exception as exc:
            errors[pair] = type(exc).__name__
            result[pair] = {}
    return result, errors

def score_matrix(observations, pairs):
    strengths, coverage = {}, {}
    for tf in HORIZONS:
        sums = {c:[] for c in CURRENCIES}
        valid = {p:observations.get(p,{}).get(tf) for p in pairs}
        # Strict balanced universe, same endpoint; never replace missing data with zero.
        endpoints = {o["end"] for o in valid.values() if o is not None}
        coverage[tf] = sum(o is not None for o in valid.values())
        if coverage[tf] != len(pairs) or len(endpoints) != 1:
            strengths[tf] = {c:None for c in CURRENCIES}
            continue
        for p,o in valid.items():
            sums[p[:3]].append(o["return"])
            sums[p[3:]].append(-o["return"])
        if any(len(v)!=7 for v in sums.values()):
            strengths[tf] = {c:None for c in CURRENCIES}
            continue
        raw = {c:float(np.mean(v)) for c,v in sums.items()}
        low, high = min(raw.values()),max(raw.values())
        strengths[tf] = {c:round(100*(v-low)/(high-low),4) if high>low else 50.0 for c,v in raw.items()}
    rows = []
    for p in pairs:
        cells = {tf:None if s[p[:3]] is None else round(s[p[:3]]-s[p[3:]],4) for tf,s in strengths.items()}
        available = [v for v in cells.values() if v is not None]
        # No ranking across incomplete horizons; publish the partial matrix anyway.
        mean = float(np.mean(available)) if len(available)==len(HORIZONS) else None
        rows.append({"symbol":p,"cells":cells,"coverage":len(available),"score":None if mean is None else round(abs(mean),4),"direction":None if mean is None else "buy" if mean>0 else "sell" if mean<0 else "neutral","alignment":None if mean is None else sum(v*mean>0 for v in available),"best_strength_horizon":None if not available else max((tf for tf in cells if cells[tf] is not None),key=lambda tf:abs(cells[tf])),"net_rr":None,"status":"research_only"})
    rows.sort(key=lambda r: (r["score"] is None,-(r["score"] or 0),r["symbol"]))
    for i,row in enumerate(rows,1):
        row["rank"] = i if row["score"] is not None else None
    return strengths,coverage,rows

def snapshot():
    assets = [a for a in json.loads((ROOT/"config/assets.json").read_text())["forex"] if a.get("enabled")]
    pairs = [a["symbol"] for a in assets]
    if len(pairs)!=28 or len({frozenset((p[:3],p[3:])) for p in pairs})!=28 or any(p[:3] not in CURRENCIES or p[3:] not in CURRENCIES or p[:3]==p[3:] for p in pairs):
        raise ValueError("expected complete 28-pair universe")
    cutoff = pd.Timestamp.now(tz="UTC").floor("5min")
    data,errors = fetch_yahoo(assets,cutoff)
    strengths,coverage,rows = score_matrix(data,pairs)
    return {"schema_version":"1.0","cutoff_utc":cutoff.isoformat(),"provider":"Yahoo Finance (unofficial, may be delayed)","method":"rolling log returns; min-max currency scores; equal horizon weights; MN=30 days, W1=7 days; not CSZ proprietary formula","horizons":HORIZONS,"strengths":strengths,"coverage":coverage,"pairs":rows,"observations":data,"errors":errors}

def main():
    result = snapshot()
    path = ROOT/"reports"/"fx-strength-latest.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(path)

if __name__ == "__main__":
    main()
