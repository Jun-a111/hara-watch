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


    def test_last_two_historical_hoyolab_links_are_traceable_but_unverified(self):
        doc = read("hsr-publisher-notice-candidates.json")
        source_links = {
            "2023-12-27": "https://www.hoyolab.com/article/23851896",
            "2025-04-09": "https://www.hoyolab.com/article/38107267",
        }
        groups = {g["date"]: g for g in doc["groups"]}
        html = (DATA / "index.html").read_text(encoding="utf-8")
        for date, url in source_links.items():
            g = groups[date]
            self.assertEqual(g["publisher_hoyolab_url"], url)
            self.assertIn("original", g["research_status"].lower())
            self.assertEqual(g["status"], "publisher_notice_link_found_body_not_directly_accessible")
            self.assertEqual(len(g["ids"]), 3)
            for eid in g["ids"]:
                self.assertEqual(self.original[eid]["verification"], "secondary")
        self.assertIn("publisher_hoyolab_url:hoyolab", html)
        self.assertIn("公式HoYoLAB", html)
        self.assertIn("★4全員の公式原文は未確認", html)

    def test_outstanding_mirrors_are_secondary_only(self):
        doc = read("hsr-outstanding-mirror-evidence.json")
        self.assertEqual(doc["schema"], "gacha-wars-hsr-outstanding-mirror-evidence-v1")
        self.assertEqual(doc["verification"], "secondary")
        self.assertEqual(doc["group_count"], 12)
        self.assertEqual(doc["count"], 36)
        expected = read("hsr-publisher-notice-candidates.json")
        by_date = {g["date"]: g for g in expected["groups"]}
        seen = set()
        for group in doc["groups"]:
            self.assertEqual(group["verification"], "secondary")
            self.assertEqual(group["notice_body_verification"], "publisher_original_not_read")
            self.assertIn(group["date"], by_date)
            self.assertEqual(group["ids"], by_date[group["date"]]["ids"])
            self.assertEqual(group["names_ja"], by_date[group["date"]]["names"])
            self.assertTrue(group["sources"])
            for item in group["sources"]:
                self.assertTrue(item["url"].startswith("https://"))
                self.assertNotEqual(item["source_type"], "publisher_original")
            for i, eid in enumerate(group["ids"]):
                self.assertNotIn(eid, seen)
                seen.add(eid)
                row = self.original[eid]
                self.assertEqual(row["verification"], "secondary")
                self.assertEqual(row["version"], group["names_ja"][i])
                self.assertEqual(row["date"], group["date"])
                self.assertEqual(row["featured_five_star"], group["featured_five_star"])
        self.assertEqual(len(seen), 36)
        html = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-outstanding-mirror-evidence.json"', html)
        self.assertIn('function applyHsrOutstandingMirrorEvidence(', html)
        self.assertIn('g.verification!=="secondary"', html)
        self.assertIn('original.verification!=="secondary"', html)


    def test_facebook_first_party_evidence_selective_upgrade(self):
        doc = read("hsr-facebook-official-account-evidence.json")
        self.assertEqual(doc["schema"], "gacha-wars-hsr-facebook-official-account-evidence-v1")
        self.assertEqual(doc["group_count"], 3)
        self.assertEqual(doc["full_notice_count"], 1)
        self.assertEqual(doc["partial_notice_count"], 2)
        self.assertEqual(doc["records_upgraded"], 3)
        self.assertEqual(doc["publisher_account"], "https://www.facebook.com/HonkaiStarRail.CHS")
        old_full = set()
        for filename in OFFICIAL_FILES:
            for group in read(filename)["groups"]:
                old_full.update(group["ids"])
        self.assertEqual(len(old_full), 135)
        full = set()
        partial = set()
        for group in doc["groups"]:
            self.assertEqual(len(group["ids"]), 3)
            self.assertEqual(group["source_url"].split("/")[2], "www.facebook.com")
            for i, eid in enumerate(group["ids"]):
                self.assertNotIn(eid, old_full)
                row = self.original[eid]
                self.assertEqual(row["date"], group["date"])
                self.assertEqual(row["version"], group["names"][i])
                self.assertEqual(row["featured_five_star"], group["featured_five_star"])
                self.assertEqual(row["verification"], "secondary")
                if group["status"] == "publisher_indexed_full_start_and_roster":
                    self.assertEqual(group["verification"], "official")
                    full.add(eid)
                else:
                    self.assertEqual(group["status"], "publisher_indexed_partial_not_full_body")
                    self.assertEqual(group["verification"], "secondary")
                    partial.add(eid)
        self.assertEqual(len(full), 3)
        self.assertEqual(len(partial), 6)
        self.assertEqual(len(old_full | full), 138)
        self.assertEqual(len(self.original) - len(old_full | full), 39)
        html = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-facebook-official-account-evidence.json"', html)
        self.assertIn('function applyHsrFacebookEvidence(', html)
        self.assertIn('publisher_indexed_partial_not_full_body', html)
        self.assertIn('運営公式Facebook（全文確認待ち）', html)


    def test_mihoyo_original_2024_december_announcement(self):
        doc = read("hsr-mihoyo-primary-banner-overrides.json")
        self.assertEqual(doc["schema"], "gacha-wars-hsr-mihoyo-primary-banner-overrides-v1")
        self.assertEqual(doc["verification"], "official")
        self.assertEqual(doc["group_count"], 1)
        self.assertEqual(doc["count"], 3)
        group = doc["groups"][0]
        self.assertEqual(group["date"], "2024-12-04")
        self.assertEqual(group["featured_five_star"], "サンデー／景元")
        self.assertEqual(group["names"], ["停雲", "青雀", "アーラン"])
        self.assertEqual(group["names_cn"], ["停云", "青雀", "阿兰"])
        self.assertEqual(group["source_url"], "https://sr.mihoyo.com/news/127222")
        self.assertEqual(group["source_quote_fields"]["starts"], "2024/12/04 2.7版本更新后")
        self.assertEqual(group["source_quote_fields"]["shared_4star"], ["青雀", "阿兰", "停云"])
        seen = set()
        for i, eid in enumerate(group["ids"]):
            row = self.original[eid]
            self.assertNotIn(eid, seen)
            seen.add(eid)
            self.assertEqual(row["verification"], "secondary")
            self.assertEqual(row["date"], group["date"])
            self.assertEqual(row["version"], group["names"][i])
            self.assertEqual(row["featured_five_star"], group["featured_five_star"])
        self.assertEqual(len(seen), 3)
        original_official = {eid for filename in OFFICIAL_FILES
                            for g in read(filename)["groups"] for eid in g["ids"]}
        fb = read("hsr-facebook-official-account-evidence.json")
        fb_official = {eid for g in fb["groups"] if g["verification"] == "official"
                       for eid in g["ids"]}
        self.assertEqual(len(original_official), 135)
        self.assertEqual(len(fb_official), 3)
        self.assertFalse(original_official & fb_official)
        self.assertFalse((original_official | fb_official) & seen)
        all_official = original_official | fb_official | seen
        self.assertEqual(len(all_official), 141)
        self.assertEqual(len(self.original) - len(all_official), 36)
        html = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-mihoyo-primary-banner-overrides.json"', html)
        self.assertIn('function applyHsrMihoyoPrimaryBannerOverrides(', html)
        self.assertIn('row.verification!=="secondary"', html)


    def test_new_bilibili_2023_2024_publisher_proofs(self):
        doc = read("hsr-publisher-bilibili-2023-2024-official.json")
        self.assertEqual(doc["schema"], "gacha-wars-hsr-publisher-bilibili-2023-2024-official-v1")
        self.assertEqual(doc["verification"], "official")
        self.assertEqual(doc["group_count"], 3)
        self.assertEqual(doc["count"], 9)
        expected = {
            "2023-12-06": ("アルジェンティ／銀狼", ["寒鴉", "リンクス", "アスター"], "871493549220167785"),
            "2024-07-31": ("雲璃／フォフォ", ["寒鴉", "御空", "リンクス"], "959819534499315736"),
            "2024-08-21": ("椒丘／花火", ["フック", "桂乃芬", "アーラン"], "967604592193830949"),
        }
        previously_official = {
            eid for filename in OFFICIAL_FILES
            for g in read(filename)["groups"] for eid in g["ids"]
        }
        for g in read("hsr-facebook-official-account-evidence.json")["groups"]:
            if g["verification"] == "official":
                previously_official.update(g["ids"])
        for g in read("hsr-mihoyo-primary-banner-overrides.json")["groups"]:
            previously_official.update(g["ids"])
        self.assertEqual(len(previously_official), 141)
        newly = set()
        for group in doc["groups"]:
            self.assertIn(group["date"], expected)
            parent, names, suffix = expected[group["date"]]
            self.assertEqual(group["featured_five_star"], parent)
            self.assertEqual(group["names"], names)
            self.assertEqual(group["verification"], "official")
            self.assertEqual(group["source_url"], "https://www.bilibili.com/opus/" + suffix)
            self.assertEqual(group["date_basis"], "publisher_bilibili_exact_event_warp_start_and_all_three_fourstars")
            self.assertEqual(len(group["ids"]), 3)
            self.assertEqual(len(group["names_cn"]), 3)
            self.assertEqual(len(group["banner_cn"]), 2)
            for i, eid in enumerate(group["ids"]):
                self.assertNotIn(eid, previously_official)
                self.assertNotIn(eid, newly)
                newly.add(eid)
                row = self.original[eid]
                self.assertEqual(row["verification"], "secondary")
                self.assertEqual(row["date"], group["date"])
                self.assertEqual(row["version"], group["names"][i])
                self.assertEqual(row["featured_five_star"], group["featured_five_star"])
        self.assertEqual(len(newly), 9)
        self.assertEqual(len(previously_official | newly), 150)
        self.assertEqual(len(self.original) - len(previously_official | newly), 27)
        html = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-publisher-bilibili-2023-2024-official.json"', html)
        self.assertIn('function applyHsrPublisherBilibili2023to2024Official(', html)
        self.assertLess(html.index('fetch("./hsr-facebook-official-account-evidence.json"'),
                        html.index('fetch("./hsr-publisher-bilibili-2023-2024-official.json"'))



    def test_facebook_original_source_promotion_2025_summer_autumn(self):
        doc = read("hsr-official-facebook-2025-summer-autumn.json")
        self.assertEqual(doc["schema"], "gacha-wars-hsr-official-facebook-summer-autumn-2025-v1")
        self.assertEqual(doc["verification"], "official")
        self.assertEqual(doc["group_count"], 2)
        self.assertEqual(doc["count"], 6)
        expected = {
            "2025-07-23": ("ホタル／鏡流／刃", ["寒鴉", "リンクス", "ルカ"], "746110384465921", "759955636546629"),
            "2025-09-24": ("長夜月／マダム・ヘルタ", ["ミーシャ", "桂乃芬", "雪衣"], "794492746294351", "809497008259158"),
        }
        older = {eid for filename in OFFICIAL_FILES
                 for g in read(filename)["groups"] for eid in g["ids"]}
        for file in ["hsr-facebook-official-account-evidence.json",
                     "hsr-mihoyo-primary-banner-overrides.json",
                     "hsr-publisher-bilibili-2023-2024-official.json"]:
            for group in read(file)["groups"]:
                if group.get("verification") == "official":
                    older.update(group["ids"])
        self.assertEqual(len(older), 150)
        upgraded = set()
        for group in doc["groups"]:
            self.assertIn(group["date"], expected)
            parent, names, chs, cht = expected[group["date"]]
            self.assertEqual(group["featured_five_star"], parent)
            self.assertEqual(group["names_ja"], names)
            self.assertEqual(group["source_url"], "https://www.facebook.com/HonkaiStarRail.CHS/posts/" + chs + "/")
            self.assertEqual(group["corroborating_official_url"], "https://www.facebook.com/HonkaiStarRail.CHT/posts/" + cht + "/")
            self.assertEqual(group["verification"], "official")
            self.assertEqual(len(group["ids"]), 3)
            self.assertEqual(len(group["names_cn"]), 3)
            self.assertEqual(len(group["featured_five_star_cn"]), 3 if group["date"] == "2025-07-23" else 2)
            self.assertIn(group["date"].replace("-", "/"), group["time_cn"])
            for i, eid in enumerate(group["ids"]):
                self.assertNotIn(eid, older | upgraded)
                upgraded.add(eid)
                base = self.original[eid]
                self.assertEqual(base["date"], group["date"])
                self.assertEqual(base["version"], group["names_ja"][i])
                self.assertEqual(base["featured_five_star"], group["featured_five_star"])
                self.assertEqual(base["verification"], "secondary")
        self.assertEqual(len(upgraded), 6)
        self.assertEqual(len(older | upgraded), 156)
        self.assertEqual(len(self.original) - len(older | upgraded), 21)
        site = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-official-facebook-2025-summer-autumn.json"', site)
        self.assertIn('function applyHsrOfficialFacebook2025SummerAutumn(', site)
        self.assertLess(site.index('fetch("./hsr-publisher-bilibili-2023-2024-official.json"'),
                        site.index('fetch("./hsr-official-facebook-2025-summer-autumn.json"'))

    def test_new_five_historical_official_2023_2025_groups(self):
        doc = read("hsr-five-historical-official-notices.json")
        self.assertEqual(doc["schema"], "gacha-wars-hsr-five-historical-official-notices-v1")
        self.assertEqual(doc["verification"], "official")
        self.assertEqual((doc["group_count"], doc["count"]), (5, 15))
        expected = {
            "2023-05-17": ("景元", ["三月なのか", "素裳", "停雲"], "18568299"),
            "2024-05-08": ("ロビン／トパーズ＆カブ", ["三月なのか", "寒鴉", "雪衣"], "28251947"),
            "2024-06-19": ("ホタル／ルアン・メェイ", ["雪衣", "ミーシャ", "ギャラガー"], "551806632766472744"),
            "2024-10-23": ("乱破／丹恒・飲月", ["リンクス", "雪衣", "御空"], "34424519"),
            "2025-02-05": ("アグライア／ブートヒル／ロビン／銀狼", ["寒鴉", "停雲", "素裳"], "36843932"),
        }
        original = self.original
        prev = {
            eid for filename in OFFICIAL_FILES
            for group in read(filename)["groups"] for eid in group["ids"]
        }
        for filename in [
            "hsr-facebook-official-account-evidence.json",
            "hsr-mihoyo-primary-banner-overrides.json",
            "hsr-publisher-bilibili-2023-2024-official.json",
            "hsr-official-facebook-2025-summer-autumn.json",
        ]:
            prev.update(eid for group in read(filename)["groups"]
                        if group["verification"] == "official" for eid in group["ids"])
        self.assertEqual(len(prev), 156)
        newly = set()
        for group in doc["groups"]:
            date = group["date"]
            self.assertIn(date, expected)
            parent, names, source_id = expected[date]
            self.assertEqual(group["featured_five_star"], parent)
            self.assertEqual(group["names_ja"], names)
            self.assertIn(source_id, group["source_url"])
            self.assertEqual(group["verification"], "official")
            self.assertTrue(group["date_basis"].startswith("publisher_"))
            self.assertEqual(len(group["ids"]), 3)
            for i, eid in enumerate(group["ids"]):
                self.assertEqual(eid, f"hsr-four-pu-{date}-{i+1}")
                self.assertNotIn(eid, prev | newly)
                self.assertEqual(original[eid]["date"], date)
                self.assertEqual(original[eid]["featured_five_star"], parent)
                self.assertEqual(original[eid]["version"], names[i])
                self.assertEqual(original[eid]["verification"], "secondary")
                newly.add(eid)
        self.assertEqual(len(newly), 15)
        self.assertEqual(len(prev | newly), 171)
        html = (DATA / "index.html").read_text(encoding="utf-8")
        self.assertIn('fetch("./hsr-five-historical-official-notices.json"', html)
        self.assertIn("function applyHsrFiveHistoricalOfficialNotices(", html)

    def test_hsr_evidence_progress_groups_original_177_records(self):
        import subprocess
        import tempfile
        base = read("release-events.json")["events"]
        historical = [
            dict(e) for e in base
            if e.get("game") == "hsr"
            and e.get("type") == "character"
            and e.get("rarity") == 4
            and e.get("banner_type") == "event_warp_four_star"
        ]
        official = {
            eid for filename in OFFICIAL_FILES
            for g in read(filename)["groups"] for eid in g["ids"]
        }
        for g in read("hsr-facebook-official-account-evidence.json")["groups"]:
            if g["verification"] == "official":
                official.update(g["ids"])
        for g in read("hsr-mihoyo-primary-banner-overrides.json")["groups"]:
            official.update(g["ids"])
        for g in read("hsr-publisher-bilibili-2023-2024-official.json")["groups"]:
            official.update(g["ids"])
        for g in read("hsr-official-facebook-2025-summer-autumn.json")["groups"]:
            official.update(g["ids"])
        for g in read("hsr-five-historical-official-notices.json")["groups"]:
            official.update(g["ids"])
        self.assertEqual(len(historical), 177)
        self.assertEqual(len(official), 171)
        for row in historical:
            if row["id"] in official:
                row["verification"] = "official"
        html = (DATA / "index.html").read_text(encoding="utf-8")
        start = html.index("function hsrFourStarProvenanceBoard(){")
        end = html.index("function unresolvedSourceBoard(){", start)
        function = html[start:end]
        with tempfile.TemporaryDirectory() as tmp:
            file = pathlib.Path(tmp) / "historical.json"
            file.write_text(json.dumps(historical, ensure_ascii=False), encoding="utf-8")
            js = '''
const fs=require("fs");
const publishedEvents=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
''' + function + '''
const rendered=hsrFourStarProvenanceBoard();
console.log(JSON.stringify({
  progress:rendered.includes("171/177件・保留 6件（2開催分）"),
  rows:(rendered.match(/<tr><td>/g)||[]).length,
  chronology:rendered.indexOf("2023-12-27")<rendered.indexOf("2025-04-09"),
  unverifiedExplanation:rendered.includes("原文照合が済んでいない場合は未照合")
}));
'''
            result = subprocess.run(["node", "-e", js, str(file)], capture_output=True, text=True, check=True)
            outcome = json.loads(result.stdout)
            self.assertTrue(outcome["progress"])
            self.assertEqual(outcome["rows"], 2)
            self.assertTrue(outcome["chronology"])
            self.assertTrue(outcome["unverifiedExplanation"])


if __name__ == "__main__":
    unittest.main()
