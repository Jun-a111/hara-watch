#!/usr/bin/env python3
"""Fetch Google News RSS and update a deduplicated public news archive.
No article from an aggregator is labeled as a verified official statement.
"""
import datetime as dt
import email.utils
import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'news.json'
QUERIES = [
    ('鳴潮', '"Wuthering Waves" OR "鳴潮" when:7d'),
    ('クロゲ', '"Kuro Games" OR "庫洛遊戲" when:7d'),
    ('新作', '"Kuro Games" game development OR new game when:7d'),
    ('中国ゲーム', '"中国ゲーム" OR "Chinese gacha games" when:7d'),
]
HEADERS = {'User-Agent':'KURO-WATCH/1.0 (personal news aggregator)'}
RUMOR_RE = re.compile(r'(?i)(leak|rumou?r|datamin|unconfirmed|リーク|噂|未確認|爆料|内鬼|流出)')
SPOILER_RE = re.compile(r'(?i)(spoiler|ネタバレ|劇透|泄露|leak|リーク|爆料|内鬼)')

def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()[:400]

def collect_from_xml(xml_bytes, category):
    root = ET.fromstring(xml_bytes)
    today = dt.datetime.now(dt.timezone.utc)
    items = []
    for item in root.findall('./channel/item'):
        title = clean(item.findtext('title'))
        link = (item.findtext('link') or '').strip()
        if not title or not link.startswith('https://'):
            continue
        pub = item.findtext('pubDate')
        try:
            when = email.utils.parsedate_to_datetime(pub).astimezone(dt.timezone.utc)
        except Exception:
            continue
        if not (today - dt.timedelta(days=10) <= when <= today + dt.timedelta(days=1)):
            continue
        source = clean(item.findtext('source'))
        is_rumor = bool(RUMOR_RE.search(title))
        summary = (f'配信元: {source}。' if source else '') + 'RSSで検出した記事です。内容・信頼性は出典先で確認してください。'
        items.append(dict(id='rss-'+hashlib.sha256((title+'|'+source).encode()).hexdigest()[:18],date=when.date().isoformat(),category='リーク' if is_rumor else category,status='未確認' if is_rumor else '報道',lang='MIX',title=title,summary=summary,url=link,spoiler=bool(SPOILER_RE.search(title)),source=source))
    return items

def main():
    try:
        old=json.loads(OUT.read_text('utf-8')) if OUT.exists() else []
        if not isinstance(old,list): old=[]
    except (ValueError,OSError):
        old=[]
    items = {x['id']:x for x in old if isinstance(x,dict) and 'id' in x and x.get('id','').startswith('rss-')}
    success=0
    for category,q in QUERIES:
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'ja','gl':'JP','ceid':'JP:ja'})
        try:
            req=urllib.request.Request(url,headers=HEADERS)
            with urllib.request.urlopen(req,timeout=20) as r:
                fetched=collect_from_xml(r.read(1500000),category)
            success+=1
            for x in fetched:items[x['id']]=x
            print(category, len(fetched))
        except Exception as e:
            print('RSS read failed:',category,str(e))
    if success==0:raise RuntimeError('Every feed failed; leaving archive intact')
    archive=sorted(items.values(),key=lambda x:(x['date'],x['id']),reverse=True)[:500]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(archive,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Total archive',len(archive))

if __name__=='__main__': main()
