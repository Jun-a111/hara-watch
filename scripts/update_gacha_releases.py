#!/usr/bin/env python3
"""Collect unverified links to official announcements. No release dates are inferred."""
import json
import re
import urllib.request
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"gacha-wars"/"release-candidates.json"
SOURCES={
 "ww":"https://wutheringwaves.kurogames.com/jp/main/news",
 "gi":"https://genshin.hoyoverse.com/ja/news",
 "hsr":"https://hsr.hoyoverse.com/ja-jp/news",
 "zzz":"https://zenless.hoyoverse.com/ja-jp/news",
 "nte":"https://nte.perfectworld.com/",
 "end":"https://endfield.gryphline.com/",
}
# Explicitly verified article URLs provide fallback when official news lists render client-side.
SEEDS={
 "gi":[
  ("Luna V 前半祈願 公式告知","https://genshin.hoyoverse.com/en/news/detail/162721"),
  ("Luna V 後半祈願 公式告知","https://genshin.hoyoverse.com/en/news/detail/163094"),
  ("Luna VI 後半祈願 公式告知","https://genshin.hoyoverse.com/en/news/detail/163629")
 ],
 "ww":[
  ("Ver.3.7 配信開始のお知らせ","https://wutheringwaves.kurogames.com/jp/main/news/detail/5530"),
  ("Ver.3.7 共鳴者・武器集音 第一期","https://wutheringwaves.kurogames.com/jp/main/news/detail/5547"),
  ("Ver.3.2 共鳴者・武器集音 第二期","https://wutheringwaves.kurogames.com/jp/main/news/detail/4497"),
  ("共鳴者集音 明日へ焼き付ける記憶","https://wutheringwaves.kurogames.com/jp/main/news/detail/4887")
 ]
}
KEYWORDS=("ガチャ","集音","祈願","跳躍","チャンネル","ピックアップ","新キャラ","実装","アップデート","バージョン","version","banner","update","recruit","new character","活动","卡池","版本","更新")
class Links(HTMLParser):
 def __init__(self): super().__init__();self.href=None;self.parts=[];self.items=[]
 def handle_starttag(self,tag,attrs):
  if tag=="a": self.href=dict(attrs).get("href");self.parts=[]
 def handle_data(self,data):
  if self.href is not None:self.parts.append(data)
 def handle_endtag(self,tag):
  if tag=="a" and self.href:
   self.items.append((self.href," ".join(" ".join(self.parts).split())))
   self.href=None
DATE_RE=re.compile(r"(20\d{2})[年/\-.](0?[1-9]|1[0-2])[月/\-.](0?[1-9]|[12]\d|3[01])日?")
PHASE_FIRST=("前半","第一期","第1期","phase 1","phase i","上半")
PHASE_SECOND=("後半","第二期","第2期","phase 2","phase ii","下半")
def hints(text):
 text=unescape(re.sub(r"<[^>]+>"," ",text or ""));low=" ".join(text.lower().split())
 dates=[]
 for y,m,d in DATE_RE.findall(low):
  day=f"{y}-{int(m):02d}-{int(d):02d}"
  try: datetime.fromisoformat(day);dates.append(day)
  except ValueError:pass
 first=any(k in low for k in PHASE_FIRST)
 second=any(k in low for k in PHASE_SECOND)
 return {"date_candidates":list(dict.fromkeys(dates))[:8],
         "phase_hint":"first" if first and not second else "second" if second and not first else "unknown"}
def page_hints(url):
 try:
  request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; GachaWars/1.0)"})
  with urllib.request.urlopen(request,timeout=10) as response:body=response.read(450000).decode("utf-8","replace")
  return hints(body[:180000])
 except Exception:return {"date_candidates":[],"phase_hint":"unknown"}

now=datetime.now(timezone.utc).isoformat(timespec="seconds")
try:
 previous=json.loads(OUTPUT.read_text(encoding="utf-8"))
 history=previous.get("candidates",[])
except (OSError,ValueError):history=[]
out={}
collected={}
for game,url in SOURCES.items():
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; GachaWars/1.0)"})
  with urllib.request.urlopen(req,timeout=22) as res:html=res.read(1200000).decode("utf-8","replace")
  parser=Links();parser.feed(html)
  matched=[]
  home=urlparse(url).hostname or ""
  for href,title in parser.items:
   link=urljoin(url,href);domain=urlparse(link).hostname or ""
   if not (domain==home or domain.endswith("."+home)):continue
   if not title or len(title)>180 or not any(k in title.lower() for k in KEYWORDS):continue
   if not link.startswith("https://"):continue
   matched.append({"game":game,"title":title[:180],"url":link,"detected_at":now,"verification":"unreviewed",**hints(title)})
  for title,link in SEEDS.get(game,[]):
   if not any(item["url"]==link for item in matched):matched.append({"game":game,"title":title,"url":link,"detected_at":now,"verification":"unreviewed",**hints(title)})
  collected[game]=list({x["url"]:x for x in matched}.values())[:80]
  for item in collected[game][:8]:
   detail=page_hints(item["url"])
   item["date_candidates"]=list(dict.fromkeys(item["date_candidates"]+detail["date_candidates"]))[:8]
   if item["phase_hint"]=="unknown":item["phase_hint"]=detail["phase_hint"]
  out[game]={"ok":True,"links_found":len(collected[game]),"index_links_found":len(matched)-len(SEEDS.get(game,[])),"seed_links":len(SEEDS.get(game,[])),"checked_at":now}
 except Exception as exc:
  collected[game]=[]
  out[game]={"ok":False,"error":str(exc)[:120],"checked_at":now}
seen={}
for x in history:
 if isinstance(x,dict) and x.get("game") in SOURCES and isinstance(x.get("url"),str) and x["url"].startswith("https://"):seen[(x["game"],x["url"])]=x
for items in collected.values():
 for x in items:seen[(x["game"],x["url"])]=dict(seen.get((x["game"],x["url"]),{}),**x)
records=sorted(seen.values(),key=lambda x:x.get("detected_at",""),reverse=True)[:400]
OUTPUT.write_text(json.dumps({"schema":"gacha-wars-release-candidates-v1","updated_at":now,"status":out,"candidates":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("Official announcement candidate links:",len(records),{k:v.get("links_found",0) for k,v in out.items()})
