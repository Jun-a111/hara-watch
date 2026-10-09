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
  ("特別スカウト「臨淵望北」","https://endfield.gryphline.com/ja-jp/news/2656"),
  ("「雪氷の幽夢」バージョンアップデートについて","https://endfield.gryphline.com/ja-jp/news/5208")
 ]
}
KEYWORDS=("ガチャ","集音","祈願","跳躍","チャンネル","ピックアップ","新キャラ","実装","アップデート","バージョン","version","banner","update","recruit","new character","convene","patch notes","featured resonator","event preview","活动","卡池","版本","更新")
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
 periods=[]
 seen=set()
 for pattern in (PERIOD_RE,DATE_PREFIX_RE):
  for m in pattern.finditer(text):
   start_raw,end_raw=m.group(1).strip(),m.group(2).strip()
   key=(start_raw,end_raw)
   if key in seen:continue
   seen.add(key)
   context=text[max(0,m.start()-110):min(len(text),m.end()+65)]
   nearby=text[max(0,m.start()-110):m.start()].lower()
   # The nearest preceding label is usually the event type, not the article title.
   cues={
    "maintenance":("メンテナンス実施日時","メンテナンス期間","メンテナンス","maintenance","downtime"),
    "banner_possible":("祈願期間","集音期間","集音開催期間","祈願開催期間","跳躍期間","跳躍開催期間","スカウト開催期間","スカウト期間","チャンネル開催期間","event wish duration","convene duration","warp duration","banner duration"),
    "other_event":("開催期間","開放期間","末日の幻影","虚構叙事","混沌の記憶","忘却の庭","simulated universe","event duration")
   }
   nearest=(-1,"unknown")
   for category,terms in cues.items():
    for term in terms:
     pos=nearby.rfind(term)
     if pos>nearest[0]:nearest=(pos,category)
   classification=nearest[1]
   # Regional server schedules may share one preceding maintenance heading.
   if classification=="unknown" and ("サーバー：" in nearby or "server:" in nearby) and "メンテナンス" in text[max(0,m.start()-230):m.start()].lower():
    classification="maintenance"
   if re.search(r"(?:集音|祈願|跳躍|スカウト).{0,4}開催期間[：:\\s〓]*$",nearby):classification="banner_possible"
   periods.append({"raw":m.group(0)[:110].strip(),"start_raw":start_raw,"end_raw":end_raw,"classification":classification,"context_excerpt":context[:190]})
 periods=periods[:5]
 characters=[]
 for clue in CHARACTER_CONTEXT:
  for match in re.finditer(re.escape(clue),text):
   excerpt=text[match.end():match.end()+65]
   for name in QUOTED_NAME.findall(excerpt):
    if any(word in name for word in NON_CHARACTER) or re.search(r"\d{4}|Ver\.|版本",name,re.I):continue
    if name not in characters:characters.append(name)
 return {"period_candidates":periods,"character_candidates":characters[:12],"extraction_note":"本文周辺の語から期間用途を暫定分類。未検証のため戦績へ自動登録しません"}
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

def json_news_items(value,depth=0):
 """Discover title/URL pairs from official news API responses, never invent links."""
 if depth>7:return []
 if isinstance(value,list):
  items=[]
  for part in value[:120]:items.extend(json_news_items(part,depth+1))
  return items
 if not isinstance(value,dict):return []
 title=next((value[k] for k in ("title","newsTitle","articleTitle","headline","name") if isinstance(value.get(k),str) and len(value[k])>5),None)
 url=next((value[k] for k in ("url","link","href","newsUrl","articleUrl") if isinstance(value.get(k),str)),None)
 out=[(title,url)] if title and url else []
 for key,v in value.items():
  if isinstance(v,(dict,list)) and key not in ("translations","locale","locales"):out.extend(json_news_items(v,depth+1))
 return out

