#!/usr/bin/env python3
"""GACHA WARS release gate: validate published content and inline JavaScript."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "gacha-wars"

class SiteTests(unittest.TestCase):
    def read(self, filename):
        return json.loads((SITE / filename).read_text(encoding="utf-8"))

    def test_html_javascript_syntax(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S | re.I)
        self.assertTrue(scripts, "inline site script missing")
        with tempfile.TemporaryDirectory() as temp:
            for i, script in enumerate(scripts):
                js = Path(temp) / f"site-{i}.js"
                js.write_text(script, encoding="utf-8")
                subprocess.run(["node", "--check", str(js)], check=True, capture_output=True, text=True)

    def test_duel_requires_comparable_observations(self):
        """Do not regress safeguards for incomparable ranking snapshots."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function duel(){")
        end = html.index("function ", start + len("function duel(){"))
        duel = html[start:end]
        self.assertIn('sameIosScan(ra,iosMarketStatus[region])', duel)
        self.assertIn('sameIosScan(rb,iosMarketStatus[region])', duel)
        self.assertIn('iosMarketStatus[region].matched?.includes(a)', duel)
        self.assertIn('iosMarketStatus[region].matched?.includes(b)', duel)
        self.assertIn('ra.source.trim().toLowerCase()!==rb.source.trim().toLowerCase()', duel)
        self.assertIn('Androidの取得元が異なるため比較不可', duel)
        self.assertIn('同じ最新巡回の実測順位が揃っていないため比較不可', duel)

    def test_character_search_controls_and_filter(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('function changeCharacterSearch(value)', html)
        self.assertIn('id="characterSearch"', html)
        self.assertIn('characterSearch.toLocaleLowerCase()', html)
        self.assertIn('changeCharacterSearch(&quot;&quot;)', html)

    def test_anniversary_convenes_separate_from_normal_ranking(self):
        events = self.read("release-events.json")["events"]
        anniversary = [e for e in events if e.get("banner_type") == "anniversary_convene"]
        self.assertGreaterEqual(len(anniversary), 10)
        expected = {"first": 5, "second": 5}
        for phase, count in expected.items():
            self.assertGreaterEqual(sum(e["game"] == "ww" and
                                        e["version_group"] == "Ver.2.3" and
                                        e["phase"] == phase for e in anniversary), count)
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('specialEvents=events.filter(e=>', html)
        self.assertIn('"anniversary_convene"', html)
        self.assertIn('周年記念・選択式★5', html)

    def test_character_ranking_pagination(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('function changeCharacterPage(n)', html)
        self.assertIn('ranked.slice(characterPage*50,(characterPage+1)*50)', html)
        self.assertIn('visibleRanked.map((x,i)', html)
        self.assertIn('ranked.slice(0,characterPage*50+i+1)', html)
        self.assertIn("+'</tbody></table></div>'+pager+'</section>'", html)

    def test_character_rank_requires_full_14_day_observation(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("complete:after&&possible>=14&&daily.size===14", html)
        self.assertIn('e.schedule_status!=="announced"', html)
        self.assertIn('const scheduledEvents=events.filter(e=>e.schedule_status==="announced")', html)

    def test_incomplete_historical_rank_is_not_called_ongoing(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('p.possible>=14?"期間終了・欠測 "', html)
        self.assertIn('"集計期間途中 "+p.days+"/14日"', html)
        self.assertIn('complete:after&&possible>=14&&daily.size===14', html)

    def test_future_rank_observations_are_excluded(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function periodStats(")
        end = html.index("function observationQuality(", start)
        period = html[start:end]
        self.assertIn("t>=max||t>current", period)
        self.assertIn("complete:after&&possible>=14&&daily.size===14", period)

    def test_phase_trend_rejects_future_observations(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function phaseTrend(")
        end = html.index("function phaseBattles(", start)
        phase = html[start:end]
        self.assertIn("Number.isFinite(t)&&t<=today&&i>=0&&i<14", phase)

    def test_period_stats_runtime_scenarios(self):
        """Execute the actual inline JS with complete, missing and future rows."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        day_start = html.index("function observationDay(")
        day_end = html.index("function observationQuality(", day_start)
        functions = html[html.index("function validRankValue("):day_end]
        scenario = r"""
const assert = require("node:assert/strict");
let records = [], autoRecords = [], region = "jp", store = "ios";
const dayMs = 86400000;
const current = new Date(Date.now() + 9 * 3600000).toISOString().slice(0,10);
const today = Date.parse(current+"T00:00:00Z");
const start = new Date(today-20*dayMs).toISOString().slice(0,10);
const make = i => ({
  game:"ww",kind:"rank",region:"jp",store:"ios",value:i+1,
  date:new Date(Date.parse(start+"T00:00:00Z")+i*dayMs).toISOString().slice(0,10)
});
records = Array.from({length:14},(_,i)=>make(i));
let full = periodStats("ww",start,true);
assert.equal(full.days,14);
assert.equal(full.complete,true);
assert.equal(full.best,1);
// The 14th observation can exist on the 14th calendar day, but that
// day is still in progress and must not be treated as a final result.
const ongoingStart = new Date(today-13*dayMs).toISOString().slice(0,10);
const ongoingMake = i => ({
  ...make(i),
  date:new Date(Date.parse(ongoingStart+"T00:00:00Z")+i*dayMs).toISOString().slice(0,10)
});
records = Array.from({length:14},(_,i)=>ongoingMake(i));
const ongoing = periodStats("ww",ongoingStart,true);
assert.equal(ongoing.days,14);
assert.equal(ongoing.complete,false);
records = Array.from({length:14},(_,i)=>make(i));
records.splice(5,1);
let missing = periodStats("ww",start,true);
assert.equal(missing.days,13);
assert.equal(missing.complete,false);
records = [make(0)];
const futureStart = new Date(today+2*dayMs).toISOString().slice(0,10);
assert.equal(periodStats("ww",futureStart,true),null);
records.push({...make(1),date:new Date(today+10*dayMs).toISOString()});
assert.equal(periodStats("ww",start,true).days,1);
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "period-scenarios.cjs"
            path.write_text(functions + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(path)], check=True,
                           capture_output=True, text=True)

    def test_14_day_window_waits_until_next_day(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function periodStats(")
        end = html.index("function observationQuality(", start)
        period = html[start:end]
        self.assertIn("Math.floor((current-start)/86400000))):7", period)
        self.assertNotIn("Math.floor((current-start)/86400000)+1", period)

    def test_update_21_day_comparison_runtime(self):
        """Evaluate the actual ranking function under full and missing day scenarios."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        functions = html[html.index("function validRankValue("):
                         html.index("function observationQuality(")]
        scenario = r"""
const assert = require("node:assert/strict");
let records = [], autoRecords = [], region = "jp", store = "ios";
const step = 86400000;
const today = Date.parse(new Date(Date.now()+9*3600000).toISOString().slice(0,10)+"T00:00:00Z");
const base = today - 30*step;
const date = i => new Date(base+i*step).toISOString().slice(0,10);
const sample = Array.from({length:21},(_,i)=>({
  game:"ww",kind:"rank",region:"jp",store:"ios",date:date(i),value:i<7?20:10
}));
function comparable(rows) {
  records = rows;
  const pre = periodStats("ww",date(7),false);
  const post = periodStats("ww",date(7),true);
  return Boolean(pre&&post&&pre.days===7&&post.complete&&post.days===14);
}
assert.equal(comparable(sample),true);
assert.equal(comparable(sample.filter((_,i)=>i!==3)),false);
assert.equal(comparable(sample.filter((_,i)=>i!==10)),false);
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "comparison-21-days.cjs"
            path.write_text(functions + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(path)], check=True,
                           capture_output=True, text=True)

    def test_ios_history_and_integrity(self):
        data = self.read("ios-rank-data.json")
        self.assertEqual(data["schema"], "gacha-wars-ios-v1")
        rows = data["records"]
        self.assertGreaterEqual(len(rows), 190, "iOS history fell below verified archive baseline")
        keys = [(r["game"], r["region"], r["date"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)), "duplicate chart observations")
        for r in rows:
            self.assertIn(r["game"], {"gi", "hsr", "zzz", "ww", "nte", "end"})
            self.assertIn(r["region"], {"jp", "cn", "tw", "hk", "kr", "us"})
            self.assertEqual(r["store"], "ios")
            self.assertEqual(r["kind"], "rank")
            self.assertIs(type(r["value"]), int)
            self.assertGreater(r["value"], 0)
        for market in ("jp", "cn", "tw", "hk", "kr", "us"):
            status = data["market_status"][market]
            check = data["integrity"][market]
            if status["ok"]:
                self.assertTrue(check["ok"], f"{market} integrity failed")
                self.assertFalse(check["missing_rank_records"])
                self.assertEqual(check["matched_count"], check["recorded_count"])
            else:
                self.assertIsNone(check["ok"])

    def test_published_release_events(self):
        data = self.read("release-events.json")
        self.assertEqual(data["schema"], "gacha-wars-releases-v1")
        self.assertGreaterEqual(len(data["events"]), 534, "published release archive shrank")
        ids = [e["id"] for e in data["events"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate release event IDs")
        # A large archive is not useful if the same banner is counted twice or
        # entries silently lose their provenance.  Keep these checks independent
        # of the total baseline: the archive can grow without hiding corruption.
        semantic_keys = []
        for event in data["events"]:
            self.assertIn(event["game"], {"gi", "hsr", "zzz", "ww", "nte", "end"})
            self.assertIn(event["type"], {"character", "version", "weapon"})
            self.assertRegex(event["date"], r"^\d{4}-\d{2}-\d{2}$")
            from datetime import date
            self.assertEqual(date.fromisoformat(event["date"]).isoformat(), event["date"])
            self.assertTrue(event["version"].strip())
            self.assertTrue(event["source_url"].startswith("https://"))
            self.assertIn(event["verification"], {"official", "secondary", "unreviewed"})
            if event["type"] == "character":
                self.assertIn(event["event_kind"], {"debut", "rerun", "featured_banner"})
                self.assertIn(event["phase"], {"first", "second", "unknown"})
                self.assertTrue(event["version_group"].strip())
                semantic_keys.append((
                    event["game"], event["version"], event["date"],
                    event.get("banner_type") or "",
                    (event.get("featured_five_star") or "")
                    if event.get("banner_type") in {
                        "featured_convene_four_star", "anniversary_convene_four_star",
                        "collab_convene_four_star", "reverb_convene_four_star",
                        "exclusive_channel_a_rank", "exclusive_channel_a_default"
                    } else ""
                ))
            if event["type"] == "weapon":
                self.assertIn(event["game"], {"zzz", "ww"})
                self.assertIn(event.get("rarity"), {"S","A",5,4})
                self.assertIn(event.get("banner_type"), {"w_engine_s_rank", "w_engine_a_rank", "w_engine_a_default", "ww_weapon_five", "ww_weapon_four", "ww_weapon_anniversary_five", "ww_weapon_anniversary_four", "ww_weapon_collab_five"})
                self.assertEqual(event["event_kind"], "featured_banner")
                self.assertIn(event.get("phase"), {"first","second"})
                self.assertTrue(event.get("featured_five_star"))
                self.assertTrue(event.get("version_group"))
                semantic_keys.append((
                    event["game"], event["version"], event["date"],
                    event["banner_type"], event["featured_five_star"]
                ))
        self.assertEqual(len(semantic_keys), len(set(semantic_keys)),
                         "duplicate banner item of the same date and featured parent")


    def test_special_pools_share_one_visible_row(self):
        """Each 3-person four-star rotation should render once, without losing names."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        helper = html[html.index("function renderSpecialEventsGrouped("):
                      html.index("function characterRanking()")]
        scenario = r'''
const assert = require("node:assert/strict");
const esc = String;
const name = value => value === "gi" ? "原神" : value;
const phaseLabel = x => x.phase === "first" ? "前半" : "後半";
const eventSource = e => '<a>' + e.source_url + '</a>';
const sample = ["ヨォーヨ", "雲菫", "辛炎"].map((version,i)=>({
  id:"test"+i,game:"gi",type:"character",version,date:"2023-01-18",
  phase:"first",version_group:"Ver.3.4",
  banner_type:"event_wish_four_star",
  rarity:4,source_url:"https://example.com/source"
}));
const result=renderSpecialEventsGrouped(sample);
assert.equal((result.match(/<tr>/g)||[]).length,1);
for (const e of sample) assert.ok(result.includes(e.version));
assert.ok(result.includes("3枠を同時開催"));
assert.equal((result.match(/https:\/\/example.com\/source/g)||[]).length,1);
const another={...sample[0],id:"other",date:"2023-02-07"};
assert.equal((renderSpecialEventsGrouped([...sample,another]).match(/<tr>/g)||[]).length,2);
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "grouped-special.cjs"
            path.write_text(helper + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(path)], check=True,
                           capture_output=True, text=True)

    def test_genshin_2023_2025_four_star_phase_coverage(self):
        """Every 2023-25 limited wish phase has one shared three-character pool."""
        audit = self.read("audits/2026-10-12-genshin-2023-2025-fourstar-rotations.json")
        events = self.read("release-events.json")["events"]
        summary = audit["summary"]
        self.assertEqual(summary["periods"], 52)
        self.assertEqual(summary["slots"], 156)
        self.assertEqual(summary["newly_added"], 138)
        self.assertGreaterEqual(len(events), summary["total_live_records"])
        self.assertEqual(len(audit["banner_periods"]), 52)
        per_date = {}
        for event in events:
            if (event["game"] == "gi" and
                "2023-01-01" <= event["date"] < "2026-01-01" and
                event.get("banner_type") == "event_wish_four_star"):
                per_date.setdefault(event["date"], []).append(event)
        self.assertEqual(len(per_date), 52)
        self.assertEqual(sum(map(len, per_date.values())), 156)
        self.assertEqual({v[0]["date"][:4] for v in per_date.values()},
                         {"2023", "2024", "2025"})
        all_added = set()
        for phase in audit["banner_periods"]:
            with self.subTest(date=phase["date"]):
                current = per_date[phase["date"]]
                self.assertEqual(len(current), 3)
                self.assertEqual(len(set(e["version"] for e in current)), 3)
                self.assertEqual({e["version"] for e in current}, set(phase["members"]))
                self.assertEqual({e["id"] for e in current}, set(phase["ids"]))
                self.assertEqual({e["source_url"] for e in current}, set(phase["sources"]))
                self.assertTrue(all(e["rarity"] == 4 and
                                    e["verification"] == "official" and
                                    e["phase"] == phase["phase"] and
                                    e["version_group"] == phase["version_group"]
                                    for e in current))
                self.assertTrue(any(x["game"] == "gi" and
                                    x["date"] == phase["date"] and
                                    x.get("rarity", 5) != 4 and
                                    x["event_kind"] in {"debut", "rerun"}
                                    for x in events))
                all_added.update(phase["new_this_batch"])
        self.assertEqual(len(all_added), 138)
        self.assertTrue(all(x.startswith("gi-four-pu-") for x in all_added))
        june = per_date["2023-06-13"]
        self.assertEqual({e["version"] for e in june},
                         {"鹿野院平蔵", "香菱", "ヨォーヨ"})
        self.assertTrue(all(e["banner_type"] == "event_wish_four_star"
                            for e in june))
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('!specialTypes.includes(ev.banner_type)', html)

    def test_genshin_2020_2022_five_star_banner_four_star_pool_coverage(self):
        """Every historic 2020-2022 banner phase has exactly three shared 4-star PU slots."""
        ledger = self.read("audits/2026-10-12-genshin-2020-2022-fourstar-rotations.json")
        events = self.read("release-events.json")["events"]
        self.assertEqual(ledger["summary"]["periods"], 41)
        self.assertEqual(ledger["summary"]["four_star_slots"], 123)
        self.assertEqual(ledger["summary"]["newly_added"], 104)
        self.assertGreaterEqual(len(events), ledger["summary"]["total_live_events"])
        id_index = {e["id"]: e for e in events}
        periods = ledger["banner_periods"]
        self.assertEqual(len(periods), 41)
        self.assertEqual(len({p["date"] for p in periods}), 41)
        current = [e for e in events if e["game"] == "gi"
                   and "2020-09-28" <= e["date"] < "2023-01-01"
                   and e.get("banner_type") == "event_wish_four_star"]
        self.assertEqual(len(current), 123)
        self.assertEqual(len({(e["date"], e["version"]) for e in current}), 123)
        new_ids = set()
        for pool in periods:
            with self.subTest(date=pool["date"]):
                self.assertEqual(len(pool["members"]), 3)
                self.assertEqual(len(set(pool["members"])), 3)
                actual = [e for e in current if e["date"] == pool["date"]]
                self.assertEqual({e["version"] for e in actual}, set(pool["members"]))
                self.assertEqual({e["id"] for e in actual}, set(pool["ids"]))
                self.assertEqual({e["source_url"] for e in actual}, set(pool["sources"]))
                self.assertTrue(all(e["rarity"] == 4 and
                                    e["verification"] == "official" and
                                    e["banner_type"] == "event_wish_four_star"
                                    for e in actual))
                self.assertTrue(all(e["version_group"] == pool["version_group"]
                                    and e["phase"] == pool["phase"]
                                    for e in actual))
                self.assertTrue(any(e["game"] == "gi" and
                                    e["date"] == pool["date"] and
                                    e.get("rarity", 5) != 4 and
                                    e["event_kind"] in {"debut", "rerun", "featured_banner"}
                                    for e in events))
                for eid in pool["four_star_added_this_turn"]:
                    self.assertTrue(eid.startswith("gi-four-pu-"))
                    self.assertIn(eid, id_index)
                    new_ids.add(eid)
        self.assertEqual(len(new_ids), 104)
        html = (SITE / "index.html").read_text(encoding="utf-8")
        for label in ("event_wish_four_star", "!specialTypes.includes(ev.banner_type)"):
            self.assertIn(label, html)

    def test_genshin_four_star_debut_backfill_2020_through_2025(self):
        """New four-stars are documented but excluded from five-star banner rankings."""
        events = self.read("release-events.json")["events"]
        four = [e for e in events if e["id"].startswith("gi-four-debut-")
                and e["date"] < "2026-01-01"]
        self.assertEqual(len(four), 33)
        expected = {
            "ディオナ": "2020-11-11", "辛炎": "2020-12-01",
            "ロサリア": "2021-04-06", "煙緋": "2021-04-28",
            "早柚": "2021-08-10", "九条裟羅": "2021-09-01",
            "トーマ": "2021-11-02", "ゴロー": "2021-12-14",
            "雲菫": "2022-01-05", "久岐忍": "2022-06-21",
            "鹿野院平蔵": "2022-07-13", "コレイ": "2022-08-24",
            "ドリー": "2022-09-09", "キャンディス": "2022-09-28",
            "レイラ": "2022-11-18", "ファルザン": "2022-12-07",
            "ヨォーヨ": "2023-01-18", "ミカ": "2023-03-21",
            "カーヴェ": "2023-05-02", "綺良々": "2023-05-24",
            "リネット": "2023-08-16", "フレミネ": "2023-09-05",
            "シャルロット": "2023-11-08", "シュヴルーズ": "2024-01-09",
            "嘉明": "2024-01-31", "セトス": "2024-06-05",
            "カチーナ": "2024-08-28", "オロルン": "2024-11-20",
            "藍硯": "2025-01-21", "イアンサ": "2025-03-26",
            "イファ": "2025-05-07", "ダリア": "2025-06-18",
            "ヤフォダ": "2025-12-03",
        }
        self.assertEqual({e["version"]: e["date"] for e in four}, expected)
        for event in four:
            with self.subTest(character=event["version"]):
                self.assertEqual(event["game"], "gi")
                self.assertEqual(event["rarity"], 4)
                self.assertEqual(event["event_kind"], "debut")
                self.assertEqual(event["banner_type"], "event_wish_four_star")
                self.assertEqual(event["verification"], "official")
                self.assertTrue(event["version_group"])
                self.assertIn(event["phase"], {"first", "second"})
                self.assertTrue(event["source_url"].startswith("https://"))
        self.assertEqual(len({(e["game"], e["version"], e["date"])
                              for e in four}), len(four))
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertGreaterEqual(html.count('"event_wish_four_star"'), 4)
        self.assertIn('!specialTypes.includes(ev.banner_type)', html)

    def test_all_official_genshin_chronicled_wishes_and_reminiscence(self):
        """Keep seven curated selectable five-star roster pools distinct from reruns."""
        events = self.read("release-events.json")["events"]
        expected = {
            ("2024-03-13", "暁風の詩"): {
                "モナ", "クレー", "ディルック", "ジン", "アルベド", "エウルア"
            },
            ("2025-01-21", "玉岩の憶"): {
                "白朮", "申鶴", "刻晴", "甘雨", "七七", "タルタリヤ", "魈"
            },
            ("2025-05-27", "天を裂く雷鳴"): {
                "神里綾華", "神里綾人", "宵宮", "千織", "八重神子",
                "荒瀧一斗", "珊瑚宮心海", "楓原万葉"
            },
            ("2025-09-10", "露と草の盃"): {
                "ディシア", "アルハイゼン", "放浪者", "セノ", "ニィロウ", "ティナリ"
            },
            ("2026-02-25", "暁風の詩"): {
                "エウルア", "モナ", "アルベド", "クレー", "ディルック", "ジン"
            },
            ("2026-04-28", "ルキナのせせらぎ"): {
                "エミリエ", "クロリンデ", "シグウィン", "ナヴィア", "リネ"
            },
            ("2026-07-01", "空に輝く星のお告げ"): {
                "夢見月瑞希", "リオセスリ", "セノ", "八重神子", "七七"
            },
        }
        special = [e for e in events if e["game"] == "gi" and
                   e.get("banner_type") in {"chronicled_wish", "reminiscence_wish"}]
        grouped = {}
        for e in special:
            if e.get("wish_name"):
                key = (e["date"], e["wish_name"])
            else:
                # The already-curated Luna I pool predates wish_name metadata.
                key = (e["date"], "露と草の盃")
            grouped.setdefault(key, []).append(e)
        self.assertEqual(set(grouped), set(expected))
        self.assertEqual(sum(map(len, grouped.values())), 43)
        for key, pool in grouped.items():
            with self.subTest(wish=key):
                suffixes = {"（追憶祈願）", "（集録祈願）"}
                self.assertEqual(
                    {next(e["version"][:-len(t)] for t in suffixes
                          if e["version"].endswith(t)) for e in pool},
                    expected[key],
                )
                self.assertTrue(all(e["verification"] == "official" for e in pool))
                self.assertTrue(all(e["event_kind"] == "featured_banner" for e in pool))
                self.assertTrue(all(e["rarity"] == 5 for e in pool))
                self.assertTrue(all(e.get("banner_type") ==
                                    ("reminiscence_wish" if key[0] == "2026-07-01"
                                     else "chronicled_wish") for e in pool))
        html = (SITE / "index.html").read_text(encoding="utf-8")
        for label in ("追憶祈願の選択候補", "集録祈願の選択候補", "追憶祈願・★"):
            self.assertIn(label, html)
        self.assertGreaterEqual(html.count('"reminiscence_wish"'), 5)

    def test_special_banner_types_are_explicit_and_separate(self):
        events = self.read("release-events.json")["events"]
        special_types = {
            "anniversary_convene", "special_rerun", "event_wish_four_star",
            "event_warp_four_star", "exclusive_channel_a_rank",
            "exclusive_channel_a_default",
            "featured_convene_four_star", "anniversary_convene_four_star",
            "collab_convene_four_star", "reverb_convene_four_star",
            "chronicled_wish", "reminiscence_wish", "standard_character_event",
            "w_engine_s_rank", "w_engine_a_rank", "w_engine_a_default",
            "ww_weapon_five", "ww_weapon_four", "ww_weapon_anniversary_five",
            "ww_weapon_anniversary_four", "ww_weapon_collab_five"
        }
        specials = [e for e in events if e.get("banner_type")]
        self.assertGreaterEqual(len(specials), 20)
        for event in specials:
            self.assertIn(event["banner_type"], special_types)
            self.assertEqual(event["type"], "weapon" if event["banner_type"].startswith(("w_engine_", "ww_weapon_")) else "character")
        html = (SITE / "index.html").read_text(encoding="utf-8")
        # Both the actual group filter and the coverage counters must agree.
        for kind in special_types:
            self.assertGreaterEqual(html.count('"' + kind + '"'), 1 if kind.startswith(("w_engine_", "ww_weapon_")) else 2, kind)

    def test_youtube_archive_over_3000_records(self):
        """A missing API key must not truncate or corrupt a large archive."""
        import os
        import shutil
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "gacha-wars").mkdir()
            shutil.copy2(ROOT / "scripts" / "update_gacha_youtube.py",
                         root / "scripts" / "update_gacha_youtube.py")
            (root / "gacha-wars" / "youtube-targets.json").write_text(
                json.dumps({"videos": [{"game": "ww", "video_id": "LczEBLHeu24"}]}),
                encoding="utf-8")
            start = datetime(2017, 1, 1, tzinfo=timezone.utc)
            original = [
                {"game": "ww", "region": "global", "kind": "sns",
                 "store": "youtube", "video_id": "LczEBLHeu24",
                 "value": i, "date": (start + timedelta(days=i)).isoformat(),
                 "source": "YouTube Data API v3"}
                for i in range(3001)
            ]
            out = root / "gacha-wars" / "youtube-data.json"
            out.write_text(json.dumps({"records": original}), encoding="utf-8")
            env = dict(os.environ)
            env.pop("YOUTUBE_API_KEY", None)
            subprocess.run(["python", str(root / "scripts" / "update_gacha_youtube.py")],
                           env=env, check=True, capture_output=True, text=True)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "missing_api_key")
            self.assertEqual(len(saved["records"]), 3001)
            self.assertEqual(saved["records"][0]["date"], original[0]["date"])
            self.assertEqual(saved["records"][-1]["date"], original[-1]["date"])

    def test_release_coverage_by_game(self):
        """Track archive coverage without pretending it proves completeness."""
        data = self.read("release-events.json")["events"]
        baseline = {"gi": 196, "hsr": 139, "zzz": 71,
                    "ww": 100, "nte": 12, "end": 15}
        for game, minimum in baseline.items():
            rows = [e for e in data if e["game"] == game]
            self.assertGreaterEqual(len(rows), minimum,
                                    f"{game} release history unexpectedly shrank")
            self.assertTrue(any(e["type"] == "character" for e in rows))

    def test_zzz_15_reruns_are_recorded(self):
        events = self.read("release-events.json")["events"]
        reruns = [e for e in events if e["game"] == "zzz" and
                  e.get("version_group") == "Ver.1.5" and
                  e.get("event_kind") == "rerun"]
        self.assertEqual(
            {(e["version"], e["date"], e["phase"]) for e in reruns},
            {("エレン（復刻）", "2025-01-22", "first"),
             ("青衣（復刻）", "2025-02-12", "second")}
        )

    def test_special_reruns_not_ranked_as_regular_banners(self):
        """Special select-a-character events must not inherit regular banner results."""
        data = self.read("release-events.json")["events"]
        special = [e for e in data if e.get("banner_type") == "special_rerun"]
        self.assertGreaterEqual(len(special), 6)
        self.assertEqual(len({(e["game"], e["date"], e["version"]) for e in special}),
                         len(special))
        self.assertTrue(all(e["event_kind"] in {"rerun", "featured_banner"} for e in special))
        html = (SITE / "index.html").read_text(encoding="utf-8")
        ranking = html[html.index("function characterRanking()"):
                       html.index("function ", html.index("function characterRanking()") + 30)]
        updates = html[html.index("function updates(){"):
                       html.index("function ", html.index("function updates(){") + 20)]
        phases = html[html.index("function phaseBattles()"):
                      html.index("function updates(){")]
        self.assertIn('"special_rerun"', ranking)
        self.assertIn('!specialTypes.includes(ev.banner_type)', updates)
        self.assertIn('!specialTypes.includes(e.banner_type)', phases)
        grouped = html[html.index("function renderSpecialEventsGrouped("):
                       html.index("function characterRanking()")]
        self.assertIn('e.banner_type==="special_rerun"?"特別復刻枠"', grouped)
        self.assertIn("renderSpecialEventsGrouped(specialEvents)", ranking)

    def test_yinlin_december_2024_rerun_source(self):
        events = {e["id"]: e for e in self.read("release-events.json")["events"]}
        event = events["historical-ww-2024-12-12-49"]
        self.assertEqual(event["version"], "吟霖（復刻）")
        self.assertEqual(event["date"], "2024-12-12")
        self.assertEqual(event["verification"], "official")
        self.assertEqual(
            event["source_url"],
            "https://wutheringwaves.kurogames.com/jp/main/news/detail/1762"
        )

    def test_kuro_press_releases_for_early_2024_banners(self):
        """Check primary publisher release references for launch/early banners."""
        events = {e["id"]: e for e in self.read("release-events.json")["events"]}
        expected = {
            "history-ww-2024-05-23-0": ("忌炎", "2024-05-23", "/000000001.000143406.html"),
            "history-ww-2024-07-22-3": ("長離", "2024-07-22", "/000000004.000143406.html"),
            "historical-ww-2024-09-07-45": ("相里要", "2024-09-07", "/000000008.000143406.html"),
        }
        for key, (name, date, suffix) in expected.items():
            with self.subTest(key=key):
                event = events[key]
                self.assertEqual(event["version"], name)
                self.assertEqual(event["date"], date)
                self.assertEqual(event["verification"], "official")
                self.assertTrue(event["source_url"].startswith("https://prtimes.jp/main/html/rd/p/"))
                self.assertTrue(event["source_url"].endswith(suffix))

    def test_publisher_sources_for_2024_zenless_and_wuthering_debuts(self):
        """Guard publisher notices and exact launch dates for reverified records."""
        events = {e["id"]: e for e in self.read("release-events.json")["events"]}
        expected = {
            "history-zzz-2024-08-14-20":
                ("2024-08-14", "青衣", "prtimes.jp", "/000000235.000096124.html"),
            "history-zzz-2024-11-06-24":
                ("2024-11-06", "柳", "prtimes.jp", "/000000257.000096124.html"),
            "historical-ww-2024-09-29-46":
                ("2024-09-29", "ショアキーパー", "wutheringwaves.kurogames.com", "/1454"),
            "historical-ww-2024-11-14-48":
                ("2024-11-14", "ツバキ", "wutheringwaves.kurogames.com", "/1647"),
        }
        for key, (date, name, host, suffix) in expected.items():
            with self.subTest(event_id=key):
                event = events[key]
                self.assertEqual(event["date"], date)
                self.assertEqual(event["version"], name)
                self.assertEqual(event["verification"], "official")
                self.assertEqual(event["source_url"].split("/")[2], host)
                self.assertTrue(event["source_url"].endswith(suffix))

    def test_primary_notices_for_six_wuthering_waves_debuts(self):
        """Guard six publisher-backed debut notices against accidental downgrades."""
        events = {e["id"]: e for e in self.read("release-events.json")["events"]}
        verified = {
            "history-ww-2024-06-28-2": ("/996", "2024-06-28"),
            "historical-ww-2024-08-15-44": ("/1189", "2024-08-15"),
            "history-ww-2025-06-12-92": ("/2801", "2025-06-12"),
            "history-ww-2025-07-24-94": ("/2936", "2025-07-24"),
            "history-ww-2025-08-28-98": ("/3194", "2025-08-28"),
            "history-ww-2025-10-09-117": ("/3340", "2025-10-09"),
        }
        for event_id, (suffix, expected_date) in verified.items():
            with self.subTest(event_id=event_id):
                event = events[event_id]
                self.assertEqual(event["verification"], "official")
                self.assertEqual(event["date"], expected_date)
                self.assertEqual(
                    event["source_url"].split("/")[2],
                    "wutheringwaves.kurogames.com"
                )
                self.assertTrue(event["source_url"].endswith(suffix))

    def test_bulk_primary_source_backfill_is_consistent(self):
        """Bulk provenance ledger must match the live event dataset exactly."""
        ledger = self.read("audits/2026-10-12-batch-primary-source-backfill.json")
        events = self.read("release-events.json")["events"]
        lookup = {e["id"]: e for e in events}
        summary = ledger["summary"]
        self.assertGreaterEqual(len(events), summary["total_events"])
        self.assertEqual(summary["total_events"], 538)  # archived point-in-time baseline
        self.assertEqual(summary["upgraded_this_batch"], 35)
        self.assertEqual(len(ledger["upgraded"]), 35)
        self.assertEqual(len({e["id"] for e in ledger["upgraded"]}), 35)
        for entry in ledger["upgraded"]:
            with self.subTest(id=entry["id"]):
                ev = lookup[entry["id"]]
                self.assertEqual(ev["version"], entry["name"])
                self.assertEqual(ev["date"], entry["date"])
                self.assertEqual(ev["verification"], "official")
                self.assertEqual(ev["source_url"], entry["official_notice"])
                self.assertEqual(ev["source_url"].split("/")[2],
                                 "wutheringwaves.kurogames.com")
        secondary = {e["id"] for e in events if e["verification"] == "secondary"}
        original_backlog = {e["id"] for e in ledger["remaining_secondary"]}
        # This audit is a dated snapshot: later source verifications may
        # reduce the outstanding set without rewriting historical evidence.
        new_secondary_ids = {
            e["id"] for e in events
            if e["verification"] == "secondary" and e["id"].startswith(("hsr-four-pu-", "zzz-a-pu-", "ww-extra-four-", "zzz-a-2026-backfill-", "zzz-wengine-", "ww-weapon-"))
        }
        self.assertEqual(len(new_secondary_ids), 598)  # previous 512 + 86 secondary WW weapons
        self.assertTrue((secondary - new_secondary_ids) <= original_backlog)
        self.assertTrue(new_secondary_ids <= secondary)
        self.assertEqual(summary["secondary_labeled"], len(original_backlog))
        self.assertEqual(summary["first_party_labeled"],
                         summary["total_events"] - len(original_backlog))
        self.assertEqual(secondary & {e["id"] for e in ledger["upgraded"]},
                         set())

    def test_recent_primary_banner_verifications(self):
        """The 4 direct publisher notices must remain dated and attributed."""
        events = {e["id"]: e for e in self.read("release-events.json")["events"]}
        expected = {
            "history-zzz-2024-07-04-18":
                ("2024-07-04", "https://zenless.hoyoverse.com/ja-jp/news/124566"),
            "history-zzz-2024-10-16-23":
                ("2024-10-16", "https://zenless.hoyoverse.com/ja-jp/news/126371"),
            "history-zzz-2024-11-27-25":
                ("2024-11-27", "https://www.facebook.com/ZZZ.Official.JP/videos/1332661831445812/"),
            "history-hsr-2026-04-08-464":
                ("2026-04-08", "https://x.com/houkaistarrail/status/2041380447087927707"),
        }
        for event_id, (date, url) in expected.items():
            with self.subTest(event_id=event_id):
                event = events[event_id]
                self.assertEqual(event["date"], date)
                self.assertEqual(event["verification"], "official")
                self.assertEqual(event["date_basis"], "first_party_exact_banner_start")
                self.assertEqual(event["source_url"], url)

    def test_unresolved_provenance_panel_and_annotations(self):
        """All nonofficial banner records must remain discoverable with evidence."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("function unresolvedSourceBoard()", html)
        self.assertIn('publishedEvents.filter(e=>e.verification!=="official")', html)
        self.assertIn("+unresolvedSourceBoard()+'", html)
        self.assertIn("補助公式資料", html)
        self.assertIn("開始日まで直接確認できたことを意味しません", html)
        events = self.read("release-events.json")["events"]
        unresolved = [e for e in events if e["verification"] != "official"]
        self.assertTrue(unresolved)
        for event in unresolved:
            with self.subTest(event_id=event["id"]):
                self.assertTrue(event.get("date_basis"))
                self.assertTrue(event.get("review_note"))
                self.assertIsInstance(event.get("corroborating_sources"), list)
                for url in event["corroborating_sources"]:
                    self.assertTrue(url.startswith("https://"))
                if event.get("schedule_status") == "announced":
                    self.assertNotEqual(event["verification"], "official")

    def test_third_party_sources_are_not_marked_official(self):
        """A fan archive or aggregator link cannot by itself prove a publisher announcement."""
        events = self.read("release-events.json")["events"]
        third_party_hosts = {
            "wutheringwaves.gg", "wutheringwaves.fandom.com",
            "zenless.gg", "www.dearplayers.com"
        }
        checked = [
            e for e in events if
            e["source_url"].split("/")[2].lower() in third_party_hosts
        ]
        # All third-party citations can legitimately be replaced by first-party URLs.
        self.assertTrue(all(e["verification"] != "official" for e in checked))

    def test_endfield_celebration_scout_has_all_four_candidates(self):
        """The May 2026 special scout was a shared pool, not four rate-up reruns."""
        events = self.read("release-events.json")["events"]
        candidates = [e for e in events
                      if e["game"] == "end" and e["date"] == "2026-05-14"
                      and e.get("banner_type") == "special_rerun"]
        self.assertEqual({e["version"] for e in candidates}, {
            "レーヴァテイン（特殊スカウト対象）",
            "ギルベルタ（特殊スカウト対象）",
            "アルデリア（特殊スカウト対象）",
            "ポグラニチニク（特殊スカウト対象）"
        })
        self.assertTrue(all(e["event_kind"] == "featured_banner" for e in candidates))
        self.assertTrue(all(e["verification"] == "official" for e in candidates))
        self.assertTrue(all(e["source_url"].endswith("/4494") for e in candidates))

    def test_unconfirmed_schedule_is_labeled_as_unconfirmed(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("外部資料の予定・未確定", html)
        events = self.read("release-events.json")["events"]
        scheduled = [e for e in events if e.get("schedule_status") == "announced"]
        self.assertTrue(scheduled)
        for e in scheduled:
            self.assertIn(e["verification"], {"official", "secondary", "unreviewed"})

    def test_ww_35_phase_two_start_date(self):
        events = self.read("release-events.json")["events"]
        expected = ("スイスイ", "エイメス（復刻）")
        for name in expected:
            rows = [e for e in events if e["game"] == "ww"
                    and e.get("version_group") == "Ver.3.5"
                    and e["version"] == name]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["date"], "2026-07-30")
            self.assertEqual(rows[0]["phase"], "second")
            self.assertEqual(rows[0]["verification"], "official")

    def test_scheduled_banners_have_separate_visible_section(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("開催予定のキャラ・復刻（ランキング対象外）", html)
        self.assertIn("scheduledEvents.slice().sort(", html)
        self.assertIn("開催予定 '+scheduledEvents.length+'件", html)
        self.assertIn('e.schedule_status!=="announced"&&[', html)

    def test_phase_battles_exclude_scheduled_and_special_banners(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function phaseBattles()")
        end = html.index("function ", start + len("function phaseBattles()"))
        phase = html[start:end]
        self.assertIn('e.schedule_status!=="announced"', phase)
        self.assertIn('!specialTypes.includes(e.banner_type)', phase)
        self.assertIn('"anniversary_convene","special_rerun"', phase)

    def test_update_battles_exclude_announced_schedule(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function updates(){")
        end = html.index("function ", start + len("function updates(){"))
        section = html[start:end]
        self.assertIn('ev.schedule_status!=="announced"&&!specialTypes.includes(ev.banner_type)', section)
        self.assertIn("14日分すべての順位観測が揃った場合", html)

    def test_update_verdict_requires_full_21_day_coverage(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function updates(){")
        end = html.index("function ", start + len("function updates(){"))
        code = html[start:end]
        self.assertIn("pre.days===7&&post.complete&&post.days===14", code)
        self.assertIn("合計21日すべてに実測順位", code)

    def test_special_banners_excluded_from_update_battles(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function updates(){")
        end = html.index("function ", start + len("function updates(){"))
        section = html[start:end]
        self.assertIn("!specialTypes.includes(ev.banner_type)", section)
        for special_type in ("chronicled_wish", "reminiscence_wish", "event_wish_four_star",
                             "standard_character_event", "anniversary_convene",
                             "special_rerun"):
            self.assertIn('"' + special_type + '"', section)

    def test_elapsed_unconfirmed_schedules_keep_warning(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("予定日経過・実施未確認", html)
        self.assertGreaterEqual(html.count("予定日経過・実施未確認"), 2)
        self.assertIn('ev.schedule_status!=="announced"', html)
        self.assertIn('e.schedule_status!=="announced"', html)

    def test_overdue_unconfirmed_banners_remain_visible(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function releaseCalendar()")
        end = html.index("function ", start + len("function releaseCalendar()"))
        calendar = html[start:end]
        self.assertIn('e.date<today&&e.schedule_status==="announced"', calendar)
        self.assertIn('e.date<today&&e.schedule_status!=="announced"', calendar)
        self.assertIn("const events=[...upcoming,...overdue,...recent]", calendar)

    def test_event_timing_keeps_unconfirmed_status(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function eventTiming(")
        end = html.index("function phaseLabel(", start)
        timing = html[start:end]
        self.assertIn('e.schedule_status==="announced"', timing)
        self.assertIn("予定日経過・実施未確認", timing)
        self.assertIn("外部資料の予定・未確定", timing)

    def test_event_timing_runtime_scenarios(self):
        """Execute status labels, not just a string-presence assertion."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        code = html[html.index("function eventTiming("):
                    html.index("function phaseLabel(")]
        scenario = r"""
const assert = require("node:assert/strict");
const today = new Date(Date.now()+9*3600000).toISOString().slice(0,10);
const offset = n => new Date(Date.parse(today+"T00:00:00Z")+n*86400000).toISOString().slice(0,10);
assert.equal(eventTiming({date:offset(-2),schedule_status:"announced",verification:"secondary"}),"予定日経過・実施未確認");
assert.equal(eventTiming({date:offset(2),schedule_status:"announced",verification:"secondary"}),"外部資料の予定・未確定");
assert.equal(eventTiming({date:offset(2),schedule_status:"announced",verification:"official"}),"公式発表の予定");
assert.equal(eventTiming({date:offset(-2),verification:"official"}),"実装日到来");
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "timing-status.cjs"
            path.write_text(code + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(path)], check=True, capture_output=True, text=True)

    def test_latest_filters_invalid_and_future_records(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        function = html[html.index("function validRankValue("):
                        html.index("function recs(", html.index("function latest("))]
        scenario = r"""
const assert = require("node:assert/strict");
const now = new Date().toISOString();
const nextYear = new Date(Date.now()+365*86400000).toISOString();
const records = [
 {game:"ww",region:"jp",kind:"rank",store:"ios",date:now,value:7},
 {game:"ww",region:"jp",kind:"rank",store:"ios",date:nextYear,value:1},
 {game:"ww",region:"jp",kind:"rank",store:"ios",date:"invalid",value:1},
 {game:"ww",region:"jp",kind:"rank",store:"ios",date:now,value:0}
];
const autoRecords = [];
assert.equal(latest("ww","jp","rank","ios").value,7);
records.push({game:"ww",region:"global",kind:"steam",store:"steam",date:now,value:1200});
records.push({game:"ww",region:"global",kind:"steam",store:"steam",date:new Date(Date.now()+1000).toISOString(),value:1250.5});
assert.equal(latest("ww","global","steam","steam").value,1200);
records.push({game:"ww",region:"global",kind:"steam",store:"steam",date:new Date(Date.now()+2000).toISOString(),value:" "});
records.push({game:"ww",region:"global",kind:"steam",store:"steam",date:new Date(Date.now()+3000).toISOString(),value:true});
assert.equal(latest("ww","global","steam","steam").value,1200);
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "latest.cjs"
            path.write_text(function + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(path)], check=True, capture_output=True, text=True)

    def test_rank_statistics_reject_blank_and_boolean_values(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        script = html[html.index("function validRankValue("):
                      html.index("function observationQuality(")]
        scenario = r"""
const assert=require("node:assert/strict");
let records=[],autoRecords=[],region="jp",store="ios";
const day=86400000;
const now=Date.parse(new Date(Date.now()+9*3600000).toISOString().slice(0,10)+"T00:00:00Z");
const start=new Date(now-20*day).toISOString().slice(0,10);
records=[
 {game:"ww",region:"jp",store:"ios",kind:"rank",date:start,value:7},
 {game:"ww",region:"jp",store:"ios",kind:"rank",date:start,value:true},
 {game:"ww",region:"jp",store:"ios",kind:"rank",date:new Date(now-19*day).toISOString().slice(0,10),value:" "}
];
assert.equal(validRankValue(true),false);
assert.equal(validRankValue(" "),false);
assert.equal(validRankValue("7"),true);
const stats=periodStats("ww",start,true);
assert.equal(stats.days,1);
assert.equal(stats.best,7);
"""
        with tempfile.TemporaryDirectory() as temp:
            script_path=Path(temp)/"rank-values.cjs"
            script_path.write_text(script+"\n"+scenario, encoding="utf-8")
            subprocess.run(["node",str(script_path)],check=True,
                           capture_output=True,text=True)
        self.assertIn("!validRankValue(r.value)", html[html.index("function phaseTrend("):html.index("function phaseBattles(")])

    def test_latest_uses_shared_rank_validator(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function latest(")
        end = html.index("function recs(", start)
        self.assertIn("return validMetricValue(kind,x.value)", html[start:end])

    def test_history_list_rejects_invalid_rank_dates(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        start = html.index("function recs(")
        end = html.index("function isFresh(", start)
        code = html[start:end]
        self.assertIn('t>Date.now()+3600000', code)
        self.assertIn('validMetricValue(x.kind,x.value)', code)
        self.assertIn('Date.parse(b.date)-Date.parse(a.date)', code)

    def test_history_nonrank_values_are_validated(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        code = html[html.index("function recs("):html.index("function isFresh(")]
        self.assertIn('validMetricValue(x.kind,x.value)', code)
        helper = html[html.index('function validMetricValue('):html.index('function latest(')]
        self.assertIn('/^[0-9]+$/.test(value.trim())', helper)
        self.assertIn('Number.isInteger(v)&&v>=0', helper)

    def test_latest_and_history_share_metric_validation(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        latest = html[html.index("function latest("):html.index("function recs(")]
        history = html[html.index("function recs("):html.index("function isFresh(")]
        self.assertIn("validMetricValue(kind,x.value)", latest)
        self.assertIn("validMetricValue(x.kind,x.value)", history)

    def test_metric_strings_require_plain_decimal_digits(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        code = html[html.index("function validRankValue("):
                    html.index("function latest(")]
        scenario = r"""
const assert = require("node:assert/strict");
assert.equal(validRankValue("12"), true);
assert.equal(validRankValue("1e2"), false);
assert.equal(validRankValue("0x10"), false);
assert.equal(validRankValue(" "), false);
assert.equal(validMetricValue("steam","1200"), true);
assert.equal(validMetricValue("steam","0x10"), false);
assert.equal(validMetricValue("steam",0), true);
"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "metric-format.cjs"
            path.write_text(code + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(path)], check=True,
                           capture_output=True, text=True)

    def test_latest_and_history_runtime_agree(self):
        """Latest and history must select the same valid observation set."""
        html = (SITE / "index.html").read_text(encoding="utf-8")
        code = html[html.index("function validRankValue("):
                    html.index("function isFresh(")]
        scenario = r"""
const assert = require("node:assert/strict");
const now = new Date().toISOString();
const future = new Date(Date.now()+86400000).toISOString();
const records = [
 {game:"ww",region:"jp",kind:"rank",store:"ios",value:7,date:now},
 {game:"ww",region:"jp",kind:"rank",store:"ios",value:2,date:future},
 {game:"ww",region:"jp",kind:"rank",store:"ios",value:"0x10",date:now},
 {game:"ww",region:"jp",kind:"rank",store:"ios",value:true,date:now}
];
const autoRecords = [];
assert.equal(latest("ww","jp","rank","ios").value,7);
assert.deepEqual(recs("ww","rank").map(x=>x.value),[7]);
"""
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "history-consistency.cjs"
            p.write_text(code + "\n" + scenario, encoding="utf-8")
            subprocess.run(["node", str(p)], check=True,
                           capture_output=True, text=True)

    def test_release_calendar_discloses_source_coverage(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        calendar = html[html.index("function releaseCalendar("):
                        html.index("function eventTiming(")]
        self.assertIn('publishedEvents.filter(e=>e.verification==="official").length', calendar)
        self.assertIn("外部資料は公式確定情報ではありません", calendar)

    def test_calendar_shows_per_game_verified_coverage(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        section = html[html.index("function releaseCalendar("):
                       html.index("function home(", html.index("function releaseCalendar("))]
        self.assertIn('const byGame=G.map(g=>', section)
        self.assertIn('items.filter(e=>e.verification==="official").length', section)
        self.assertIn('作品別（確認済/総数）', section)
        self.assertIn('公式告知の転載が含まれます', section)

    def test_source_tiers_runtime(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        code = html[html.index("function eventSourceTier("):
                    html.index("function eventSource(", html.index("function eventSourceTier("))]
        scenario = r"""
const assert = require("node:assert/strict");
const source = url => ({source_url:url});
assert.equal(eventSourceTier(source("https://wutheringwaves.kurogames.com/jp/main/news")),"運営公式サイト");
assert.equal(eventSourceTier(source("https://endfield.gryphline.com/en/news")),"運営公式サイト");
assert.equal(eventSourceTier(source("https://nte.perfectworld.com/jp/")),"運営公式サイト");
assert.equal(eventSourceTier(source("https://prtimes.jp/main/html/rd/p/00001.html")),"プレスリリース");
assert.equal(eventSourceTier(source("https://wutheringwaves.gg/banner/")),"外部サイト・転載・SNS");
assert.equal(eventSourceTier(source("https://fakekurogames.com/banner")),"外部サイト・転載・SNS");
assert.equal(eventSourceTier(source("")),"出典URL不明");
"""
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"source-tiers.cjs"
            file.write_text(code+"\n"+scenario,encoding="utf-8")
            subprocess.run(["node",str(file)],check=True,capture_output=True,text=True)

    def test_all_reruns_have_earlier_matching_debuts(self):
        events = self.read("release-events.json")["events"]

        def canonical_name(name):
            return re.sub(r"（[^）]*(?:復刻|ピックアップ|集録祈願|周年)[^）]*）", "", name).strip()

        debuts = {}
        for event in events:
            if event.get("type") != "character" or event.get("event_kind") != "debut":
                continue
            key = (event["game"], canonical_name(event["version"]))
            debuts[key] = min(debuts.get(key, event["date"]), event["date"])

        reruns = [
            event for event in events
            if event.get("type") == "character" and event.get("event_kind") == "rerun"
        ]
        self.assertGreaterEqual(len(reruns), 300, "Historical rerun coverage unexpectedly shrank")
        unmatched = [
            f"{event['id']} ({event['version']})"
            for event in reruns
            if debuts.get((event["game"], canonical_name(event["version"])), "9999-12-31")
            >= event["date"]
        ]
        self.assertEqual(unmatched, [], "Rerun has no earlier debut in the dataset")

    def test_corrected_character_names_and_false_schedule(self):
        events = {event["id"]: event for event in self.read("release-events.json")["events"]}
        self.assertEqual(events["history-ww-2026-05-21-393"]["version"], "ダーニャ")
        self.assertEqual(events["history-zzz-2024-12-18-27"]["version"], "浅羽悠真")
        self.assertNotIn("scheduled-nte-1.4-akane-rin", events)

    def test_other_feeds(self):
        for filename in ("steam-data.json", "youtube-data.json", "release-candidates.json"):
            data = self.read(filename)
            self.assertIsInstance(data, dict)
            self.assertIn("updated_at", data)
        steam = self.read("steam-data.json")
        self.assertIsInstance(steam["records"], list)
        self.assertGreaterEqual(len(steam["records"]), 32, "Steam history fell below verified archive baseline")
        keys = [(row["game"], row["date"]) for row in steam["records"]]
        self.assertEqual(len(keys), len(set(keys)), "duplicate Steam observations")
        for row in steam["records"]:
            self.assertIn(row["game"], {"ww", "zzz", "nte"})
            self.assertEqual(row["store"], "steam")
            self.assertIs(type(row["value"]), int)
            self.assertGreaterEqual(row["value"], 0)
        self.assertIsInstance(self.read("youtube-data.json")["records"], list)
        self.assertIsInstance(self.read("release-candidates.json")["candidates"], list)


class Genshin2026FourStarOfficialTests(unittest.TestCase):
    """2026 rate-up roster checked against COGNOSPHERE's dated notices."""

    def test_13_phases_39_official_fourstar_slots(self):
        import json
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        all_events = json.loads(
            (repo_root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        expected = {
            "2026-01-14": ("セトス", "フィッシュル", "イファ"),
            "2026-02-03": ("イルーガ", "アイノ", "ゴロー"),
            "2026-02-25": ("ベネット", "香菱", "スクロース"),
            "2026-03-17": ("ダリア", "キャンディス", "シャルロット"),
            "2026-04-08": ("イルーガ", "アイノ", "ノエル"),
            "2026-04-28": ("行秋", "綺良々", "ヤフォダ"),
            "2026-05-20": ("プルーネ", "レザー", "フィッシュル"),
            "2026-06-09": ("ミカ", "香菱", "ベネット"),
            "2026-07-01": ("北斗", "ディオナ", "フレミネ"),
            "2026-07-21": ("ヤフォダ", "オロルン", "セトス"),
            "2026-08-12": ("アリョーシャ", "ディオナ", "フレミネ"),
            "2026-09-01": ("アイノ", "イアンサ", "藍硯"),
            "2026-09-23": ("ディオナ", "ファルザン", "重雲"),
        }
        pools = [
            e for e in all_events
            if e.get("game") == "gi"
            and e.get("date", "").startswith("2026-")
            and e.get("banner_type") == "event_wish_four_star"
        ]
        self.assertEqual(len(pools), 39)
        self.assertEqual(len({e["id"] for e in pools}), 39)
        self.assertEqual(len({(e["date"], e["version"]) for e in pools}), 39)
        self.assertEqual({e["date"] for e in pools}, set(expected))
        for date, roster in expected.items():
            pool = [e for e in pools if e["date"] == date]
            with self.subTest(date=date):
                self.assertEqual({e["version"] for e in pool}, set(roster))
                self.assertEqual({e["phase"] for e in pool},
                                 {"first" if date in
                                  ("2026-01-14", "2026-02-25", "2026-04-08",
                                   "2026-05-20", "2026-07-01", "2026-08-12",
                                   "2026-09-23") else "second"})
                self.assertTrue(all(e["rarity"] == 4 and e["type"] == "character"
                                    and e["verification"] == "official" and
                                    "prtimes.jp/main/html/rd/p/" in e["source_url"]
                                    for e in pool))
        debuts = {e["version"] for e in pools if e.get("event_kind") == "debut"}
        self.assertEqual(debuts, {"イルーガ", "プルーネ", "アリョーシャ"})
        self.assertEqual(
            {e["version"] for e in pools if e["date"] == "2026-08-12"},
            {"アリョーシャ", "ディオナ", "フレミネ"},
            "The COGNOSPHERE announcement must take precedence over a conflicting third-party table.",
        )


class HsrAndZenlessLowRarityRosterTests(unittest.TestCase):
    """2023–26 4-star/A-rank pools do not distort five-star rankings."""

    def test_archived_low_rarity_roster_counts_and_provenance(self):
        import json
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        events = json.loads(
            (root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        hsr = [e for e in events if e.get("banner_type") == "event_warp_four_star"]
        zzz = [e for e in events if e.get("banner_type") == "exclusive_channel_a_rank" and e["date"] < "2026-01-01"]
        hsr_older = [e for e in hsr if e["date"] < "2025-01-01"]
        zzz_older = [e for e in zzz if e["date"] < "2025-01-01"]
        self.assertEqual(len(hsr), 177)
        self.assertEqual(len(zzz), 56)
        self.assertEqual(len(hsr_older), 90)
        self.assertEqual(len(zzz_older), 20)
        self.assertEqual(len({e["date"] for e in hsr_older}), 30)
        self.assertEqual(len({(e["date"],e["featured_five_star"]) for e in zzz_older}), 10)
        self.assertEqual(len({e["date"] for e in hsr}), 59)
        self.assertEqual(len({(e["date"],e["featured_five_star"]) for e in zzz}), 28)
        self.assertEqual({e["version"] for e in zzz
                          if e["date"] == "2024-12-18" and
                          e["featured_five_star"] == "雅"}, {"蒼角", "パイパー"})
        self.assertEqual({e["version"] for e in zzz
                          if e["date"] == "2024-12-18" and
                          e["featured_five_star"] == "浅羽悠真"}, {"ルーシー", "セス"})
        for event in hsr + zzz:
            with self.subTest(id=event["id"]):
                self.assertEqual(event["type"], "character")
                self.assertEqual(event["verification"], "secondary")
                self.assertTrue(event["source_url"].startswith("https://"))
                self.assertTrue(event["date_basis"])
                self.assertTrue(event["review_note"])
                self.assertTrue(event["corroborating_sources"])
        for date in {e["date"] for e in hsr}:
            self.assertEqual(sum(e["date"] == date for e in hsr), 3)
        for date, featured in {(e["date"],e["featured_five_star"]) for e in zzz}:
            self.assertEqual(sum(e["date"] == date and
                                 e["featured_five_star"] == featured for e in zzz), 2)

    def test_new_types_are_excluded_from_normal_revenue_rankings(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        html = (root / "gacha-wars" / "index.html").read_text(encoding="utf-8")
        for banner_type in ("event_warp_four_star", "exclusive_channel_a_rank"):
            self.assertGreaterEqual(html.count('"' + banner_type + '"'), 4)
        self.assertIn('["exclusive_channel_a_rank","exclusive_channel_a_default","featured_convene_four_star","collab_convene_four_star"].includes(e.banner_type)?e.featured_five_star||""',html)
        self.assertIn('イベント跳躍・共有★4枠',html)
        self.assertIn('独占変調・A級PU',html)


class Hsr2025Zenless2025AdditionalRegressionTests(unittest.TestCase):
    """2025–26 source-labeled roster additions and phase grouping."""

    def test_new_123_slots_and_2025_26_phase_ranges(self):
        import json
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        events = json.loads(
            (root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        self.assertEqual(len(events), 1607)
        hsr_new = [x for x in events
                   if x.get("banner_type") == "event_warp_four_star"
                   and x["date"] >= "2025-01-01"]
        zzz_new = [x for x in events
                   if x.get("banner_type") == "exclusive_channel_a_rank"
                   and "2025-01-01" <= x["date"] < "2026-01-01"]
        self.assertEqual(len(hsr_new), 87)
        self.assertEqual(len(zzz_new), 36)
        self.assertEqual(len({x["date"] for x in hsr_new}), 29)
        self.assertEqual(len({(x["date"], x["featured_five_star"]) for x in zzz_new}), 18)
        self.assertEqual(sum(x["date"].startswith("2025-") for x in hsr_new), 51)
        self.assertEqual(sum(x["date"].startswith("2026-") for x in hsr_new), 36)
        self.assertTrue(all(x["verification"] == "secondary" for x in hsr_new + zzz_new))
        self.assertTrue(all(x["date_basis"].startswith("first_party_") for x in hsr_new + zzz_new))
        for e in hsr_new:
            self.assertEqual(e["source_url"],
                             "https://www.pcgamer.com/games/rpg/honkai-star-rail-banner-next-current/")
        for e in zzz_new:
            self.assertTrue(e["source_url"].startswith(
                "https://game8.co/games/Zenless-Zone-Zero/archives/"))
        self.assertEqual({e["version"] for e in hsr_new if e["date"] == "2025-12-17"},
                         {"ギャラガー", "ルカ", "三月なのか"})
        self.assertEqual({e["version"] for e in hsr_new if e["date"] == "2026-04-22"},
                         {"ギャラガー", "雪衣", "フック"})
        self.assertEqual({e["version"] for e in zzz_new if e["date"] == "2025-10-15"},
                         {"狛野真斗", "パイパー"})
        self.assertEqual({e["version"] for e in zzz_new if e["date"] == "2025-12-30"},
                         {"ニコ", "ルーシー", "アンビー", "ベン"})
        self.assertEqual({e["version"] for e in zzz_new
                          if e["date"] == "2025-12-30"
                          and e["featured_five_star"] == "葉瞬光"},
                         {"ニコ", "ルーシー"})
        self.assertEqual({e["version"] for e in zzz_new
                          if e["date"] == "2025-12-30"
                          and e["featured_five_star"] == "照"},
                         {"アンビー", "ベン"})
        self.assertEqual(
            {e["version"] for e in zzz_new if e.get("event_kind") == "debut"},
            {"プルクラ", "潘引壺", "狛野真斗"})
        self.assertEqual(
            len({(e["game"], e["date"], e["version"], e["featured_five_star"]) for e in hsr_new + zzz_new}),
            123)


class WutheringOfficialFourStarConveneTests(unittest.TestCase):
    """Verify 14 KURO GAMES first-party ★4 rosters, including anniversary distinction."""

    def test_14_official_three_person_pools(self):
        import json
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        events = json.loads(
            (root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        current = [e for e in events if e.get("game") == "ww" and
                   e["id"].startswith("ww-four-pu-") and
                   e.get("banner_type") in (
                       "featured_convene_four_star", "anniversary_convene_four_star")]
        self.assertEqual(len(current), 42)
        self.assertEqual(len({e["date"] for e in current}), 14)
        self.assertEqual(sum(e["banner_type"] == "anniversary_convene_four_star"
                             for e in current), 3)
        self.assertEqual(sum(e["banner_type"] == "featured_convene_four_star"
                             for e in current), 39)
        self.assertTrue(all(e["verification"] == "official" and
                            e["rarity"] == 4 and
                            e["source_url"].startswith(
                              "https://wutheringwaves.kurogames.com/en/main/news/detail/")
                            for e in current))
        for date in {e["date"] for e in current}:
            self.assertEqual(len([e for e in current if e["date"] == date]), 3)
        checks = {
            "2024-06-28": {"散華", "丹瑾", "秧秧"},
            "2024-12-12": {"灯灯", "白芷", "淵武"},
            "2025-04-29": {"灯灯", "桃祈", "淵武"},
            "2025-12-11": {"卜霊", "丹瑾", "熾霞"},
            "2026-07-10": {"丹瑾", "熾霞", "アールト"},
        }
        for date, roster in checks.items():
            self.assertEqual({e["version"] for e in current if e["date"] == date}, roster)
        self.assertEqual({e["version"] for e in current
                          if e.get("event_kind") == "debut"}, {"灯灯", "卜霊"})

    def test_convene_types_are_excluded_from_normal_sales_comparisons(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        html = (root / "gacha-wars" / "index.html").read_text(encoding="utf-8")
        for kind in ("featured_convene_four_star", "anniversary_convene_four_star"):
            self.assertGreaterEqual(html.count('"' + kind + '"'), 4)
        self.assertIn('共鳴者集音・★4ピックアップ', html)
        self.assertIn('周年選択集音・共有★4枠', html)


class WutheringSecondary108BatchTests(unittest.TestCase):
    """108 nonofficial-labeled roster slots: no false source upgrades or sales duplication."""

    def test_36_banner_groups_108_slots_and_provenance(self):
        import pathlib
        import json
        root = pathlib.Path(__file__).resolve().parents[1]
        events = json.loads(
            (root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        self.assertEqual(len(events), 1607)
        added = [e for e in events if e["id"].startswith("ww-extra-four-")]
        self.assertEqual(len(added), 108)
        self.assertEqual({(e["verification"],e["rarity"]) for e in added},
                         {("secondary", 4)})
        types = {
            "featured_convene_four_star": 96,
            "anniversary_convene_four_star": 3,
            "collab_convene_four_star": 6,
            "reverb_convene_four_star": 3,
        }
        self.assertEqual({kind: sum(e["banner_type"] == kind for e in added)
                          for kind in types}, types)
        self.assertEqual({year: sum(e["date"].startswith(year) for e in added)
                          for year in ("2024","2025","2026")},
                         {"2024":21,"2025":45,"2026":42})
        self.assertEqual(len({e["date"] for e in added}), 32)
        groups = {}
        for e in added:
            k=(e["date"],e["banner_type"],e["featured_five_star"])
            groups.setdefault(k, []).append(e)
            self.assertEqual(e["event_kind"], "featured_banner")
            self.assertTrue(e["source_url"].startswith("https://"))
            self.assertNotIn("wutheringwaves.kurogames.com", e["source_url"])
            self.assertTrue(e.get("date_basis"))
            self.assertTrue(e.get("review_note"))
            self.assertIsInstance(e.get("corroborating_sources"), list)
            self.assertTrue(e["corroborating_sources"])
        self.assertEqual(len(groups),36)
        for key,group in groups.items():
            with self.subTest(key=key):
                self.assertEqual(len(group),3)
                self.assertEqual(len({e["version"] for e in group}),3)
                self.assertEqual(len({e["source_url"] for e in group}),1)
        self.assertEqual({e["version"] for e in added
                          if e["date"] == "2026-06-08"
                          and e["featured_five_star"] == "レベッカ"},
                         {"灯灯","釉瑚","桃祈"})
        self.assertEqual({e["version"] for e in added
                          if e["date"] == "2026-07-10"
                          and e["banner_type"] == "reverb_convene_four_star"},
                         {"卜霊","散華","秧秧"})
        self.assertEqual({e["version"] for e in added
                          if e["date"] == "2025-05-22"
                          and e["banner_type"] == "anniversary_convene_four_star"},
                         {"丹瑾","秧秧","モルトフィー"})
        self.assertEqual({e["version"] for e in added
                          if e["date"] == "2026-09-30"},
                         {"卜霊","桃祈","釉瑚"})

    def test_ui_does_not_credit_special_convenes_as_single_character_revenue(self):
        import pathlib
        root=pathlib.Path(__file__).resolve().parents[1]
        html=(root / "gacha-wars" / "index.html").read_text(encoding="utf-8")
        for kind in ("collab_convene_four_star","reverb_convene_four_star"):
            self.assertGreaterEqual(html.count('"' + kind + '"'),4)
        self.assertIn("コラボ専用集音・★4枠",html)
        self.assertIn("特別選択集音・★4枠",html)
        self.assertIn("対象★5：",html)
        self.assertIn('!specialTypes.includes(ev.banner_type)',html)


class WEngine2025AndAgent2026RegressionTests(unittest.TestCase):
    """S-rank W-Engine and A-rank agent histories remain separate from sales."""

    def test_107_new_records_and_official_source_labeled(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        events = json.loads(
            (root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        self.assertEqual(len(events), 1607)
        added = [x for x in events
                 if x["id"].startswith(("zzz-a-2026-backfill-", "zzz-wengine-20"))]
        self.assertEqual(len(added), 107)
        agents = [x for x in added if x["type"] == "character"]
        engines = [x for x in added if x["type"] == "weapon"]
        self.assertEqual(len(agents), 38)
        self.assertEqual(len(engines), 69)
        self.assertEqual(sum(x["rarity"] == "S" for x in engines), 23)
        self.assertEqual(sum(x["rarity"] == "A" for x in engines), 46)
        self.assertEqual(len({(x["date"], x["featured_five_star"]) for x in engines}), 23)
        self.assertEqual(sum(x["verification"] == "official" for x in added), 62)
        self.assertEqual(sum(x["verification"] == "secondary" for x in added), 45)
        self.assertEqual(sum(bool(x.get("default_rate_up")) for x in added), 20)
        for row in added:
            with self.subTest(id=row["id"]):
                self.assertTrue(row["date_basis"])
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertTrue(row["review_note"])
                self.assertTrue(row["corroborating_sources"])
                self.assertEqual(row["event_kind"], "featured_banner")
        self.assertEqual({x["version"] for x in agents if x["date"] == "2026-02-06"},
                         {"カリン", "ビリー"})
        self.assertEqual({x["version"] for x in agents if x["date"] == "2026-09-30"},
                         {"カリン", "ビリー"})
        self.assertEqual({x["version"] for x in engines
                          if x["date"] == "2026-09-30" and x["rarity"] == "S"},
                         {"Crimson Moon Casket", "Frostfall Sickle"})
        self.assertEqual({x["version"] for x in agents if x["date"] == "2026-08-19"},
                         {"蒼角", "ルーシー"})
        for date, parent in {(x["date"], x["featured_five_star"]) for x in engines}:
            self.assertEqual(sum(x["date"] == date and
                                 x["featured_five_star"] == parent for x in engines), 3)

    def test_weapons_visible_but_not_part_of_character_sales(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        html = (root / "gacha-wars" / "index.html").read_text(encoding="utf-8")
        self.assertIn("function weaponHistory()", html)
        self.assertIn("武器・音動機ガチャ履歴（キャラ戦績と分離）", html)
        self.assertIn('["version","character","weapon"].includes(x.type)', html)
        self.assertIn('"ww_weapon_anniversary_five","ww_weapon_anniversary_four","ww_weapon_collab_five"', html)
        self.assertIn('初期設定・ユーザー変更可', html)
        self.assertIn('+weaponHistory()', html)


class ArchivedWEngine42BannersTests(unittest.TestCase):
    """42 historical ZZZ W-Engine channels are separate and provenance-labeled."""

    def test_archived_126_weapon_slots_and_no_duplicates(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        events = json.loads(
            (root / "gacha-wars" / "release-events.json").read_text(encoding="utf-8")
        )["events"]
        self.assertEqual(len(events), 1607)
        rows = [x for x in events if x["id"].startswith("zzz-wengine-archive-")]
        self.assertEqual(len(rows), 126)
        self.assertEqual(sum(x["rarity"] == "S" for x in rows), 42)
        self.assertEqual(sum(x["rarity"] == "A" for x in rows), 84)
        self.assertEqual({year: sum(x["date"].startswith(year) for x in rows)
                          for year in ("2024", "2025", "2026")},
                         {"2024":30, "2025":90, "2026":6})
        self.assertEqual({x["verification"] for x in rows}, {"secondary"})
        self.assertEqual({x["source_url"] for x in rows},
                         {"https://zenless-zone-zero.fandom.com/wiki/W-Engine_Channel/History"})
        groups = {}
        for x in rows:
            key = (x["date"], x["featured_five_star"])
            groups.setdefault(key, []).append(x)
            self.assertEqual(x["type"], "weapon")
            self.assertTrue(x["date_basis"].startswith("first_party_"))
            self.assertTrue(x["corroborating_sources"])
            self.assertTrue(x["review_note"])
        self.assertEqual(len(groups), 42)
        self.assertEqual(len({(x["date"],x["version"],x["featured_five_star"]) for x in rows}), 126)
        for (date, parent), group in groups.items():
            with self.subTest(date=date, parent=parent):
                self.assertEqual(len(group), 3)
                self.assertEqual({x["rarity"] for x in group}, {"S", "A"})
                self.assertEqual(sum(x["rarity"] == "S" for x in group), 1)
                self.assertEqual(len({x["version"] for x in group}), 3)
        self.assertEqual({x["version"] for x in rows
                          if x["date"] == "2024-12-18" and
                          x["featured_five_star"] == "雅"},
                         {"Hailstorm Shrine", "Roaring Ride", "Bashful Demon"})
        self.assertEqual({x["version"] for x in rows
                          if x["date"] == "2025-12-30" and
                          x["featured_five_star"] == "葉瞬光"},
                         {"Cloudcleave Radiance", "The Vault", "Kaboom the Cannon"})
        self.assertFalse(any(x["date"] == "2026-07-08" for x in rows))


class Wuthering2024To2026WeaponConveneTests(unittest.TestCase):
    """102 WW weapon rows cover 66 regular, 10 anniversary, 2 collab, 24 four-star."""

    def test_wuthering_102_weapon_records_and_references(self):
        import pathlib
        import json
        root=pathlib.Path(__file__).resolve().parents[1]
        events=json.loads((root/"gacha-wars"/"release-events.json").read_text(encoding="utf-8"))["events"]
        self.assertEqual(len(events),1607)
        rows=[e for e in events if e["id"].startswith("ww-weapon-")]
        self.assertEqual(len(rows),102)
        counts={"ww_weapon_five":66,"ww_weapon_anniversary_five":10,
                "ww_weapon_collab_five":2,"ww_weapon_four":18,
                "ww_weapon_anniversary_four":6}
        self.assertEqual({k:sum(e["banner_type"]==k for e in rows) for k in counts},counts)
        self.assertEqual(sum(e["verification"]=="official" for e in rows),16)
        self.assertEqual(sum(e["verification"]=="secondary" for e in rows),86)
        self.assertEqual(sum(e["rarity"]==5 for e in rows),78)
        self.assertEqual(sum(e["rarity"]==4 for e in rows),24)
        self.assertTrue(all(e["type"]=="weapon" for e in rows))
        self.assertTrue(all(e["source_url"].startswith("https://") for e in rows))
        self.assertTrue(all(e["featured_five_star"] for e in rows))
        self.assertTrue(all(e["date_basis"] for e in rows))
        self.assertEqual(len({e["id"] for e in rows}),102)
        for date,weapon in [
                ("2024-05-23","Verdant Summit"),
                ("2025-02-13","Luminous Hymn"),
                ("2025-07-24","Lethean Elegy"),
                ("2025-11-20","Kumokiri"),
                ("2026-06-13","Freeze Frame")]:
            self.assertEqual(sum(e["date"]==date and e["version"]==weapon and
                                 e["banner_type"]=="ww_weapon_five" for e in rows),1)

    def test_anniversary_is_one_selectable_pool_not_five_independent_banners(self):
        import pathlib
        import json
        root=pathlib.Path(__file__).resolve().parents[1]
        events=json.loads((root/"gacha-wars"/"release-events.json").read_text(encoding="utf-8"))["events"]
        rows=[e for e in events if e["id"].startswith("ww-weapon-anniv-") or
              e.get("banner_type")=="ww_weapon_anniversary_four"]
        for date,phase in [("2025-04-29","I"),("2025-05-22","II")]:
            group=[e for e in rows if e["date"]==date]
            self.assertEqual(len(group),8)
            self.assertEqual(sum(e["rarity"]==5 for e in group),5)
            self.assertEqual(sum(e["rarity"]==4 for e in group),3)
            self.assertEqual({e["featured_five_star"] for e in group},
                             {"周年限定選択武器・第"+phase+"期"})
            self.assertEqual({e["weapon_banner_group"] for e in group},
                             {"Anniversary Weapon Convene Phase "+phase})
            self.assertEqual({e["verification"] for e in group},{"official"})
        html=(root/"gacha-wars"/"index.html").read_text(encoding="utf-8")
        self.assertIn("武器・音動機ガチャ履歴（キャラ戦績と分離）",html)
        self.assertIn('"ww_weapon_anniversary_five"',html)
        self.assertIn("選択可能な★5武器5本",html)
        self.assertIn('e.rarity==="S"||e.rarity===5',html)

    def test_low_four_star_early_first_party_boundary(self):
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        events=json.loads((root/"gacha-wars"/"release-events.json").read_text(encoding="utf-8"))["events"]
        early=[e for e in events if e.get("banner_type")=="ww_weapon_four" and e["date"]<"2024-07-01"]
        self.assertEqual(len(early),9)
        self.assertEqual({e["date"] for e in early},{"2024-05-23","2024-06-06","2024-06-28"})
        self.assertTrue(all(e["verification"]=="secondary" for e in early))


    def test_genshin_weapon_history_supplement_has_105_complete_banners(self):
        """The secondary-sourced weapon archive must stay separate from character banners."""
        data = json.loads((SITE / "gi-weapon-history.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "gacha-wars-gi-weapons-v1")
        self.assertEqual(data["verification"], "secondary")
        self.assertTrue(data["source"].startswith("https://github.com/MadeBaruna/paimon-moe/"))
        banners = data["banners"]
        self.assertEqual(len(banners), 105)
        self.assertEqual(len(set(b["date"] for b in banners)), 105)
        self.assertEqual(sum(len(b["five"]) for b in banners), 210)
        self.assertEqual(sum(len(b["four"]) for b in banners), 525)
        for b in banners:
            self.assertRegex(b["date"], r"^20\d{2}-\d{2}-\d{2}$")
            self.assertLessEqual(b["date"], "2026-10-12")
            self.assertEqual(len(b["five"]), 2)
            self.assertEqual(len(b["four"]), 5)
            self.assertEqual(len(set(b["five"] + b["four"])), 7)
            self.assertTrue(all(x and isinstance(x, str) for x in b["five"] + b["four"]))

    def test_genshin_weapon_display_is_secondary_and_does_not_affect_character_rankings(self):
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn('"gi-weapon-history.json",parseGenshinWeaponArchive', html)
        self.assertIn('fetch("./"+file,{cache:"no-store"})', html)
        self.assertIn('function parseGenshinWeaponArchive(data)', html)
        self.assertIn('data.verification!=="secondary"', html)
        self.assertIn('"gi_weapon_five","gi_weapon_four"', html)
        self.assertIn('verification:"secondary"', html)
        self.assertIn('weaponPage*perPage', html)
        self.assertIn('const events=[...publishedEvents,...updateEvents].filter(e=>e.type==="character"', html)



class HsrLightconeSupplementTests(unittest.TestCase):
    def test_68_lightcone_groups_341_slots_and_secondary_provenance(self):
        info=json.loads((SITE/"hsr-lightcone-history.json").read_text(encoding="utf-8"))
        self.assertEqual(info["schema"],"gacha-wars-hsr-lightcone-history-v1")
        self.assertEqual(info["verification"],"secondary")
        self.assertTrue(info["source"].startswith("https://github.com/FuriaPaladins/"))
        groups=info["banners"]
        self.assertEqual(len(groups),68)
        self.assertEqual(sum(g["kind"]=="standard" for g in groups),66)
        self.assertEqual(sum(g["kind"]=="special" for g in groups),2)
        self.assertEqual(sum(len(g["five"]) for g in groups),143)
        self.assertEqual(sum(len(g["four"]) for g in groups),198)
        self.assertEqual(len({(g["date"],g["kind"],g["banner_index"]) for g in groups}),68)
        for g in groups:
            self.assertRegex(g["date"],r"^20\d{2}-\d{2}-\d{2}$")
            self.assertLessEqual(g["date"],"2026-10-12")
            self.assertEqual(len(g["four"]),3 if g["kind"]=="standard" else 0)
            self.assertTrue(all(x.get("name") and str(x.get("id","")).isdigit() for x in g["five"]+g["four"]))
        self.assertEqual(groups[0]["date"],"2023-04-26")
        self.assertTrue(any(g["source_start"].startswith("2023-04-25") for g in groups))

    def test_hsr_archive_merger_keeps_characters_and_special_banners_separate(self):
        site=(SITE/"index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./"+file,{cache:"no-store"})',site)
        self.assertIn('"hsr-lightcone-history.json",parseHsrLightconeArchive',site)
        self.assertIn('"hsr_lightcone_special_five"',site)
        self.assertIn('verification:"secondary"',site)
        self.assertIn("同時開催枠を資料上で合算（選択式ではない）",site)
        self.assertIn('String(a.parent||a.items[0]?.event_banner_name||"")',site)
        self.assertIn('const events=[...publishedEvents,...updateEvents].filter(e=>e.type==="character"',site)

    def test_hsr_archive_parser_runtime_and_group_collisions(self):
        source=(SITE/"index.html").read_text(encoding="utf-8")
        parser=source[source.index("function parseHsrLightconeArchive(data){"):source.index("async function loadEvents(){")]
        script=r'''
const assert=require("node:assert/strict");
const fs=require("node:fs");
'''+parser+r'''
const d=JSON.parse(fs.readFileSync("gacha-wars/hsr-lightcone-history.json","utf8"));
const events=parseHsrLightconeArchive(d);
assert.equal(events.length,341);
assert.equal(new Set(events.map(e=>e.id)).size,341);
assert.equal(events.filter(e=>e.rarity===5).length,143);
assert.equal(events.filter(e=>e.rarity===4).length,198);
assert.ok(events.every(e=>e.verification==="secondary"));
assert.ok(events.every(e=>e.type==="weapon"&&e.game==="hsr"));
const map=new Map();
for(const e of events){
 const key=[e.game,e.date,e.version_group||"",e.phase||"",e.featured_five_star||"",e.weapon_banner_group||""].join("|");
 if(!map.has(key))map.set(key,[]);
 map.get(key).push(e);
}
assert.equal(map.size,68);
const same= [...map.entries()].filter(([k])=>k.includes("2026-02-13"));
assert.equal(same.length,2);
assert.ok(same.every(([_,items])=>items[0].weapon_banner_group));
assert.ok(events.some(e=>e.special_banner));
assert.ok(events.some(e=>e.multiple_concurrent));
'''
        result=subprocess.run(["node","-e",script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__ == "__main__":
    unittest.main()
