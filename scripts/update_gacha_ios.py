#!/usr/bin/env python3
"""Collect public Apple top-grossing chart observations, never infer missing ranks."""
import json
import re
import urllib.request
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "gacha-wars" / "ios-rank-data.json"
MARKETS = ("jp", "cn", "tw", "hk", "kr", "us")
ALIASES = {
    "ww": ("鳴潮", "鸣潮", "명조", "wutheringwaves"),
    "gi": ("原神", "원신", "genshinimpact"),
    "hsr": ("崩壊スターレイル", "崩坏星穹铁道", "崩壞星穹鐵道", "붕괴스타레일", "honkaistarrail"),
    "zzz": ("ゼンレスゾーンゼロ", "绝区零", "絕區零", "젠레스존제로", "zenlesszonezero"),
    "nte": ("異環", "异环", "이환", "nevernesstoeverness"),
    "end": ("アークナイツエンドフィールド", "明日方舟终末地", "明日方舟終末地", "명일방주엔드필드", "arknightsendfield"),
}
# Strict title matching avoids assigning the rank of unrelated apps to a game.
def normalized(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value).casefold(), flags=re.UNICODE).replace("_", "")

MATCH = {game: {normalized(alias) for alias in aliases} for game, aliases in ALIASES.items()}
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
try:
    past = json.loads(OUTPUT.read_text(encoding="utf-8")).get("records", [])
except (OSError, ValueError):
    past = []
new = []
status = {}
for market in MARKETS:
    url = f"https://itunes.apple.com/{market}/rss/topgrossingapplications/limit=100/genre=6014/json"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; GachaWars/1.0)",
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=24) as res:
            data = json.load(res)
        entries = data.get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        if not isinstance(entries, list) or not entries:
            raise ValueError("empty or invalid chart")
        matches = set()
        for rank, entry in enumerate(entries, 1):
            title = normalized(entry.get("im:name", {}).get("label", ""))
            for game, names in MATCH.items():
                if title in names and game not in matches:
                    new.append({"game": game, "region": market, "kind": "rank",
                                "store": "ios", "value": rank, "date": now,
                                "source": "Apple iTunes top grossing Games RSS",
                                "source_url": url, "chart": "topgrossingapplications",
                                "chart_depth": len(entries), "app_id": entry.get("id", {}).get("attributes", {}).get("im:id")})
                    matches.add(game)
        status[market] = {"ok": True, "chart_depth": len(entries),
                          "matched": sorted(matches), "checked_at": now}
        print(f"{market}: top {len(entries)}, matched {sorted(matches)}")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        status[market] = {"ok": False, "error": str(exc)[:150], "checked_at": now}
        print(f"{market}: unavailable: {exc}")
# Only append positive observations. A missing game might be beyond chart depth,
# unavailable in the country, or published under another localized title.
known = {(r.get("game"), r.get("region"), r.get("date")) for r in past}
past.extend(r for r in new if (r["game"], r["region"], r["date"]) not in known)
past = sorted(past, key=lambda r: r["date"])[-5000:]
OUTPUT.write_text(json.dumps({
    "schema": "gacha-wars-ios-v1", "updated_at": now,
    "market_status": status, "records": past
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