def wuthering_steam_announcements():
 """Discover game-specific announcements from Steam API and public official announcements page."""
 endpoint="https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=3513350&count=60&maxlength=0&format=json"
 found=[]
 errors=[]
 diag={"api_items":0,"bad_url":0,"bad_host":0,"non_news_path":0,"other_game":0,"bad_title":0,"matched":0,"html_links":0,"html_matched":0,"sample_hosts":[],"sample_paths":[],"sample_titles":[]}
 try:
  req=urllib.request.Request(endpoint,headers={"User-Agent":"GachaWars/1.0"})
  with urllib.request.urlopen(req,timeout=14) as response:data=json.load(response)
  news=data.get("appnews",{}).get("newsitems",[])
  diag["api_items"]=len(news)
  for item in news:
   title=item.get("title","")
   link=item.get("url","")
   if not isinstance(title,str) or not isinstance(link,str):
    diag["bad_url"]+=1
    continue
   if len(diag["sample_titles"])<5:diag["sample_titles"].append(title[:100])
   parsed=urlparse(link)
   if len(diag["sample_paths"])<6:diag["sample_paths"].append(parsed.path[:120])
   if parsed.scheme!="https" or parsed.hostname not in ("store.steampowered.com","steamcommunity.com","steamstore-a.akamaihd.net","wutheringwaves.kurogames.com"):
    diag["bad_host"]+=1
    if len(diag["sample_hosts"])<6:diag["sample_hosts"].append(parsed.hostname or "")
    continue
   if parsed.hostname=="steamstore-a.akamaihd.net" and not parsed.path.startswith("/news/"):
    diag["non_news_path"]+=1
    continue
   if parsed.hostname=="store.steampowered.com" and "/news/" not in parsed.path:
    diag["non_news_path"]+=1
    continue
   if parsed.hostname=="steamcommunity.com" and not ("/games/3513350/" in parsed.path or "/app/3513350/" in parsed.path):
    diag["other_game"]+=1
    continue
   if not any(keyword in title.lower() for keyword in KEYWORDS):
    diag["bad_title"]+=1
    continue
   found.append((title[:180],link))
   diag["matched"]+=1
 except Exception as error:errors.append("api: "+str(error)[:100])
 if not found:
  try:
   page_url="https://steamcommunity.com/app/3513350/announcements/?l=japanese"
   req=urllib.request.Request(page_url,headers={"User-Agent":"Mozilla/5.0"})
   with urllib.request.urlopen(req,timeout=14) as response:html=response.read(1300000).decode("utf-8","replace")
   parser=Links();parser.feed(html)
   diag["html_links"]=len(parser.items)
   for href,title in parser.items:
    link=urljoin(page_url,href)
    parsed=urlparse(link)
    if parsed.hostname not in ("steamcommunity.com","store.steampowered.com"):continue
    if not ("/announcements/detail/" in parsed.path or "/news/app/3513350/" in parsed.path):continue
    title=" ".join(title.split())[:180]
    if title and any(keyword in title.lower() for keyword in KEYWORDS):
     found.append((title,link))
     diag["html_matched"]+=1
  except Exception as error:errors.append("html: "+str(error)[:100])
 unique=[]
 seen_titles=set()
 for title,link in found:
  normalized=" ".join(title.casefold().split())
  if normalized in seen_titles:continue
  seen_titles.add(normalized)
  unique.append((title,link))
 diag["duplicate_titles"]=len(found)-len(unique)
 return unique[:25],"; ".join(errors),diag

def endfield_news_items(value,depth=0):
 """Extract Endfield title/cid identifiers, keeping URLs provisional until verified."""
 if depth>7:return []
 if isinstance(value,list):
  out=[]
  for item in value[:100]:out.extend(endfield_news_items(item,depth+1))
  return out
 if not isinstance(value,dict):return []
 out=[]
 title=value.get("title")
 cid=value.get("cid")
 if isinstance(title,str) and len(title)>5 and isinstance(cid,(int,str)) and str(cid).isdigit():
  out.append((title,"https://endfield.gryphline.com/ja-jp/news/"+str(cid)))
 for child in value.values():
  if isinstance(child,(dict,list)):out.extend(endfield_news_items(child,depth+1))
 return out

