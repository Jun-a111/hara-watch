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

    def test_ios_history_and_integrity(self):
        data = self.read("ios-rank-data.json")
        self.assertEqual(data["schema"], "gacha-wars-ios-v1")
        rows = data["records"]
        self.assertTrue(rows)
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
        self.assertGreater(len(data["events"]), 0)
        ids = [e["id"] for e in data["events"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate release event IDs")

    def test_other_feeds(self):
        for filename in ("steam-data.json", "youtube-data.json", "release-candidates.json"):
            data = self.read(filename)
            self.assertIsInstance(data, dict)
            self.assertIn("updated_at", data)
        steam = self.read("steam-data.json")
        self.assertIsInstance(steam["records"], list)
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
