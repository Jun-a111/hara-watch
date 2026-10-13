"""Guard against promoting secondary HSR banner records to official without first-party evidence."""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "gacha-wars"

OFFICIAL_FILES = [
    "hsr-remaining-2023-2024-official.json",
    "hsr-bilibili-fourstar-official-overrides.json",
    "hsr-official-weibo-fourstar-overrides.json",
    "hsr-2026-spring-summer-fourstar-official.json",
    "hsr-2025-2026-fourstar-official-overrides.json",
    "hsr-2025-fourstar-official-overrides.json",
    "hsr-2024-fourstar-official-overrides.json",
    "hsr-2023-fourstar-official-overrides.json",
]


def read(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


class HsrFourStarEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = read("release-events.json")["events"]
        cls.original = {
            e["id"]: e for e in original
            if e.get("game") == "hsr"
            and e.get("type") == "character"
            and e.get("rarity") == 4
            and e.get("banner_type") == "event_warp_four_star"
        }

    def test_no_double_promotion_and_exact_original_rosters(self):
        self.assertEqual(len(self.original), 177)
        seen = set()
        for filename in OFFICIAL_FILES:
            doc = read(filename)
            self.assertEqual(doc["verification"], "official", filename)
            self.assertEqual(len(doc["groups"]), doc["group_count"], filename)
            self.assertEqual(doc["count"], 3 * doc["group_count"], filename)
            for group in doc["groups"]:
                names = group.get("names_ja", group.get("names"))
                self.assertEqual(len(names), 3, filename)
                self.assertEqual(len(group["ids"]), 3, filename)
                self.assertTrue(group.get("source_url", "").startswith("https://"), filename)
                for i, eid in enumerate(group["ids"]):
                    self.assertNotIn(eid, seen, eid)
                    seen.add(eid)
                    actual = self.original[eid]
                    self.assertEqual(actual["verification"], "secondary", eid)
                    self.assertEqual(actual["date"], group["date"], eid)
                    self.assertEqual(actual["version"], names[i], eid)
                    self.assertEqual(actual["featured_five_star"], group["featured_five_star"], eid)
        self.assertEqual(len(seen), 135)
        self.assertEqual(len(self.original) - len(seen), 42)

    def test_secondary_mirrors_never_upgrade_verification(self):
        doc = read("hsr-secondary-corroboration-2025.json")
        self.assertEqual(doc["verification"], "secondary")
        self.assertEqual(doc["count"], 6)
        self.assertEqual(doc["group_count"], 2)
        all_ids = set()
        for group in doc["groups"]:
            self.assertEqual(len(group["sources"]), 1 if group["date"] == "2025-07-23" else 2)
            for i, eid in enumerate(group["ids"]):
                self.assertNotIn(eid, all_ids)
                all_ids.add(eid)
                original = self.original[eid]
                self.assertEqual(original["verification"], "secondary", eid)
                self.assertEqual(original["version"], group["names"][i], eid)
                self.assertEqual(original["date"], group["date"], eid)
                self.assertEqual(original["featured_five_star"], group["featured_five_star"], eid)
        index = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-secondary-corroboration-2025.json"', index)
        self.assertIn('function applyHsrSecondaryCorroboration(', index)
        self.assertIn('補助参考資料 ', index)
        self.assertNotIn('補助公式資料 ', index)

    def test_unread_publisher_articles_remain_pending(self):
        doc = read("hsr-publisher-notice-candidates.json")
        self.assertEqual(doc["verification"], "not_yet_verified")
        self.assertEqual(doc["count"], 36)
        self.assertEqual(doc["group_count"], 12)
        for group in doc["groups"]:
            self.assertEqual(group["status"], "publisher_notice_link_found_body_not_directly_accessible")
            self.assertTrue(group["publisher_notice_url"].startswith("https://www.miyoushe.com/"))
            for i, eid in enumerate(group["ids"]):
                self.assertEqual(self.original[eid]["verification"], "secondary")
                self.assertEqual(self.original[eid]["version"], group["names"][i])


if __name__ == "__main__":
    unittest.main()
