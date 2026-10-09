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
 "nte":"https://nte.perfectworld.com/jp/article/news/gamenews/index.html",
 "end":"https://endfield.gryphline.com/ja-jp/news",
}
# Explicitly verified article URLs provide fallback when official news lists render client-side.
SEEDS={
 "ww":[
  ("Ver.3.7 配信開始のお知らせ","https://wutheringwaves.kurogames.com/jp/main/news/detail/5530"),
  ("Ver.3.7 共鳴者・武器集音 第一期","https://wutheringwaves.kurogames.com/jp/main/news/detail/5547"),
  ("Ver.3.2 共鳴者・武器集音 第二期","https://wutheringwaves.kurogames.com/jp/main/news/detail/4497"),
  ("共鳴者集音 明日へ焼き付ける記憶","https://wutheringwaves.kurogames.com/jp/main/news/detail/4887")
 ],
 "gi":[
  ("Luna V 前半祈願 公式告知","https://genshin.hoyoverse.com/en/news/detail/162721"),
  ("Luna V 後半祈願 公式告知","https://genshin.hoyoverse.com/en/news/detail/163094"),
  ("Luna VI 後半祈願 公式告知","https://genshin.hoyoverse.com/en/news/detail/163629")
 ],
 "hsr":[
  ("Ver.3.0「再創紀の凱歌」アップデートについて","https://hsr.hoyoverse.com/ja-jp/news/127987")
 ],
 "zzz":[
  ("Ver.3.2期間限定チャンネル（後半）","https://zenless.hoyoverse.com/ja-jp/news/166475"),
  ("Ver.3.2 予告番組・情報まとめ","https://zenless.hoyoverse.com/ja-jp/news/165917"),
  ("Ver.2.6期間限定チャンネル（前半）","https://zenless.hoyoverse.com/ja-jp/news/162496"),
  ("Ver.3.3予告番組のお知らせ","https://zenless.hoyoverse.com/m/ja-jp/news/166552")
 ],
 "nte":[
  ("NTE 正式サービス開始","https://nte.perfectworld.com/jp/article/news/gamenews/20260428/261953.html")
 ],
 "end":[
  ("特別スカウト「臨淵望北」","https://endfield.gryphline.com/ja-jp/news/2656")
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
DATE_RE=re.compile(r"(?<!\d)(20\d{2})[年/\-.](0?[1-9]|1[0-2])[月/\-.](0?[1-9]|[12]\d|3[01])日?(?!\d)")
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
DATE_TOKEN=r"20\d{2}(?:年|[./-])\s*\d{1,2}(?:月|[./-])\s*\d{1,2}日?"
CLOCK_TOKEN=r"(?:\s*[（(]?\s*\d{1,2}[:：時]\d{0,2}分?\s*[）)]?)?"
PERIOD_RE=re.compile(r"("+DATE_TOKEN+CLOCK_TOKEN+r")\s*(?:～|〜|~|－|–|—|から|to|至)\s*("+DATE_TOKEN+CLOCK_TOKEN+r")",re.I)
DATE_PREFIX_RE=re.compile(r"("+DATE_TOKEN+CLOCK_TOKEN+r")\s*(?:～|〜|~|－|–|—|から|to|至)\s*(\d{1,2}月\s*\d{1,2}日"+CLOCK_TOKEN+r")",re.I)
CHARACTER_CONTEXT=("提供割合が上昇","ピックアップ中","★6オペレーター","登場キャラクター","対象キャラクター","ピックアップ対象","限定キャラクター","対象エージェント","集音対象","祈願対象","跳躍対象","スカウト対象")
QUOTED_NAME=re.compile(r"[「『〖](.{2,18}?)[」』〗]")
NON_CHARACTER=("スカウト","ガチャ","イベント","チャンネル","祈願","集音","ピックアップ","バージョン","開催","更新","期間","記憶","武器","訓練","作戦","ショップ","任務","ストーリー")
def article_details(text):
 text=" ".join(text.split())
 periods=list({(m.group(1).strip(),m.group(2).strip()):{"raw":m.group(0)[:110].strip(),"start_raw":m.group(1).strip(),"end_raw":m.group(2).strip()} for pattern in (PERIOD_RE,DATE_PREFIX_RE) for m in pattern.finditer(text)}.values())[:5]
 characters=[]
 for clue in CHARACTER_CONTEXT:
  for match in re.finditer(re.escape(clue),text):
   # Restrict to text after the explicit target label; avoid unrelated quoted announcements.
   excerpt=text[match.end():match.end()+65]
   for name in QUOTED_NAME.findall(excerpt):
    if any(word in name for word in NON_CHARACTER) or re.search(r"\d{4}|Ver\.|版本",name,re.I):continue
    if name not in characters:characters.append(name)
 return {"period_candidates":periods,"character_candidates":characters[:12],"extraction_note":"告知本文内の対象表現に続く名前候補（未検証）"}
class ArticleText(HTMLParser):
 def __init__(self):
  super().__init__();self.depth=0;self.parts=[];self.body=[];self.title=[];self.in_title=False;self.skip=0;self.in_body=False
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style","footer","nav","header"):self.skip+=1
  if tag=="body":self.in_body=True
  if tag=="title":self.in_title=True
  if tag in ("article","main"):self.depth+=1
 def handle_endtag(self,tag):
  if tag in ("script","style","footer","nav","header"):self.skip=max(0,self.skip-1)
  if tag=="title":self.in_title=False
  if tag in ("article","main"):self.depth=max(0,self.depth-1)
  if tag=="body":self.in_body=False
 def handle_data(self,data):
  if self.in_title:self.title.append(data)
  if self.in_body and not self.skip:
   self.body.append(data)
   if self.depth:self.parts.append(data)
class StructuredArticle(HTMLParser):
 """Read article text from JSON-LD and selected metadata, never arbitrary app state."""
 def __init__(self):
  super().__init__();self.capture=False;self.scripts=[];self.current=[];self.meta=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=="script" and a.get("type","").lower()=="application/ld+json":
   self.capture=True;self.current=[]
  if tag=="meta" and a.get("property") in ("og:description","article:description"):
   self.meta.append(a.get("content",""))
  if tag=="meta" and a.get("name")=="description":
   self.meta.append(a.get("content",""))
 def handle_data(self,data):
  if self.capture:self.current.append(data)
 def handle_endtag(self,tag):
  if tag=="script" and self.capture:
   self.scripts.append("".join(self.current));self.capture=False
 def texts(self):
  out=[]
  def visit(node,depth=0):
   if depth>5:return
   if isinstance(node,list):
    for item in node[:30]:visit(item,depth+1)
   elif isinstance(node,dict):
    typ=node.get("@type",[])
    if isinstance(typ,str):typ=[typ]
    if any(t in ("NewsArticle","Article","BlogPosting") for t in typ):
     for field in ("headline","articleBody","description"):
      if isinstance(node.get(field),str):out.append(node[field])
    if "@graph" in node:visit(node["@graph"],depth+1)
  for data in self.scripts[:15]:
   try:visit(json.loads(data))
   except (ValueError,TypeError):pass
  return out
def blank_hints(status,context):
 return {"date_candidates":[],"phase_hint":"unknown","date_context":context,
         "body_status":status,"period_candidates":[],"character_candidates":[]}
def page_hints(url):
 try:
  request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; GachaWars/1.0)"})
  with urllib.request.urlopen(request,timeout=10) as response:body=response.read(450000).decode("utf-8","replace")
  parser=ArticleText();parser.feed(body)
  structured=StructuredArticle();structured.feed(body)
  main=" ".join(parser.parts)
  full=" ".join(parser.body)
  rich=" ".join(structured.texts())
  path=urlparse(url).path.rstrip("/")
  listing=path.endswith("/news") or path.endswith("/index.html") or path=="/"
  if listing:return blank_hints("listing","ニュース一覧は本文解析対象外")
  if len(rich)>=80:text=rich;context="構造化された記事本文"
  elif len(main)>=80:text=main;context="main/article の本文"
  elif len(full)>=200:text=full;context="記事ページの表示テキスト（要確認）"
  else:return blank_hints("unavailable","本文未取得（JavaScript表示の可能性）")
  output=article_details(text[:18000])
  output["date_candidates"]=[]
  for period in output["period_candidates"]:
   for raw in (period["start_raw"],period["end_raw"]):
    found=DATE_RE.search(raw)
    if found:
     year,month,day=found.groups()
     normalized=f"{year}-{int(month):02d}-{int(day):02d}"
     try:datetime.fromisoformat(normalized)
     except ValueError:continue
     if normalized not in output["date_candidates"]:output["date_candidates"].append(normalized)
  output["date_candidates"]=output["date_candidates"][:8]
  output["phase_hint"]=hints(" ".join(parser.title)+text[:1000])["phase_hint"]
  output["date_context"]=context+"（開催日未確定）"
  output["body_status"]="extracted"
  return output
 except Exception as error:
  result=blank_hints("error","本文取得失敗")
  result["body_error"]=str(error)[:100]
  return result

# A headless browser is used only when static HTML lacks article content.
# Browser-rendered text is still an unverified extraction, never a confirmed release.
_browser=None
_browser_driver=None
def rendered_hints(url):
 global _browser,_browser_driver
 try:
  from playwright.sync_api import sync_playwright
  if _browser is None:
   _browser_driver=sync_playwright().start()
   _browser=_browser_driver.chromium.launch(headless=True,args=["--no-sandbox"])
  page=_browser.new_page(locale="ja-JP")
  try:
   page.goto(url,wait_until="domcontentloaded",timeout=18000)
   page.wait_for_timeout(1400)
   path=urlparse(url).path.rstrip("/")
   if path.endswith("/news") or path.endswith("/index.html") or not path:
    return blank_hints("listing","ニュース一覧は本文解析対象外")
   text=page.locator("main, article").all_text_contents()
   joined=" ".join(text)
   if len(joined)<80:joined=page.locator("body").inner_text(timeout=5000)
   if len(joined)<180:return blank_hints("unavailable","ブラウザ表示後も本文未取得")
   output=article_details(joined[:18000])
   output["phase_hint"]=hints(joined[:1000])["phase_hint"]
   output["date_candidates"]=[]
   for period in output["period_candidates"]:
    for raw in (period["start_raw"],period["end_raw"]):
     match=DATE_RE.search(raw)
     if match:
      year,month,day=match.groups()
      day_text=f"{year}-{int(month):02d}-{int(day):02d}"
      try:datetime.fromisoformat(day_text)
      except ValueError:continue
      if day_text not in output["date_candidates"]:output["date_candidates"].append(day_text)
   output["body_status"]="rendered"
   output["date_context"]="ブラウザ表示テキスト（内容未検証）"
   return output
  finally:page.close()
 except Exception as err:
  result=blank_hints("render_error","ブラウザ本文抽出失敗")
  result["body_error"]=str(err)[:140]
  return result
def close_browser():
 global _browser,_browser_driver
 if _browser:_browser.close();_browser=None
 if _browser_driver:_browser_driver.stop();_browser_driver=None

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
  discovered_count=len(matched)
  for title,link in SEEDS.get(game,[]):
   if not any(item["url"]==link for item in matched):matched.append({"game":game,"title":title,"url":link,"detected_at":now,"verification":"unreviewed",**hints(title)})
  collected[game]=list({x["url"]:x for x in matched}.values())[:80]
  for item in collected[game][:8]:
   detail=page_hints(item["url"])
   if detail.get("body_status")=="unavailable":detail=rendered_hints(item["url"])
   item["date_candidates"]=detail["date_candidates"][:8]
   item["date_context"]=detail.get("date_context","本文未取得")
   item["body_status"]=detail.get("body_status","unavailable")
   item.pop("body_error",None)
   if detail.get("body_error"):item["body_error"]=detail["body_error"]
   item["period_candidates"]=detail.get("period_candidates",[])
   item["character_candidates"]=detail.get("character_candidates",[])
   if item["phase_hint"]=="unknown":item["phase_hint"]=detail["phase_hint"]
  out[game]={"ok":True,"body_rendered":sum(x.get("body_status")=="rendered" for x in collected[game]),"body_errors":sum(x.get("body_status") in ("error","render_error") for x in collected[game]),"body_parsed":sum(x.get("body_status") in ("extracted","rendered") for x in collected[game]),"links_found":len(collected[game]),"index_links_found":discovered_count,"seed_links":max(0,len(collected[game])-discovered_count),"checked_at":now}
 except Exception as exc:
  collected[game]=[]
  out[game]={"ok":False,"error":str(exc)[:120],"checked_at":now}
seen={}
for x in history:
 if not isinstance(x,dict) or x.get("game") not in SOURCES or not isinstance(x.get("url"),str) or not x["url"].startswith("https://"):continue
 path=urlparse(x["url"]).path.rstrip("/")
 if path.endswith("/news") or path.endswith("/index.html") or not path:continue
 seen[(x["game"],x["url"])]=x
for items in collected.values():
 for x in items:
  merged=dict(seen.get((x["game"],x["url"]),{}),**x)
  if x.get("body_status") not in ("error","render_error"):merged.pop("body_error",None)
  seen[(x["game"],x["url"])]=merged
records=sorted(seen.values(),key=lambda x:x.get("detected_at",""),reverse=True)[:400]
close_browser()
OUTPUT.write_text(json.dumps({"schema":"gacha-wars-release-candidates-v1","updated_at":now,"status":out,"candidates":records},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("Official announcement candidate links:",len(records),{k:v.get("links_found",0) for k,v in out.items()})
