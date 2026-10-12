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
            self.assertIn(event["type"], {"character", "version"})
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
                semantic_keys.append((event["game"], event["version"], event["date"]))
        self.assertEqual(len(semantic_keys), len(set(semantic_keys)),
                         "duplicate character banner on the same date")


    def test_special_banner_types_are_explicit_and_separate(self):
        events = self.read("release-events.json")["events"]
        special_types = {
            "anniversary_convene", "special_rerun", "event_wish_four_star",
            "chronicled_wish", "standard_character_event"
        }
        specials = [e for e in events if e.get("banner_type")]
        self.assertGreaterEqual(len(specials), 20)
        for event in specials:
            self.assertIn(event["banner_type"], special_types)
            self.assertEqual(event["type"], "character")
        html = (SITE / "index.html").read_text(encoding="utf-8")
        # Both the actual group filter and the coverage counters must agree.
        for kind in special_types:
            self.assertGreaterEqual(html.count('"' + kind + '"'), 2, kind)

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
        self.assertIn('e.banner_type==="special_rerun"?"特別復刻枠"', ranking)

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
        self.assertGreaterEqual(len(checked), 52)
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
        for special_type in ("chronicled_wish", "event_wish_four_star",
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

if __name__ == "__main__":
    unittest.main()
