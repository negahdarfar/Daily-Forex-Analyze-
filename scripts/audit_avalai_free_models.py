#!/usr/bin/env python3
"""Safely discover AvalAI chat models with published zero input/output pricing."""
from __future__ import annotations
import json, os, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
BASE=os.getenv("AVALAI_BASE_URL","https://api.avalai.ir/v1").rstrip("/")
CATALOG="https://api.avalai.ir/public/models"
OUT=Path("reports/avalai-model-audit"); OUT.mkdir(parents=True,exist_ok=True)
def get_json(url,headers=None):
 req=urllib.request.Request(url,headers=headers or {"User-Agent":"daily-market-analyze/1.0"})
 with urllib.request.urlopen(req,timeout=25) as r: return json.loads(r.read().decode("utf-8"))
def zero(v):
 try: return float(v)==0.0
 except (TypeError,ValueError): return False
def eligible(m):
 p=m.get("pricing") or {}; eps=m.get("supported_endpoints") or []
 return m.get("mode")=="chat" and zero(p.get("input")) and zero(p.get("output")) and (not eps or "/v1/chat/completions" in eps)
def probe(mid,key):
 body={"model":mid,"messages":[{"role":"user","content":"Reply with exactly: OK"}],"temperature":0,"max_tokens":8,"stream":False}
 req=urllib.request.Request(BASE+"/chat/completions",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=35) as r:
   d=json.loads(r.read().decode()); c=(((d.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
   return {"status":"success","model_returned":d.get("model"),"response_received":bool(c)}
 except urllib.error.HTTPError as e: return {"status":"http_error","http_status":e.code}
 except Exception as e: return {"status":"network_error","error_type":type(e).__name__}
def main():
 stamp=datetime.now(timezone.utc).isoformat(); key=os.getenv("AVALAI_API_KEY","")
 try:
  data=get_json(CATALOG); models=data.get("data",[]) if isinstance(data,dict) else []
  if not isinstance(models,list): raise ValueError("Unexpected catalog schema")
 except Exception as e:
  result={"checked_at_utc":stamp,"status":"catalog_error","error_type":type(e).__name__,"models_total":0,"zero_cost_chat_models":[]}
  (OUT/"inventory.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
  (OUT/"SUMMARY.fa.md").write_text("# ممیزی مدل‌های AvalAI\n\nدریافت فهرست عمومی ناموفق بود.\n",encoding="utf-8")
  print("AvalAI catalog unavailable; no model was called."); return 2
 free=sorted([m for m in models if isinstance(m,dict) and eligible(m)],key=lambda m:(m.get("min_tier",999),m.get("id","")))
 probes=[{"model":m.get("id"),**probe(str(m.get("id")),key)} for m in free[:3]] if key and free else []
 result={"checked_at_utc":stamp,"status":"ok","models_total":len(models),"zero_cost_chat_models_count":len(free),"zero_cost_chat_models":[{"id":m.get("id"),"owned_by":m.get("owned_by"),"min_tier":m.get("min_tier"),"pricing":m.get("pricing"),"supported_endpoints":m.get("supported_endpoints",[]),"max_input_tokens":m.get("max_input_tokens"),"max_output_tokens":m.get("max_output_tokens")} for m in free],"authenticated_probe":{"performed":bool(probes),"results":probes,"note":"Only published zero-input/zero-output models were probed; API key is never stored."}}
 (OUT/"inventory.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 lines=["# ممیزی زنده مدل‌های AvalAI","",f"- زمان بررسی UTC: {stamp}",f"- کل مدل‌ها: **{len(models)}**",f"- مدل‌های چت با قیمت صفر ورودی و خروجی: **{len(free)}**",f"- تست احراز هویت: **{len(probes)} مدل**" if probes else "- تست احراز هویت انجام نشد.","","فقط مدل‌هایی که هر دو قیمت ورودی و خروجی آن‌ها دقیقاً صفر است واجد تست هستند. اعتبار تبلیغاتی یا تخفیف، رایگان دائمی محسوب نمی‌شود.","","## مدل‌های صفرهزینه","","| شناسه | ارائه‌دهنده | حداقل سطح | ورودی/۱M | خروجی/۱M |","|---|---|---:|---:|---:|"]
 for m in free:
  p=m.get("pricing") or {}; lines.append(f"| {m.get(chr(105)+chr(100))} | {m.get(chr(111)+chr(119)+chr(110)+chr(101)+chr(100)+chr(95)+chr(98)+chr(121),chr(8212))} | {m.get(chr(109)+chr(105)+chr(110)+chr(95)+chr(116)+chr(105)+chr(101)+chr(114),chr(8212))} | {p.get(chr(105)+chr(110)+chr(112)+chr(117)+chr(116))} | {p.get(chr(111)+chr(117)+chr(116)+chr(112)+chr(117)+chr(116))} |")
 if not free: lines.append("| موردی یافت نشد | — | — | — | — |")
 lines += ["","## تست اتصال",""]
 for p in probes: lines.append(f"- {p[chr(109)+chr(111)+chr(100)+chr(101)+chr(108)]}: **{p[chr(115)+chr(116)+chr(97)+chr(116)+chr(117)+chr(115)]}**"+(f" (HTTP {p[chr(104)+chr(116)+chr(116)+chr(112)+chr(95)+chr(115)+chr(116)+chr(97)+chr(116)+chr(117)+chr(115)]})" if p.get("http_status") else ""))
 if not probes: lines.append("هیچ تست تکمیل اجرا نشد؛ مدل پولی فراخوانی نشده است.")
 lines += ["","## تصمیم عملیاتی","","تا وقتی مدل صفرهزینه هم در کاتالوگ باشد و هم تست API آن موفق شود، به موتور تولید تحلیل متصل نمی‌شود. کلید در خروجی/لاگ ثبت نمی‌شود."]
 (OUT/"SUMMARY.fa.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
 print(f"Scanned {len(models)} models; {len(free)} published zero-cost chat candidates; {len(probes)} authenticated probes.")
 print("API key value was not logged. Audit saved under reports/avalai-model-audit/.")
 return 0 if models else 2
if __name__=="__main__": sys.exit(main())