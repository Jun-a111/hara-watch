#!/usr/bin/env python3
"""Collect unverified links to official announcements. No release dates are inferred."""
import json
import re
import urllib.request
from datetime import datetime, timezone
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
   matched.append({"game":game,"title":title[:180],"url":link,"detected_at":now,"verification":"unreviewed"})
  collected[game]=list({x["url"]:x for x in matched}.values())[:80]
  out[game]={"ok":True,"links_found":len(collected[game]),"checked_at":now}
 except Exception as exc:
  collected[game]=[]
  out[game]={"ok":False,"error":str(exc)[:120],"checked_at":now}
seen={}
for x in history:
 if isinstance(x,dict) and x.get("game") in SOURCES and isinstance(x.get("url"),str) and x["url"].startswith("https://"):seen[(x["game"],x["url"])]=x
for items in collected.values():
 for x in items:seen.setdefault((x["game"],x["url"]),x)
records=sorted(seen.values(),key=lambda x:x.get("detected_at",""),reverse=True)[:400]
OUTPUT.write_text(json.dumps({"schema":"gacha-wars-release-candidates-v1","updated_at":now,"status":out,"candidates":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("Official announcement candidate links:",len(records),{k:v.get("links_found",0) for k,v in out.items()})
