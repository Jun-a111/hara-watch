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
        self.assertGreaterEqual(len(data["events"]), 505, "published release archive shrank")
        ids = [e["id"] for e in data["events"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate release event IDs")
        # A large archive is not useful if the same banner is counted twice or
        # entries silently lose their provenance.  Keep these checks independent
        # of the total baseline: the archive can grow without hiding corruption.
        semantic_keys = []
        for event in data["events"]:
            self.assertIn(event["game"], {"gi", "hsr", "zzz", "ww", "nte", "end"})
            self.assertIn(event["type"], {"character", "version"})
            self.assertRegex(event["date"], r"^\\d{4}-\\d{2}-\\d{2}$")
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
