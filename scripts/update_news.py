#!/usr/bin/env python3
"""KURO WATCH: focused collector.

Keep only:
1) Wuthering Waves / 鳴潮 leaks, rumors, datamines and test-server info.
2) Kuro Games' unannounced / in-development games and projects.

Ordinary Wuthering Waves guides, event recaps, hardware articles, videos, etc. are excluded.
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
HEADERS = {'User-Agent': 'KURO-WATCH/2.0 (personal focused news aggregator)'}

QUERIES = [
    ('リーク', '"Wuthering Waves" (leak OR leaked OR leaks OR rumor OR rumour OR datamine OR "test server") when:14d'),
    ('リーク', '鳴潮 (リーク OR 噂 OR 流出 OR 未実装 OR テストサーバー OR 先行情報) when:14d'),
    ('リーク', '鸣潮 (爆料 OR 内鬼 OR 泄露 OR 测试服 OR 未实装) when:14d'),
    ('新作', '"Kuro Games" ("new game" OR "new project" OR unannounced OR development OR recruiting OR hiring OR trademark) when:30d'),
    ('新作', '库洛游戏 (新游 OR 新作 OR 新项目 OR 未公开 OR 开发中 OR 招聘 OR 商标) when:30d'),
    ('新作', '庫洛遊戲 (新遊戲 OR 新作 OR 新專案 OR 未公開 OR 開發中 OR 招聘 OR 商標) when:30d'),
]

LEAK_RE = re.compile(
    r'(?i)(leak|leaked|leaks|rumou?r|datamin|test server|unconfirmed|'
    r'リーク|噂|流出|未実装|テストサーバー|先行情報|爆料|内鬼|泄露|测试服|未实装)'
)
WUWA_RE = re.compile(r'(?i)(wuthering\s*waves|鳴潮|鸣潮)')
KURO_RE = re.compile(r'(?i)(kuro\s*games|クロゲ|庫洛遊戲|库洛游戏)')
DEV_RE = re.compile(
    r'(?i)(new game|new project|unannounced|development|developing|recruit|hiring|trademark|'
    r'新作|新遊戲|新游戏|新游|新项目|新專案|未公開|未公开|開発中|开发中|招聘|商標|商标|project)'
)
VIDEO_SOURCE_RE = re.compile(r'(?i)(youtube|ニコニコ|tiktok|bilibili)')
GUIDE_RE = re.compile(
    r'(?i)(攻略|評価とおすすめ|おすすめパーティ|最強|tier|build|guide|武器|音骸|素材|育成|'
    r'イベント攻略|ガチャ|リセマラ|初心者|タブレット|スマホ|スマートフォン|pc benchmark)'
)
SPOILER_RE = re.compile(r'(?i)(spoiler|ネタバレ|劇透|剧透|leak|リーク|爆料|内鬼|泄露)')

def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()[:500]

def wanted(title, source, category):
    text = f'{title} {source}'
    if VIDEO_SOURCE_RE.search(source):
        return False
    if GUIDE_RE.search(title):
        return False
    if category == 'リーク':
        return bool(WUWA_RE.search(text) and LEAK_RE.search(text))
    if category == '新作':
        return bool(KURO_RE.search(text) and DEV_RE.search(text))
    return False

def collect_from_xml(xml_bytes, category):
    root = ET.fromstring(xml_bytes)
    now = dt.datetime.now(dt.timezone.utc)
    items = []
    for item in root.findall('./channel/item'):
        title = clean(item.findtext('title'))
        source = clean(item.findtext('source'))
        link = (item.findtext('link') or '').strip()
        if not title or not link.startswith('https://') or not wanted(title, source, category):
            continue
        try:
            when = email.utils.parsedate_to_datetime(item.findtext('pubDate')).astimezone(dt.timezone.utc)
        except Exception:
            continue
        max_age = 16 if category == 'リーク' else 35
        if not (now - dt.timedelta(days=max_age) <= when <= now + dt.timedelta(days=1)):
            continue
        summary = (
            (f'配信元: {source}。' if source else '')
            + ('鳴潮のリーク・噂・先行情報として検出。未確認情報なので内容は出典先で確認してください。'
               if category == 'リーク'
               else 'クロゲの新作・未発表/開発中プロジェクト関連として検出。内容は出典先で確認してください。')
        )
        items.append({
            'id': 'rss-' + hashlib.sha256((title + '|' + source).encode()).hexdigest()[:18],
            'date': when.date().isoformat(),
            'category': category,
            'status': '未確認' if category == 'リーク' else '報道',
            'lang': 'MIX',
            'title': title,
            'summary': summary,
            'url': link,
            'spoiler': bool(SPOILER_RE.search(title)),
            'source': source,
        })
    return items

def keep_old(x):
    if not isinstance(x, dict) or 'id' not in x:
        return False
    return wanted(clean(x.get('title')), clean(x.get('source')), x.get('category'))

def main():
    try:
        old = json.loads(OUT.read_text('utf-8')) if OUT.exists() else []
        if not isinstance(old, list):
            old = []
    except (ValueError, OSError):
        old = []

    items = {x['id']: x for x in old if keep_old(x)}
    success = 0
    for category, q in QUERIES:
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
            'q': q, 'hl': 'ja', 'gl': 'JP', 'ceid': 'JP:ja'
        })
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                fetched = collect_from_xml(r.read(1500000), category)
            success += 1
            for x in fetched:
                items[x['id']] = x
            print(category, len(fetched))
        except Exception as e:
            print('RSS read failed:', category, str(e))

    if success == 0:
        raise RuntimeError('Every feed failed; leaving archive intact')

    archive = sorted(items.values(), key=lambda x: (x.get('date', ''), x.get('id', '')), reverse=True)[:300]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Focused archive', len(archive))

if __name__ == '__main__':
    main()
