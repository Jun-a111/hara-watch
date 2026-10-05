#!/usr/bin/env python3
"""Fetch Google News RSS and keep a cleaner, deduplicated KURO WATCH archive.

Goals:
- Prefer Wuthering Waves / Kuro Games / closely related Chinese-game coverage.
- Drop obvious false positives and generic gadget/news articles.
- De-prioritize video-only sources.
- Keep rumor/leak coverage clearly separated from reporting.
- Re-filter the existing RSS archive on every run so old noise is removed.
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
    ('鳴潮', '"Wuthering Waves" OR "鳴潮" OR "鸣潮" when:7d'),
    ('クロゲ', '"Kuro Games" OR "KURO GAMES" OR "庫洛遊戲" OR "库洛游戏" when:7d'),
    ('新作', '("Kuro Games" OR "KURO GAMES" OR 庫洛遊戲 OR 库洛游戏) (new game OR 新作 OR 新游 OR 開発) when:14d'),
    ('中国ゲーム', '("Chinese gacha" OR "中国ゲーム" OR "中国ソシャゲ") (Wuthering Waves OR Kuro OR 原神 OR Genshin OR Endfield OR NTE) when:7d'),
]

HEADERS = {'User-Agent': 'KURO-WATCH/1.1 (personal news aggregator)'}

RUMOR_RE = re.compile(r'(?i)(leak|rumou?r|datamin|unconfirmed|リーク|噂|未確認|爆料|内鬼|流出|测试服|test server)')
SPOILER_RE = re.compile(r'(?i)(spoiler|ネタバレ|劇透|剧透|leak|リーク|爆料|内鬼)')

WUWA_RE = re.compile(r'(?i)(wuthering\s*waves|鳴潮|鸣潮)')
KURO_RE = re.compile(r'(?i)(kuro\s*games|庫洛遊戲|库洛游戏|クロゲ)')
CHINA_GAME_RE = re.compile(
    r'(?i)(genshin|原神|honkai|崩壊|崩坏|zenless|ゼンゼロ|绝区零|endfield|エンドフィールド|'
    r'neverness|\bnte\b|明日方舟|アークナイツ|girls.? frontline|少女前線|少女前线|'
    r'punishing.?gray.?raven|パニグレ|战双|gacha|ソシャゲ|手游)'
)

# Obvious unrelated verticals that frequently appear as search false positives.
NOISE_RE = re.compile(
    r'(?i)(タブレット|tablet|スマートフォン|smartphone|イヤホン|headphone|ノートPC|laptop|'
    r'CPU|GPU|Snapdragon|MediaTek|セール|クーポン|Amazon.*タイムセール|家電|自動車|car review)'
)

VIDEO_SOURCE_RE = re.compile(r'(?i)(youtube|ニコニコ|tiktok|bilibili)')
OFFICIAL_SOURCE_RE = re.compile(r'(?i)(wuthering\s*waves|kuro\s*games|鳴潮公式|鸣潮官方|庫洛遊戲|库洛游戏)')

MAJOR_SOURCES = (
    '4Gamer', 'Game8', 'ファミ通', '電撃オンライン', 'AUTOMATON', 'IGN', 'GameSpot',
    'Polygon', 'PC Gamer', 'Eurogamer', 'GamesRadar', 'Gematsu', 'Siliconera',
    'RPG Site', 'TheGamer', 'GameWith', 'インサイド', 'Game*Spark'
)


def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()[:400]


def relevance_score(title, source, category):
    text = f'{title} {source}'
    score = 0

    if WUWA_RE.search(text):
        score += 8
    if KURO_RE.search(text):
        score += 7
    if CHINA_GAME_RE.search(text):
        score += 3

    if category == '鳴潮' and WUWA_RE.search(text):
        score += 5
    elif category in ('クロゲ', '新作') and KURO_RE.search(text):
        score += 5
    elif category == '中国ゲーム' and (WUWA_RE.search(text) or KURO_RE.search(text) or CHINA_GAME_RE.search(text)):
        score += 2

    if OFFICIAL_SOURCE_RE.search(source):
        score += 5
    if any(name.lower() in source.lower() for name in MAJOR_SOURCES):
        score += 2

    if VIDEO_SOURCE_RE.search(source):
        score -= 4
    if NOISE_RE.search(title) and not (WUWA_RE.search(title) or KURO_RE.search(title)):
        score -= 10

    return score


def is_relevant(title, source, category):
    text = f'{title} {source}'

    # Core feeds must actually mention the subject. This is the main false-positive filter.
    if category == '鳴潮':
        return bool(WUWA_RE.search(text)) and relevance_score(title, source, category) >= 8
    if category in ('クロゲ', '新作'):
        return bool(KURO_RE.search(text)) and relevance_score(title, source, category) >= 7

    # Broad Chinese-game feed is allowed only if it mentions a known game/category term.
    return bool(WUWA_RE.search(text) or KURO_RE.search(text) or CHINA_GAME_RE.search(text)) and relevance_score(title, source, category) >= 3


def collect_from_xml(xml_bytes, category):
    root = ET.fromstring(xml_bytes)
    now = dt.datetime.now(dt.timezone.utc)
    items = []

    for item in root.findall('./channel/item'):
        title = clean(item.findtext('title'))
        link = (item.findtext('link') or '').strip()
        source = clean(item.findtext('source'))

        if not title or not link.startswith('https://'):
            continue

        pub = item.findtext('pubDate')
        try:
            when = email.utils.parsedate_to_datetime(pub).astimezone(dt.timezone.utc)
        except Exception:
            continue

        if not (now - dt.timedelta(days=16) <= when <= now + dt.timedelta(days=1)):
            continue
        if not is_relevant(title, source, category):
            continue

        is_rumor = bool(RUMOR_RE.search(title))
        priority = relevance_score(title, source, category)

        # Google News RSS is an aggregator, so do not claim "official" unless the
        # publisher name itself is recognizably an official KURO/Wuwa source.
        if is_rumor:
            status = '未確認'
            out_category = 'リーク'
        elif OFFICIAL_SOURCE_RE.search(source):
            status = '公式'
            out_category = category
            priority += 4
        else:
            status = '報道'
            out_category = category

        summary = (f'配信元: {source}。' if source else '') + 'RSSで検出した記事です。内容・信頼性は出典先で確認してください。'

        items.append(dict(
            id='rss-' + hashlib.sha256((title + '|' + source).encode()).hexdigest()[:18],
            date=when.date().isoformat(),
            category=out_category,
            status=status,
            lang='MIX',
            title=title,
            summary=summary,
            url=link,
            spoiler=bool(SPOILER_RE.search(title)),
            source=source,
            priority=priority,
        ))

    return items


def keep_old_item(x):
    if not isinstance(x, dict) or 'id' not in x:
        return False

    # Preserve hand-written/seeded items untouched.
    if not x.get('id', '').startswith('rss-'):
        return True

    title = clean(x.get('title'))
    source = clean(x.get('source'))
    category = x.get('category', '中国ゲーム')
    if category == 'リーク':
        # Infer the original subject for old leak items.
        if WUWA_RE.search(f'{title} {source}'):
            category = '鳴潮'
        elif KURO_RE.search(f'{title} {source}'):
            category = 'クロゲ'
        else:
            category = '中国ゲーム'

    return is_relevant(title, source, category)


def main():
    try:
        old = json.loads(OUT.read_text('utf-8')) if OUT.exists() else []
        if not isinstance(old, list):
            old = []
    except (ValueError, OSError):
        old = []

    # Re-filter old RSS items so previous junk disappears after the first run.
    items = {}
    for x in old:
        if not keep_old_item(x):
            continue
        if x.get('id', '').startswith('rss-'):
            x['priority'] = relevance_score(clean(x.get('title')), clean(x.get('source')), x.get('category', '中国ゲーム'))
        items[x['id']] = x

    success = 0
    for category, q in QUERIES:
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
            'q': q,
            'hl': 'ja',
            'gl': 'JP',
            'ceid': 'JP:ja',
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

    # Same-day articles are ordered by relevance, then a stable id.
    archive = sorted(
        items.values(),
        key=lambda x: (x.get('date', ''), int(x.get('priority', 0)), x.get('id', '')),
        reverse=True,
    )[:500]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Total archive', len(archive))


if __name__ == '__main__':
    main()