def verify_endfield_url(url):
 """Only allow constructed Endfield URLs that resolve to an actual article."""
 parsed=urlparse(url)
 if parsed.hostname!="endfield.gryphline.com" or not re.fullmatch(r"/ja-jp/news/[0-9]+",parsed.path):return False
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
  with urllib.request.urlopen(req,timeout=8) as response:
   return response.status==200 and len(response.read(50000))>800
 except Exception:return False

def json_news_structure(value,depth=0):
 """Inspect JSON object shapes without recording API payload values."""
 if depth>5:return []
 if isinstance(value,list):
  shapes=[]
  for x in value[:8]:shapes.extend(json_news_structure(x,depth+1))
  return shapes[:20]
 if not isinstance(value,dict):return []
 keys=sorted(str(k)[:40] for k in value.keys())[:24]
 shapes=[keys] if any(k.lower() in ("title","newstitle","id","articleid","newsid","link","url","list","data","items","records") for k in keys) else []
 for val in value.values():
  if isinstance(val,(dict,list)):shapes.extend(json_news_structure(val,depth+1))
  if len(shapes)>=20:break
 return shapes[:20]

def browser_news_links(game,url):
 """Read news-list anchors after client-side rendering, not announcement text."""
 global _browser,_browser_driver
 try:
  from playwright.sync_api import sync_playwright
  if _browser is None:
   _browser_driver=sync_playwright().start()
   _browser=_browser_driver.chromium.launch(headless=True,args=["--no-sandbox"])
  page=_browser.new_page(locale="ja-JP")
  try:
   api_items=[]
   responses=[]
   diagnostics={"api_json":0,"api_pairs":0,"dom_anchors":0,"filtered":0,"json_responses_seen":0,"api_shapes":[]}
   def collect_response(response):
    try:
     if len(responses)>=90:return
     if "json" not in response.headers.get("content-type","").lower():return
     host=urlparse(response.url).hostname or ""
     trusted=host==(urlparse(url).hostname or "") or (game=="ww" and host.endswith(".kurogames.com")) or (game=="end" and host.endswith(".gryphline.com"))
     if trusted:responses.append(response)
    except Exception:pass
   page.on("response",collect_response)
   page.goto(url,wait_until="domcontentloaded",timeout=20000)
   page.wait_for_timeout(2600)
   diagnostics["json_responses_seen"]=len(responses)
   for response in responses:
    try:
     size=response.headers.get("content-length","")
     if size.isdigit() and int(size)>1500000:continue
     payload=response.json()
     if game=="end" and len(diagnostics["api_shapes"])<12:
      diagnostics["api_shapes"].extend(json_news_structure(payload)[:12-len(diagnostics["api_shapes"])])
     diagnostics["api_json"]+=1
     found=json_news_items(payload)[:80]
     if game=="end":
      proposed=endfield_news_items(payload)[:12]
      diagnostics["endfield_cid_pairs"]=diagnostics.get("endfield_cid_pairs",0)+len(proposed)
      found.extend((title,link) for title,link in proposed if verify_endfield_url(link))
     diagnostics["api_pairs"]+=len(found)
     api_items.extend(found)
    except Exception:continue
   links=page.locator("a[href]").evaluate_all("(nodes) => nodes.map(a => ({href:a.href,title:(a.innerText||a.textContent||a.getAttribute('aria-label')||a.parentElement?.innerText||'').trim()})).slice(0,1200)")
   diagnostics["api_pairs"]=len(api_items)
   diagnostics["dom_anchors"]=len(links)
   home=urlparse(url).hostname or ""
   matched=[]
   for x in links+ [{"href":urljoin(url,href),"title":title} for title,href in api_items]:
    link=str(x.get("href",""));title=" ".join(str(x.get("title","")).split())[:180]
    parsed=urlparse(link)
    if parsed.scheme!="https" or not parsed.hostname or not (parsed.hostname==home or parsed.hostname.endswith("."+home)):continue
    path=parsed.path.rstrip("/")
    if not path or path.endswith("/news") or path.endswith("/index.html"):continue
    if not ("/news/" in path or "/article/" in path):continue
    if not title or len(title)>180 or not any(k in title.lower() for k in KEYWORDS):continue
    matched.append((title,link))
   diagnostics["filtered"]=len(matched)
   diagnostics["rejected"]=max(0,len(links)+len(api_items)-len(matched))
   # News cards on Endfield's index expose article titles as clickable text
   # but may not have anchor hrefs. Click precise headings, never arbitrary divs.
   if game=="end" and not matched:
    cards=page.locator("body").inner_text(timeout=4000)
    titles=[]
    for line in cards.splitlines():
     title=" ".join(line.split())
     if 8<=len(title)<=110 and any(k in title.lower() for k in KEYWORDS) and title not in titles:
      titles.append(title)
    diagnostics["clickable_titles"]=len(titles)
    diagnostics["clicked_routes"]=0
    for title in titles[:16]:
     try:
      node=page.get_by_text(title,exact=True).first
      if node.count()!=1:continue
      before=page.url
      node.click(timeout=1000)
      page.wait_for_timeout(300)
      dest=page.url
      if dest==before:
       try:
        clickable=node.locator("xpath=ancestor::*[@role='button' or @onclick or contains(@class,'cursor')][1]")
        if clickable.count():
         clickable.click(timeout=1000)
         page.wait_for_timeout(350)
         dest=page.url
       except Exception:pass
      parsed=urlparse(dest)
      if dest!=before and parsed.hostname==home and re.search(r"/news/[^/]+$",parsed.path):
       matched.append((title,dest))
       diagnostics["clicked_routes"]+=1
      if dest!=before:page.goto(url,wait_until="domcontentloaded",timeout=15000)
     except Exception:continue
   return list(dict.fromkeys(matched))[:50],"ok",diagnostics
  finally:page.close()
 except Exception as err:return [],str(err)[:120],{}

