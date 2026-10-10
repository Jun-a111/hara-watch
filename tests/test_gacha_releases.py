import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"update_gacha_releases.py"

class ExtractorTests(unittest.TestCase):
 def test_regex_and_character_filters(self):
  source=SCRIPT.read_text(encoding="utf-8")
  begin=source.index("DATE_TOKEN=")
  end=source.index("class ArticleText(",begin)
  namespace={"re":__import__("re")}
  exec(source[begin:end],namespace)
  details=namespace["article_details"]("開催期間：2026年10月9日 12:00～2026年10月29日 11:59。対象キャラクター「オクギ」、通常スカウト「通常スカウト」")
  self.assertEqual(len(details["period_candidates"]),1)
  self.assertIn("オクギ",details["character_candidates"])
  self.assertNotIn("通常スカウト",details["character_candidates"])
 def test_yearless_end_date(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  cases=[
   "開催期間：2026年10月9日 12:00 ～ 10月29日 11:59",
   "2026/10/09 12:00～2026/10/29 11:59",
   "2026年10月9日から2026年10月29日まで",
  ]
  for sample in cases:
   with self.subTest(sample=sample):
    self.assertEqual(len(ns["article_details"](sample)["period_candidates"]),1)
 def test_non_period_dates(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  self.assertEqual(ns["article_details"]("公開日2026年10月9日 更新日2026年10月12日")["period_candidates"],[])
 def test_date_not_truncated(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_RE="):source.index("PHASE_FIRST=")],ns)
  examples=[("2026年6月13日",("2026","6","13")),("2026/3/17",("2026","3","17")),("2026/4/28",("2026","4","28")),("2026/5/19",("2026","5","19"))]
  for raw,expected in examples:
   with self.subTest(raw=raw):
    self.assertEqual(ns["DATE_RE"].search(raw).groups(),expected)
 def test_real_world_period_deduplication(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  text="2026/3/17 18:00~2026/4/7 14:59。2026/3/17 18:00—2026/4/7 14:59。2026/3/17 18:00—2026/4/7 14:59"
  result=ns["article_details"](text)
  self.assertEqual(len(result["period_candidates"]),1)
 def test_no_false_names(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  details=ns["article_details"]("スカウト対象「特別スカウト」「Ver.3.2」。対象キャラクター「オクギ」")
  self.assertEqual(details["character_candidates"],["オクギ"])
class StructuredArticleTests(unittest.TestCase):
 def parser(self):
  source=SCRIPT.read_text(encoding="utf-8")
  begin=source.index("class StructuredArticle(")
  end=source.index("def blank_hints(",begin)
  namespace={"HTMLParser":__import__("html.parser",fromlist=["HTMLParser"]).HTMLParser,"json":__import__("json")}
  exec(source[begin:end],namespace)
  return namespace["StructuredArticle"]()
 def test_article_ld_json(self):
  parser=self.parser()
  parser.feed('<script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle","headline":"公式告知","articleBody":"2026年10月9日～2026年10月29日 対象キャラクター「オクギ」"}</script>')
  self.assertIn("オクギ"," ".join(parser.texts()))
 def test_unrelated_json_not_accepted(self):
  parser=self.parser()
  parser.feed('<script type="application/ld+json">{"@type":"WebSite","description":"2026年10月9日～2026年10月29日"}</script>')
  self.assertEqual(parser.texts(),[])
class OfficialNewsApiTests(unittest.TestCase):
 def test_nested_json_news_links(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={}
  exec(source[source.index("def json_news_items("):source.index("def browser_news_links(")],ns)
  payload={"data":{"items":[{"title":"特別スカウト『新キャラ』のお知らせ","url":"/ja-jp/news/1234"},{"title":"ゲーム告知","link":"https://endfield.gryphline.com/ja-jp/news/5555"}]}}
  items=ns["json_news_items"](payload)
  self.assertEqual(len(items),2)
  self.assertEqual(items[0][1],"/ja-jp/news/1234")
 def test_ignore_id_without_url(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={}
  exec(source[source.index("def json_news_items("):source.index("def browser_news_links(")],ns)
  self.assertEqual(ns["json_news_items"]({"data":[{"id":1234,"title":"集音のお知らせ"}]}),[])
class CollectorRegressionTests(unittest.TestCase):
 def test_collector_compiles(self):
  source=SCRIPT.read_text(encoding="utf-8")
  compile(source,str(SCRIPT),"exec")
 def test_checkpoint_inside_game_loop(self):
  import ast
  tree=ast.parse(SCRIPT.read_text(encoding="utf-8"))
  loops=[n for n in tree.body if isinstance(n,ast.For) and any(isinstance(child,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="url" for t in child.targets) for child in n.body)]
  self.assertTrue(loops,"収集ループが見つからない")
  checkpoint=[n for n in ast.walk(loops[-1]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="save_candidates"]
  self.assertTrue(checkpoint,"各作品ごとの保存が必要")
 def test_checkpoint_ends_in_newline(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('content=json.dumps(payload,ensure_ascii=False,indent=2)+"\\n"',source)
class AtomicCandidateOutputTests(unittest.TestCase):
 def test_atomic_save_preserves_valid_file(self):
  import json,tempfile
  from pathlib import Path
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"json":json}
  exec(source[source.index("def save_candidates("):source.index("now=datetime.now(")],ns)
  with tempfile.TemporaryDirectory() as temp:
   target=Path(temp)/"release-candidates.json"
   ns["OUTPUT"]=target
   good={"schema":"gacha-wars-release-candidates-v1","candidates":[{"game":"ww","url":"https://example.org/news/1"}]}
   ns["save_candidates"](good)
   self.assertEqual(json.loads(target.read_text(encoding="utf-8")),good)
   self.assertTrue(target.read_text(encoding="utf-8").endswith("\n"))
   with self.assertRaises(ValueError):
    ns["save_candidates"]({"schema":"wrong","candidates":[]})
   self.assertEqual(json.loads(target.read_text(encoding="utf-8")),good)
class JsonDiagnosticsTests(unittest.TestCase):
 def test_shapes_contain_keys_not_values(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={}
  exec(source[source.index("def json_news_structure("):source.index("def browser_news_links(")],ns)
  example={"data":{"items":[{"id":123,"headline":"Private headline value","secret":"sensitive-value"}]}}
  result=ns["json_news_structure"](example)
  self.assertTrue(any("id" in keys for keys in result))
  self.assertNotIn("sensitive-value",str(result))
class EndfieldCidTests(unittest.TestCase):
 def test_extract_known_cid_fields(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={}
  exec(source[source.index("def endfield_news_items("):source.index("def json_news_structure(")],ns)
  data={"data":{"list":[{"cid":2656,"title":"特別スカウトのお知らせ"},{"cid":"5208","title":"バージョンアップデートのお知らせ"},{"title":"CIDなし","id":999}]}}
  found=ns["endfield_news_items"](data)
  self.assertEqual(len(found),2)
  self.assertEqual(found[0][1],"https://endfield.gryphline.com/ja-jp/news/2656")
 def test_ignore_non_numeric_cid(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={}
  exec(source[source.index("def endfield_news_items("):source.index("def json_news_structure(")],{},ns)
  self.assertEqual(ns["endfield_news_items"]({"cid":"../bad","title":"不正URLにさせない告知"}),[])
class SteamDedupTests(unittest.TestCase):
 def test_steam_title_deduplication_is_present(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('diag["duplicate_titles"]=len(found)-len(unique)',source)
  self.assertIn('steam_seen.add(key)',source)
  self.assertIn('records=deduplicated[:400]',source)

class PeriodClassificationTests(unittest.TestCase):
 def test_maintenance_separated_from_banner(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  sample="メンテナンス期間：2026年10月9日 06:00～2026年10月9日 12:00。集音開催期間：2026年10月10日 11:00～2026年10月30日 12:59"
  periods=ns["article_details"](sample)["period_candidates"]
  self.assertEqual([x["classification"] for x in periods],["maintenance","banner_possible"])
class ExtractionCacheTests(unittest.TestCase):
 def test_old_article_cache_requires_reextraction(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('previous.get("extraction_version")==4',source)
  self.assertIn('item["extraction_version"]=4',source)
  self.assertIn('"character_candidates","extraction_version"',source)

class CandidateSelectionTests(unittest.TestCase):
 def test_stale_periods_prioritized(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn("stale and has_periods",source)
  self.assertIn("selected=sorted(collected[game],key=selection_priority)[:12]",source)

class SpecificDateLabelTests(unittest.TestCase):
 def test_wish_and_other_event_dates(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  examples=[
   ("〓Event Wish Duration〓 2026/3/17 18:00~2026/4/7 14:59","banner_possible"),
   ("末日の幻影・忘却の支配 2026/10/05 04:00 ～ 2026/11/16 03:59","other_event"),
   ("開催期間：2026/09/16 12:00～2026/09/30 16:00","other_event"),
  ]
  for line,expected in examples:
   with self.subTest(line=line):
    self.assertEqual(ns["article_details"](line)["period_candidates"][0]["classification"],expected)

class RegionalMaintenanceTests(unittest.TestCase):
 def test_second_region_is_still_maintenance(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  sample="■ メンテナンス実施日時 Asiaサーバー：2026/09/02 06:00～2026/09/02 12:00（UTC+8） Americas / Europeサーバー：2026/09/01 17:00～2026/09/01 23:00"
  periods=ns["article_details"](sample)["period_candidates"]
  self.assertEqual([p["classification"] for p in periods],["maintenance","maintenance"])

class ClassificationPreservationTests(unittest.TestCase):
 def test_curated_classification_preservation_logic(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('old.get("classification_source")=="stored_context_reclassified"',source)
  self.assertIn('period.get("classification","unknown")=="unknown"',source)
  self.assertIn('preserve_period_classification(detail.get("period_candidates",[]))',source)

class FailedRefreshPreservationTests(unittest.TestCase):
 def test_failed_reextraction_keeps_previous_body(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('detail.get("body_status") not in ("rendered","extracted")',source)
  self.assertIn('previous.get("body_status") in ("rendered","extracted")',source)
  self.assertIn('item["refresh_error"]=',source)
  self.assertIn('"period_candidates","character_candidates","extraction_version"',source)

class DiscoveryMergePreservationTests(unittest.TestCase):
 def test_discovery_only_updates_preserve_previous_article_fields(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('if "body_status" not in x and old_record.get("body_status") in ("rendered","extracted"):',source)
  self.assertIn('merged[field]=old_record[field]',source)

class WutheringBodyQualityTests(unittest.TestCase):
 def test_rejects_generic_site_shell(self):
  source=SCRIPT.read_text(encoding="utf-8")
  from urllib.parse import urlparse
  import re
  ns={"urlparse":urlparse,"DATE_RE":re.compile(r"20\d{2}[年/-]\d{1,2}[月/-]\d{1,2}")}
  exec(source[source.index("def article_text_quality("):source.index("def rendered_hints(")],ns)
  url="https://wutheringwaves.kurogames.com/jp/main/news/detail/5547"
  shell="鳴潮 ニュース アップデート ホーム キャラクター "*20
  article="集音開催期間 2026年10月10日11:00 から 2026年10月30日11:00 共鳴者 "*12
  self.assertFalse(ns["article_text_quality"](url,shell))
  self.assertTrue(ns["article_text_quality"](url,article))

class OriginalSourcePriorityTests(unittest.TestCase):
 def test_kuro_refresh_not_starved_by_steam(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('not (stale and official_ww)',source)
  self.assertIn('hostname=="wutheringwaves.kurogames.com"',source)
 def test_steam_news_must_be_own_announcement(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('/news/externalpost/steam_community_announcements/',source)

class WutheringConvenePeriodTests(unittest.TestCase):
 def test_generic_event_period_under_convene_is_banner(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("DATE_TOKEN="):source.index("class ArticleText(")],ns)
  sample="共鳴者集音（イベント）「明日へ焼き付ける記憶」 イベント期間中、星5共鳴者「ルシラー」の出現率UP！ ✦開催期間✦ 2026年6月13日11:00 ~ 2026年7月9日12:59"
  periods=ns["article_details"](sample)["period_candidates"]
  self.assertEqual(periods[0]["classification"],"banner_possible")

class ConveneClassificationPersistenceTests(unittest.TestCase):
 def test_convene_context_correction_survives_failed_reclassification(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('"stored_context_reclassified","convene_notice_context"',source)

class KuroDelayedRenderTests(unittest.TestCase):
 def test_article_shell_gets_a_bounded_retry(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('for _ in range(3):',source)
  self.assertIn('if article_text_quality(url,more):',source)
  self.assertIn('page.wait_for_timeout(1200)',source)

class KuroArticleContainerTests(unittest.TestCase):
 def test_detail_selectors_require_body_validation(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('detail_selectors=(',source)
  self.assertIn('page.locator(selector).all_inner_texts',source)
  self.assertIn('if article_text_quality(url,candidate):',source)

class ReviewedConveneFallbackTests(unittest.TestCase):
 def test_generic_other_event_does_not_erase_reviewed_convene(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('old.get("classification_source")=="convene_notice_context"',source)
  self.assertIn('period.get("classification")=="other_event"',source)
  self.assertIn('re.search(r"共鳴者集音|武器集音"',source)

class KuroStaticBodyValidationTests(unittest.TestCase):
 def test_static_body_is_validated_before_extraction(self):
  source=SCRIPT.read_text(encoding="utf-8")
  part=source[source.index("def page_hints("):source.index("def article_text_quality(")]
  self.assertIn('if not article_text_quality(url,text):',part)
  self.assertIn('blank_hints("unavailable","静的HTMLの記事本文を確認できず")',part)

class RefreshMetricIntegrityTests(unittest.TestCase):
 def test_failed_refresh_not_counted_as_success(self):
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('x.get("body_status")=="rendered" and not x.get("refresh_error")',source)
  self.assertIn('x.get("body_status") in ("rendered","extracted") and not x.get("refresh_error")',source)
  self.assertIn('or bool(x.get("refresh_error"))',source)

if __name__=="__main__":unittest.main()
