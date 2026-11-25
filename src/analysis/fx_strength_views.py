"""Independent CSZ-inspired views and structural research scenarios."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import numpy as np

LTF=("M5","M15","M30","M45","H1")
HTF=("H2","H4","H6","H8","H12","D1","W1","MN")
ENTRY={"M5":"5min","M15":"15min","M30":"30min","M45":"45min","H1":"1h","H2":"2h","H4":"4h"}

def mean(values):
    return float(np.mean(values)) if values and all(v is not None for v in values) else None

def stochastic(values, period=14):
    """Stochastic of historical currency strength, not price stochastic."""
    values=values[-period:]
    if len(values)<period or any(v is None for v in values):
        return None
    lo,hi=min(values),max(values)
    return None if hi==lo else round(100*(values[-1]-lo)/(hi-lo),4)

def history_views(current, path):
    """Store distinct actual observation snapshots, not fabricated backfill."""
    old=[]
    if path.exists():
        old=json.loads(path.read_text(encoding="utf-8"))
    record={k:current[k] for k in ("cutoff_utc","provider","strengths")}
    old=[x for x in old if not (x["cutoff_utc"]==record["cutoff_utc"] and x["provider"]==record["provider"])]
    old=sorted(old+[record],key=lambda x:x["cutoff_utc"])[-1000:]
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(old,allow_nan=False),encoding="utf-8")
    tmp.replace(path)
    same=[x for x in old if x["provider"]==record["provider"] and x["cutoff_utc"]<=record["cutoff_utc"]]
    # Only consecutive five-minute snapshots enter stochastic; gaps are not interpolated.
    recent=same[-16:]
    if any(pd.Timestamp(b["cutoff_utc"])-pd.Timestamp(a["cutoff_utc"])!=pd.Timedelta("5min") for a,b in zip(recent,recent[1:])):
        recent=[]
    meter={}
    for tf,cs in current["strengths"].items():
        meter[tf]={}
        for c in cs:
            seq=[x["strengths"].get(tf,{}).get(c) for x in recent]
            ks=[stochastic(seq[:i]) for i in range(len(seq)-2,len(seq)+1)] if len(seq)>=16 else []
            meter[tf][c]={"k":stochastic(seq),"d":mean(ks) if ks else None}
    return same,meter

def candles(frame, rule, base, cutoff):
    """Input indices are closed timestamps; require every expected component."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    frame=frame.loc[frame.index<=cutoff].sort_index()
    frame=frame[~frame.index.duplicated(keep=False)]
    frame=frame.loc[frame.index.floor(base)==frame.index]
    g=frame.resample(rule,closed="right",label="right",origin="epoch")
    out=g.agg({"Open":"first","High":"max","Low":"min","Close":"last"})
    count=int(pd.Timedelta(rule)/pd.Timedelta(base))
    return out.loc[(g["Close"].count()==count)&(out.index<=cutoff)].dropna()

