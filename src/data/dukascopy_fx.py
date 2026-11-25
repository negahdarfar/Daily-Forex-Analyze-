"""Dukascopy public historical BID candles, for permitted private research."""
import lzma
import struct
import pandas as pd
import requests

BASE = "https://datafeed.dukascopy.com/datafeed"

def decode_candles(payload, period_start, interval, symbol):
    """Decode 24-byte big-endian seconds/open/close/low/high/volume records."""
    if not payload:
        return pd.DataFrame(columns=['Open','High','Low','Close'])
    raw = lzma.decompress(payload)
    if len(raw) % 24:
        raise ValueError("truncated candle record")
    scale = 1000 if symbol.endswith("JPY") else 100000
    timestamps, rows = [], []
    seconds = int(pd.Timedelta(interval).total_seconds())
    for offset, op, close, low, high, volume in struct.iter_unpack(">5If", raw):
        if offset % seconds or min(op,close,low,high)<=0 or not low<=min(op,close)<=max(op,close)<=high:
            raise ValueError("invalid candle")
        timestamps.append(period_start+pd.Timedelta(seconds=offset+seconds))
        rows.append([op/scale,high/scale,low/scale,close/scale])
    result = pd.DataFrame(rows,columns=["Open","High","Low","Close"],index=pd.DatetimeIndex(timestamps,tz="UTC") if not timestamps else pd.DatetimeIndex(timestamps),dtype=float)
    return result[~result.index.duplicated(keep="last")].sort_index()

def fetch_series(session, symbol, cutoff):
    minute_parts, hour_parts = [], []
    today = cutoff.normalize()
    for day in (today-pd.Timedelta(days=1), today):
        url = f"{BASE}/{symbol}/{day.year}/{day.month-1:02d}/{day.day:02d}/BID_candles_min_1.bi5"
        r = session.get(url,timeout=12)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        minute_parts.append(decode_candles(r.content,day,"1min",symbol))
    first = (cutoff-pd.Timedelta(days=32)).normalize().replace(day=1)
    last = cutoff.normalize().replace(day=1)
    for month in pd.date_range(first,last,freq="MS"):
        url = f"{BASE}/{symbol}/{month.year}/{month.month-1:02d}/BID_candles_hour_1.bi5"
        r = session.get(url,timeout=12)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        hour_parts.append(decode_candles(r.content,month,"1h",symbol))
    def join(parts):
        if not parts:
            return pd.Series(dtype=float)
        s = pd.concat(parts).sort_index()
        return s[(~s.index.duplicated(keep="last")) & (s.index<=cutoff)]
    minute = join(minute_parts)
    hour = join(hour_parts)
    return minute,hour

def fetch_dukascopy(assets, cutoff, horizons, observation, histories=None):
    results, errors = {}, {}
    with requests.Session() as session:
        for asset in assets:
            symbol = asset["symbol"]
            try:
                short_frame,long_frame = fetch_series(session,symbol,cutoff)
                if histories is not None:
                    histories[symbol] = (short_frame,long_frame)
                short,long = short_frame['Close'],long_frame['Close']
                # Use 5-minute-grid endpoints, never use incomplete current bars.
                short = short[short.index.minute%5==0] if not short.empty else short
                combined = pd.concat([long,short]).sort_index()
                combined = combined[~combined.index.duplicated(keep="last")]
                results[symbol] = {tf:observation(short if tf in ("M5","M15","M30","M45","H1") else combined,cutoff,duration,"5min" if tf in ("M5","M15","M30","M45","H1") else "65min") for tf,duration in horizons.items()}
            except Exception as exc:
                errors[symbol] = type(exc).__name__
                results[symbol] = {}
    return results,errors
