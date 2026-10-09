import importlib.util
import pathlib
import unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"update_gacha_releases.py"

class ExtractorTests(unittest.TestCase):
 def load(self):
  # The collector runs on import: redirect requests into a temporary sandbox.
  import tempfile
  with tempfile.TemporaryDirectory() as temp:
   with patch("urllib.request.urlopen", side_effect=OSError("offline test")):
    spec=importlib.util.spec_from_file_location("gacha_release_collector",SCRIPT)
    module=importlib.util.module_from_spec(spec)
    # Output still goes to repo; avoid import-based tests until extractor becomes import-safe.
  return None
 def test_regex_and_character_filters(self):
  source=SCRIPT.read_text(encoding="utf-8")
  begin=source.index("PERIOD_RE=")
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
 def test_no_false_names(self):
  source=SCRIPT.read_text(encoding="utf-8")
  ns={"re":__import__("re")}
  exec(source[source.index("PERIOD_RE="):source.index("class ArticleText(")],ns)
  details=ns["article_details"]("スカウト対象「特別スカウト」「Ver.3.2」。対象キャラクター「オクギ」")
  self.assertEqual(details["character_candidates"],["オクギ"])
if __name__=="__main__":unittest.main()