def scenario(frame, side, cutoff, rule, cost=None):
    if len(frame)<22 or cutoff-frame.index[-1]>pd.Timedelta(rule)*2:
        return None
    close=frame.Close
    tr=pd.concat([frame.High-frame.Low,(frame.High-close.shift()).abs(),(frame.Low-close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.rolling(14).mean().iloc[-1])
    entry=float(close.iloc[-1])
    if not np.isfinite(atr) or atr<=0:
        return None
    prior=frame.iloc[-21:-1]
    recent=frame.iloc[-6:-1]
    if side=="buy":
        stop=float(recent.Low.min()-0.2*atr)
        levels=prior.High[(prior.High>entry)&(prior.High>=prior.High.shift(1))&(prior.High>=prior.High.shift(-1))]
        target=float(levels.min()) if len(levels) else None
        risk=entry-stop
        reward=target-entry if target is not None else None
    else:
        stop=float(recent.High.max()+0.2*atr)
        levels=prior.Low[(prior.Low<entry)&(prior.Low<=prior.Low.shift(1))&(prior.Low<=prior.Low.shift(-1))]
        target=float(levels.max()) if len(levels) else None
        risk=stop-entry
        reward=entry-target if target is not None else None
    if stop<=0 or risk<=0 or reward is None or reward<=0:
        return None
    gross=reward/risk
    net=(reward-cost)/(risk+cost) if isinstance(cost,(int,float)) and np.isfinite(cost) and 0<=cost<reward else None
    ema=close.ewm(span=20,adjust=False).mean()
    trigger=(entry>ema.iloc[-1] and entry>frame.Open.iloc[-1]) if side=="buy" else (entry<ema.iloc[-1] and entry<frame.Open.iloc[-1])
    return {"entry":entry,"sl":stop,"tp":target,"gross_rr":round(gross,4),"net_rr":None if net is None else round(net,4),"atr":atr,"bar_end":frame.index[-1].isoformat(),"trigger":bool(trigger),"status":"conditional_research"}

def enrich(data, histories, path, costs=None):
    costs=costs or {}
    history,meter=history_views(data,path)
    data["views"]={"timeframe_vs_currencies":data["strengths"],"currencies_vs_timeframe":{c:{tf:row[c] for tf,row in data["strengths"].items()} for c in next(iter(data["strengths"].values()))},"historical_strength_data":history,"stochastic_strength_meter":meter}
    cutoff=pd.Timestamp(data["cutoff_utc"])
    for row in data["pairs"]:
        p=row["symbol"]; cells=row["cells"]
        ltf=mean([cells[t] for t in LTF]); htf=mean([cells[t] for t in HTF])
        row["htf_vs_ltf"]={"htf":htf,"ltf":ltf,"aligned":None if htf is None or ltf is None else htf*ltf>0}
        row["scenario"]=None; row["opportunity_score"]=None; row["opportunity_rank"]=None
        row["entry_timeframe"]=None
        if not row["htf_vs_ltf"]["aligned"] or row["direction"] not in ("buy","sell") or p not in histories:
            continue
        side=row["direction"]; sign=1 if side=="buy" else -1
        if sign*htf<=0:
            continue
        short,long=histories[p]
        candidates=[]
        for tf,rule in ENTRY.items():
            if cells[tf] is None or sign*cells[tf]<=0:
                continue
            source,base=(short,"1min") if tf in LTF else (long,"1h")
            frame=candles(source,rule,base,cutoff)
            plan=scenario(frame,side,cutoff,rule,costs.get(p))
            if plan is None or not plan["trigger"] or plan["gross_rr"]<2:
                continue
            # Research score, not a probability. Stochastic contributes only when present.
            a=meter[tf][p[:3]]["k"]; b=meter[tf][p[3:]]["k"]
            components=[(40,row["score"]),(25,row["alignment"]/13*100),(20,min(plan["gross_rr"]/4,1)*100),(10,abs(cells[tf]))]
            if a is not None and b is not None:
                components.append((5,max(0,sign*(a-b))))
            score=sum(w*v for w,v in components)/sum(w for w,v in components)
            candidates.append((score,tf,plan))
        if candidates:
            score,tf,plan=max(candidates,key=lambda x:x[0])
            row.update(opportunity_score=round(score,4),entry_timeframe=tf,scenario=plan,net_rr=plan["net_rr"])
    ranked=sorted((r for r in data["pairs"] if r["opportunity_score"] is not None),key=lambda r:(-r["opportunity_score"],r["symbol"]))
    for i,row in enumerate(ranked,1):
        row["opportunity_rank"]=i
    data["opportunities"]=ranked
    data["views"]["htf_vs_ltf"]={r["symbol"]:r["htf_vs_ltf"] for r in data["pairs"]}
    return data

def render_table(data):
    lines=["# FX research opportunities","",f"Cutoff: {data['cutoff_utc']} | Provider: {data['provider']}","","| Rank | Pair | Side | Entry TF | Entry | SL | TP | Gross R:R | Net R:R | Score |","|---:|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for row in data["opportunities"]:
        p=row["scenario"]; digits=3 if row["symbol"].endswith("JPY") else 5
        fmt=lambda v: "—" if v is None else f"{v:.{digits}f}"
        lines.append(f"| {row['opportunity_rank']} | {row['symbol']} | {row['direction']} | {row['entry_timeframe']} | {fmt(p['entry'])} | {fmt(p['sl'])} | {fmt(p['tp'])} | {p['gross_rr']} | {p['net_rr'] if p['net_rr'] is not None else '—'} | {row['opportunity_score']} |")
    if not data["opportunities"]:
        lines.append("\nNo qualifying research scenario; no fabricated levels.")
    lines+=["","Historical reference prices; not executable quotes. Missing net costs, calendar, spread and broker validation prevent active trade status.","","## Strength heatmap","", "| Pair | "+" | ".join(data["horizons"])+" |","|---|"+"---:|"*len(data["horizons"])]
    for r in data["pairs"]:
        cells=[("⚪" if v is None else ("🟢" if v>0 else "🔴" if v<0 else "🟡")+f" {v:+.1f}") for v in r["cells"].values()]
        lines.append("| "+r["symbol"]+" | "+" | ".join(cells)+" |")
    return "\n".join(lines)+"\n"