def save_candidates(payload):
 """Write atomically and validate before replacing the last usable candidate file."""
 content=json.dumps(payload,ensure_ascii=False,indent=2)+"\n"
 decoded=json.loads(content)
 if decoded.get("schema")!="gacha-wars-release-candidates-v1" or not isinstance(decoded.get("candidates"),list):
  raise ValueError("Invalid official news candidate data")
 temp=OUTPUT.with_suffix(".json.tmp")
 temp.write_text(content,encoding="utf-8")
 temp.replace(OUTPUT)

now=datetime.now(timezone.utc).isoformat(timespec="seconds")
try:
 previous=json.loads(OUTPUT.read_text(encoding="utf-8"))
 history=previous.get("candidates",[])
except (OSError,ValueError):history=[]
out={}
collected={}
for game in ("ww","end","gi","hsr","zzz","nte"):
 url=SOURCES[game]
 out[game]={"ok":False,"in_progress":True,"checked_at":now,"stage":"starting"}
 pending={(x["game"],x["url"]):x for x in history if isinstance(x,dict) and x.get("game") in SOURCES and isinstance(x.get("url"),str) and x["url"].startswith("https://")}
 for group in collected.values():
  for item in group:pending[(item["game"],item["url"])]=dict(pending.get((item["game"],item["url"]),{}),**item)
 save_candidates({"schema":"gacha-wars-release-candidates-v1","updated_at":now,"collection_partial":True,"status":out,"candidates":list(pending.values())[:400]})
 print("Starting official news discovery:",game,flush=True)
 try:
  html=""
  static_error=""
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; GachaWars/1.0)"})
   with urllib.request.urlopen(req,timeout=12) as res:html=res.read(1200000).decode("utf-8","replace")
  except Exception as err:static_error=str(err)[:120]
  parser=Links();parser.feed(html)
  matched=[]
  home=urlparse(url).hostname or ""
  for href,title in parser.items:
   link=urljoin(url,href);domain=urlparse(link).hostname or ""
   if not (domain==home or domain.endswith("."+home)):continue
   if not title or len(title)>180 or not any(k in title.lower() for k in KEYWORDS):continue
   if not link.startswith("https://"):continue
   matched.append({"game":game,"title":title[:180],"url":link,"detected_at":now,"verification":"unreviewed",**hints(title)})
  static_found=len(matched)
  browser_found=0
  browser_error=""
  browser_links,browser_error,browser_diag=browser_news_links(game,url)
  if game=="ww" and not browser_links:
   english_url="https://wutheringwaves.kurogames.com/m/en/main/news"
   extra_links,extra_error,extra_diag=browser_news_links(game,english_url)
   browser_diag["english_mobile_fallback"]=extra_diag
   browser_diag["english_mobile_error"]=extra_error[:160]
   browser_links.extend(extra_links)
   if not browser_links:
    steam_links,steam_error,steam_diag=wuthering_steam_announcements()
    browser_diag["steam_fallback_diagnostics"]=steam_diag
    browser_diag["steam_fallback_found"]=len(steam_links)
    browser_diag["steam_fallback_error"]=steam_error
    browser_links.extend(steam_links)
  for title,link in browser_links:
   if not any(x["url"]==link for x in matched):
    matched.append({"game":game,"title":title,"url":link,"detected_at":now,"verification":"unreviewed",**hints(title)})
    browser_found+=1
  discovered_count=len(matched)
  for title,link in SEEDS.get(game,[]):
   if not any(item["url"]==link for item in matched):matched.append({"game":game,"title":title,"url":link,"detected_at":now,"verification":"unreviewed",**hints(title)})
  collected[game]=list({x["url"]:x for x in matched}.values())[:80]
  # Prioritize newly discovered links for body analysis, while preserving seeded fallback.
  discovered_urls={x["url"] for x in matched[:discovered_count]}
  cache={x.get("url"):x for x in history if isinstance(x,dict) and x.get("game")==game}
  # Reprocess older period-bearing announcements first when extraction rules change.
  # This also prevents newly discovered Steam news from starving old verified body parses.
  def selection_priority(item):
   prior=cache.get(item["url"],{})
   stale=prior.get("extraction_version")!=3 and prior.get("body_status") in ("rendered","extracted")
   has_periods=bool(prior.get("period_candidates"))
   return (not (stale and has_periods),not stale,item["url"] not in discovered_urls)
  selected=sorted(collected[game],key=selection_priority)[:12]
  for item in selected:
   previous=cache.get(item["url"],{})
   # Keep context-backed classifications if a refreshed extraction has no stronger result.
   previous_periods={(p.get("start_raw"),p.get("end_raw")):p for p in previous.get("period_candidates",[]) if isinstance(p,dict)}
   def preserve_period_classification(periods):
    for period in periods:
     old=previous_periods.get((period.get("start_raw"),period.get("end_raw")))
     if old and old.get("classification_source")=="stored_context_reclassified" and period.get("classification","unknown")=="unknown":
      period["classification"]=old["classification"]
      period["classification_source"]=old["classification_source"]
    return periods
   if previous.get("extraction_version")==3 and previous.get("body_status") in ("rendered","extracted") and isinstance(previous.get("period_candidates"),list) and isinstance(previous.get("character_candidates"),list):
    for field in ("date_candidates","date_context","body_status","period_candidates","character_candidates","extraction_version"):
     if field in previous:item[field]=previous[field]
    if item["phase_hint"]=="unknown":item["phase_hint"]=previous.get("phase_hint","unknown")
    continue
   detail=page_hints(item["url"])
   if detail.get("body_status")=="unavailable":detail=rendered_hints(item["url"])
   if detail.get("body_status") not in ("rendered","extracted") and previous.get("body_status") in ("rendered","extracted"):
    # A temporary fetch failure must not erase a previously successful parse.
    for field in ("date_candidates","date_context","body_status","period_candidates","character_candidates","extraction_version"):
     if field in previous:item[field]=previous[field]
    item["refresh_error"]=detail.get("body_error") or detail.get("date_context","再取得失敗")
    continue
   item.pop("refresh_error",None)
   item["date_candidates"]=detail["date_candidates"][:8]
   item["date_context"]=detail.get("date_context","本文未取得")
   item["body_status"]=detail.get("body_status","unavailable")
   item.pop("body_error",None)
   if detail.get("body_error"):item["body_error"]=detail["body_error"]
   item["period_candidates"]=preserve_period_classification(detail.get("period_candidates",[]))
   item["character_candidates"]=detail.get("character_candidates",[])
   if item["body_status"] in ("rendered","extracted"):item["extraction_version"]=3
   if item["phase_hint"]=="unknown":item["phase_hint"]=detail["phase_hint"]
  out[game]={"ok":True,"body_cached":sum(x.get("url") in cache and x.get("body_status") in ("rendered","extracted") for x in collected[game]),"body_rendered":sum(x.get("body_status")=="rendered" for x in collected[game]),"body_errors":sum(x.get("body_status") in ("error","render_error") for x in collected[game]),"body_parsed":sum(x.get("body_status") in ("extracted","rendered") for x in collected[game]),"links_found":len(collected[game]),"index_links_found":static_found,"static_index_error":static_error,"browser_links_found":browser_found,"browser_index_error":browser_error if browser_error!="ok" else "","browser_diagnostics":browser_diag,"seed_links":max(0,len(collected[game])-discovered_count),"checked_at":now}
 except Exception as exc:
  collected[game]=[]
  out[game]={"ok":False,"error":str(exc)[:120],"checked_at":now}
 # Save a checkpoint after each game so a slow later site cannot erase all diagnostics.
 partial={(x["game"],x["url"]):x for x in history if isinstance(x,dict) and x.get("game") in SOURCES and isinstance(x.get("url"),str) and x["url"].startswith("https://")}
 for group in collected.values():
  for item in group:partial[(item["game"],item["url"])]=dict(partial.get((item["game"],item["url"]),{}),**item)
 save_candidates({"schema":"gacha-wars-release-candidates-v1","updated_at":now,"collection_partial":len(out)<len(SOURCES),"status":out,"candidates":list(partial.values())[:400]})
 print("Checkpoint",game,"browser",out[game].get("browser_links_found"),"diag",out[game].get("browser_diagnostics"),"error",out[game].get("error"),flush=True)
