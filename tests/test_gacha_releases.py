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
  checkpoint=[n for n in ast.walk(loops[-1]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=="write_text"]
  self.assertTrue(checkpoint,"各作品ごとの保存が必要")
 def test_checkpoint_ends_in_newline(self):
  import ast
  source=SCRIPT.read_text(encoding="utf-8")
  self.assertIn('+"\\n",encoding="utf-8")',source)
if __name__=="__main__":unittest.main()
