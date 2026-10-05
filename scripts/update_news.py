#!/usr/bin/env python3
"""KURO WATCH focused collector.

Collect only:
- Wuthering Waves / 鳴潮 leak-related information
- Kuro Games unannounced / in-development projects
- Controversy-only coverage for Genshin, Honkai: Star Rail, Zenless Zone Zero, and HoYoverse
  in Japanese, English and Chinese coverage

Category labels stay neutral: ハラ / スタレ / ゼンゼロ / ホヨバ.
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
HEADERS = {'User-Agent': 'KURO-WATCH/4.0 (personal focused news aggregator)'}

FEEDS = [
    ('リーク','JP','"Wuthering Waves" (leak OR leaked OR rumor OR datamine OR "test server" OR beta) when:14d','ja','JP','JP:ja'),
    ('リーク','JP','鳴潮 (リーク OR 噂 OR 流出 OR 未実装 OR テストサーバー OR ベータ OR 先行情報) when:14d','ja','JP','JP:ja'),
    ('リーク','CN','鸣潮 (爆料 OR 内鬼 OR 泄露 OR 测试服 OR 未实装 OR 前瞻) when:14d','zh-CN','CN','CN:zh-Hans'),

    ('新作','EN','"Kuro Games" ("new game" OR "new project" OR unannounced OR development OR recruiting OR hiring OR trademark) when:30d','en-US','US','US:en'),
    ('新作','JP','"Kuro Games" (新作 OR 新規プロジェクト OR 開発中 OR 求人 OR 商標) when:30d','ja','JP','JP:ja'),
    ('新作','CN','库洛游戏 (新游 OR 新作 OR 新项目 OR 未公开 OR 开发中 OR 招聘 OR 商标) when:30d','zh-CN','CN','CN:zh-Hans'),

    ('ハラ','JP','(原神 OR Genshin) (炎上 OR 批判 OR 騒動 OR 謝罪 OR 殺害予告 OR 脅迫 OR 不買 OR ボイコット OR 訴訟) when:14d','ja','JP','JP:ja'),
    ('ハラ','EN','Genshin (controversy OR backlash OR outrage OR boycott OR "death threat" OR harassment OR apology OR lawsuit) when:14d','en-US','US','US:en'),
    ('ハラ','CN','原神 (争议 OR 舆论 OR 抵制 OR 道歉 OR 威胁 OR 死亡威胁 OR 骚扰 OR 诉讼) when:14d','zh-CN','CN','CN:zh-Hans'),

    ('スタレ','JP','(スターレイル OR スタレ OR "Honkai Star Rail") (炎上 OR 批判 OR 騒動 OR 謝罪 OR 殺害予告 OR 脅迫 OR 不買 OR ボイコット) when:14d','ja','JP','JP:ja'),
    ('スタレ','EN','"Honkai Star Rail" (controversy OR backlash OR outrage OR boycott OR "death threat" OR harassment OR apology) when:14d','en-US','US','US:en'),
    ('スタレ','CN','崩坏星穹铁道 (争议 OR 舆论 OR 抵制 OR 道歉 OR 威胁 OR 骚扰) when:14d','zh-CN','CN','CN:zh-Hans'),

    ('ゼンゼロ','JP','(ゼンレスゾーンゼロ OR ゼンゼロ OR "Zenless Zone Zero") (炎上 OR 批判 OR 騒動 OR 謝罪 OR 殺害予告 OR 脅迫 OR 不買 OR ボイコット) when:14d','ja','JP','JP:ja'),
    ('ゼンゼロ','EN','"Zenless Zone Zero" (controversy OR backlash OR outrage OR boycott OR "death threat" OR harassment OR apology) when:14d','en-US','US','US:en'),
    ('ゼンゼロ','CN','绝区零 (争议 OR 舆论 OR 抵制 OR 道歉 OR 威胁 OR 骚扰) when:14d','zh-CN','CN','CN:zh-Hans'),

    ('ホヨバ','JP','(HoYoverse OR miHoYo OR ホヨバ) (炎上 OR 批判 OR 騒動 OR 謝罪 OR 新作 OR 発表 OR 殺害予告 OR 脅迫 OR 訴訟) when:14d','ja','JP','JP:ja'),
    ('ホヨバ','EN','(HoYoverse OR miHoYo) (controversy OR backlash OR outrage OR boycott OR lawsuit OR apology OR "new game") when:14d','en-US','US','US:en'),
    ('ホヨバ','CN','(米哈游 OR HoYoverse) (争议 OR 舆论 OR 抵制 OR 道歉 OR 新作 OR 新项目 OR 威胁 OR 诉讼) when:14d','zh-CN','CN','CN:zh-Hans'),
]

WUWA_RE = re.compile(r'(?i)(wuthering\s*waves|鳴潮|鸣潮)')
KURO_RE = re.compile(r'(?i)(kuro\s*games|クロゲ|庫洛遊戲|库洛游戏)')
LEAK_RE = re.compile(r'(?i)(leak|leaked|rumou?r|datamin|test server|beta|unconfirmed|リーク|噂|流出|未実装|テストサーバー|ベータ|先行情報|爆料|内鬼|泄露|测试服|未实装|前瞻)')
TEST_RE = re.compile(r'(?i)(test server|beta|cbt|テストサーバー|ベータ|先行テスト|测试服|测试|測試服)')
STRONG_RE = re.compile(r'(?i)(datamin|screenshot|image leak|footage|gameplay leak|画像|スクショ|実機|データマイン|拆包|实机|截图)')
OFFICIAL_RE = re.compile(r'(?i)(wuthering\s*waves|鳴潮公式|鸣潮官方|kuro\s*games|庫洛遊戲|库洛游戏)')
DEV_RE = re.compile(r'(?i)(new game|new project|unannounced|development|developing|recruit|hiring|trademark|新作|新規プロジェクト|開発中|求人|商標|新游|新项目|未公开|开发中|招聘|商标)')
CONTROVERSY_RE = re.compile(r'(?i)(controversy|backlash|outrage|boycott|criticism|apology|lawsuit|regulation|drama|death threat|harassment|炎上|批判|騒動|問題|不満|不買|ボイコット|謝罪|訴訟|規制|殺害予告|脅迫|誹謗中傷|嫌がらせ|争议|舆论|抵制|道歉|节奏|不满|质疑|诉讼|监管|威胁|死亡威胁|骚扰)')
VIDEO_SOURCE_RE = re.compile(r'(?i)(youtube|ニコニコ|tiktok|bilibili)')
GUIDE_RE = re.compile(r'(?i)(攻略|評価とおすすめ|おすすめパーティ|最強|tier|build|guide|武器|音骸|素材|育成|イベント攻略|ガチャ攻略|リセマラ|初心者|タブレット|スマホ|スマートフォン|pc benchmark)')
SPOILER_RE = re.compile(r'(?i)(spoiler|ネタバレ|劇透|剧透|leak|リーク|爆料|内鬼|泄露)')

TAG_RULES = [
    ('キャラ', r'(?i)(character|キャラ|角色)'),
    ('ストーリー', r'(?i)(story|plot|ストーリー|剧情|劇情)'),
    ('ガチャ', r'(?i)(gacha|banner|ガチャ|卡池)'),
    ('性能', r'(?i)(nerf|buff|balance|性能|弱体|強化|数値|平衡|削弱|加强)'),
    ('声優', r'(?i)(voice actor|voice actress|seiyuu|声優|cv|配音)'),
    ('予告配信', r'(?i)(livestream|special program|予告配信|特別番組|前瞻直播|前瞻节目)'),
    ('運営', r'(?i)(operation|management|運営|运营)'),
    ('新作', r'(?i)(new game|new project|新作|新项目|新專案)'),
    ('著作権', r'(?i)(copyright|plagiarism|著作権|盗作|抄袭)'),
    ('規制', r'(?i)(regulation|censor|規制|検閲|监管|审查)'),
    ('脅迫', r'(?i)(death threat|threat|殺害予告|脅迫|威胁|死亡威胁)'),
]
MAJOR_RE = re.compile(r'(?i)(death threat|殺害予告|死亡威胁|lawsuit|訴訟|诉讼|arrest|逮捕|警察|police|脅迫|威胁)')

def clean(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or '')).strip()[:500]

def tags_for(text):
    tags = [name for name, pat in TAG_RULES if re.search(pat, text)]
    if MAJOR_RE.search(text):
        tags.append('重大')
    return list(dict.fromkeys(tags))

def wanted(title, source, category):
    text = f'{title} {source}'
    if GUIDE_RE.search(title):
        return False
    if category == 'リーク':
        return bool(WUWA_RE.search(text) and LEAK_RE.search(text))
    if category == '新作':
        return bool(KURO_RE.search(text) and DEV_RE.search(text))
    if category in ('ハラ','スタレ','ゼンゼロ','ホヨバ'):
        return bool(CONTROVERSY_RE.search(text))
    return False

def leak_status(title, source):
    text = f'{title} {source}'
    if OFFICIAL_RE.search(source) and not LEAK_RE.search(title):
        return '公式発表'
    if TEST_RE.search(text):
        return 'テスト情報'
    if STRONG_RE.search(text):
        return '有力リーク'
    return '未確認の噂'

def collect_from_xml(xml_bytes, category, lang):
    root = ET.fromstring(xml_bytes)
    now = dt.datetime.now(dt.timezone.utc)
    items = []
    for item in root.findall('./channel/item'):
        title = clean(item.findtext('title'))
        source = clean(item.findtext('source'))
        link = (item.findtext('link') or '').strip()
        if not title or not link.startswith('https://') or not wanted(title, source, category):
            continue
        if VIDEO_SOURCE_RE.search(source) and category in ('リーク','新作'):
            continue
        try:
            when = email.utils.parsedate_to_datetime(item.findtext('pubDate')).astimezone(dt.timezone.utc)
        except Exception:
            continue

        max_age = 16 if category == 'リーク' else 35 if category == '新作' else 16
        if not (now - dt.timedelta(days=max_age) <= when <= now + dt.timedelta(days=1)):
            continue

        if category == 'リーク':
            status = leak_status(title, source)
            summary = (f'配信元: {source}。' if source else '') + f'鳴潮リーク分類: {status}。内容は出典先で確認してください。'
            tags = []
        elif category == '新作':
            status = '報道'
            summary = (f'配信元: {source}。' if source else '') + 'クロゲの新作・未発表/開発中プロジェクト関連として検出。内容は出典先で確認してください。'
            tags = ['新作']
        else:
            status = '報道'
            tags = tags_for(f'{title} {source}')
            summary = (f'配信元: {source}。' if source else '') + 'このカテゴリでは炎上・騒動・批判などの話題だけを収集しています。'

        items.append({
            'id': 'rss-' + hashlib.sha256((title + '|' + source).encode()).hexdigest()[:18],
            'date': when.date().isoformat(),
            'category': category,
            'status': status,
            'lang': lang,
            'title': title,
            'summary': summary,
            'url': link,
            'spoiler': bool(SPOILER_RE.search(title)),
            'source': source,
            'tags': tags,
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
    for category, lang, q, hl, gl, ceid in FEEDS:
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({
            'q': q, 'hl': hl, 'gl': gl, 'ceid': ceid
        })
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                fetched = collect_from_xml(r.read(1500000), category, lang)
            success += 1
            for x in fetched:
                items[x['id']] = x
            print(category, lang, len(fetched))
        except Exception as e:
            print('RSS read failed:', category, lang, str(e))

    if success == 0:
        raise RuntimeError('Every feed failed; leaving archive intact')

    archive = sorted(items.values(), key=lambda x: (x.get('date',''), x.get('id','')), reverse=True)[:500]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Focused archive', len(archive))

if __name__ == '__main__':
    main()