seen={}
for x in history:
 if not isinstance(x,dict) or x.get("game") not in SOURCES or not isinstance(x.get("url"),str) or not x["url"].startswith("https://"):continue
 path=urlparse(x["url"]).path.rstrip("/")
 if path.endswith("/news") or path.endswith("/index.html") or not path:continue
 seen[(x["game"],x["url"])]=x
for items in collected.values():
 for x in items:
  old_record=seen.get((x["game"],x["url"]),{})
  merged=dict(old_record,**x)
  # Discovery-only records have no article body: do not overwrite earlier parsed details.
  if "body_status" not in x and old_record.get("body_status") in ("rendered","extracted"):
   for field in ("date_candidates","date_context","body_status","period_candidates","character_candidates","extraction_version","phase_hint"):
    if field in old_record:merged[field]=old_record[field]
  if x.get("body_status") not in ("error","render_error"):merged.pop("body_error",None)
  seen[(x["game"],x["url"])]=merged
# Collapse duplicate Steam announcements with identical titles, preserving the newest entry.
steam_seen=set()
deduplicated=[]
for record in sorted(seen.values(),key=lambda x:x.get("detected_at",""),reverse=True):
 if record.get("game")=="ww" and urlparse(record.get("url","")).hostname=="steamstore-a.akamaihd.net":
  key=" ".join(str(record.get("title","")).casefold().split())
  if key in steam_seen:continue
  steam_seen.add(key)
 deduplicated.append(record)
records=deduplicated[:400]
close_browser()
save_candidates({"schema":"gacha-wars-release-candidates-v1","updated_at":now,"status":out,"candidates":records})
print("Official announcement candidate links:",len(records),{k:v.get("links_found",0) for k,v in out.items()})
