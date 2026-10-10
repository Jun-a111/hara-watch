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
    "nte": ("異環", "异环", "이환", "nevernesstoeverness", "NTE: Neverness to Everness"),
    "end": ("アークナイツエンドフィールド", "明日方舟终末地", "明日方舟終末地", "명일방주엔드필드", "arknightsendfield"),
}
# Apple App Store product IDs verified against their public App Store pages.
# These remain stable when display titles gain event/version subtitles.
OFFICIAL_APP_IDS = {
    "gi": {"1517783697"},
    "zzz": {"1606356401"},
    "nte": {"6754593077"},
    "end": {"6752642477"},
    "hsr": {"1599719154"},
    "ww": {"6475033368"},
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
# App Store IDs are normally shared across regions; observations from earlier
# successful chart matches can help identify localized titles safely.
KNOWN_IDS = {game: set(ids) for game, ids in OFFICIAL_APP_IDS.items()}
REGIONAL_IDS = {market: {game: set() for game in ALIASES} for market in MARKETS}
for record in past:
    if not isinstance(record, dict):
        continue
    game, app_id = record.get("game"), record.get("app_id")
    if game in ALIASES and app_id and str(app_id).isdigit():
        KNOWN_IDS.setdefault(game, set()).add(str(app_id))
        if record.get("region") in REGIONAL_IDS:
            REGIONAL_IDS[record["region"]][game].add(str(app_id))
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
            app_id = str(entry.get("id", {}).get("attributes", {}).get("im:id") or "")
            for game, names in MATCH.items():
                matched_title = title in names
                matched_id = bool(app_id) and app_id in KNOWN_IDS.get(game, set())
                if (matched_title or matched_id) and game not in matches:
                    new.append({"game": game, "region": market, "kind": "rank",
                                "store": "ios", "value": rank, "date": now,
                                "source": "Apple iTunes top grossing Games RSS",
                                "source_url": url, "chart": "topgrossingapplications",
                                "chart_depth": len(entries), "app_id": app_id, "matched_by": "name" if matched_title else "verified_app_id"})
                    if app_id.isdigit():
                        KNOWN_IDS.setdefault(game, set()).add(app_id)
                        REGIONAL_IDS[market][game].add(app_id)
                    matches.add(game)
        # App availability is distinct from placement on a revenue chart.
        # Look up all known storefront IDs in one request per region. Never
        # manufacture ranking observations from these metadata responses.
        lookup = {}
        try:
            from urllib.parse import urlencode
            ids = sorted({aid for game in ALIASES for aid in (OFFICIAL_APP_IDS[game] | REGIONAL_IDS[market][game])})
            lookup_url = "https://itunes.apple.com/lookup?" + urlencode({
                "id": ",".join(ids), "country": market, "entity": "software"})
            lookup_req = urllib.request.Request(lookup_url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; GachaWars/1.0)",
                "Accept": "application/json"})
            with urllib.request.urlopen(lookup_req, timeout=12) as response:
                lookup_data = json.load(response)
            available_ids = {str(item.get("trackId")) for item in lookup_data.get("results", [])
                             if item.get("trackId") is not None}
            lookup = {"ok": True, "available": sorted(
                game for game, ids in OFFICIAL_APP_IDS.items() if available_ids.intersection(ids | REGIONAL_IDS[market][game])),
                "not_listed": sorted(
                    game for game, ids in OFFICIAL_APP_IDS.items()
                    if not available_ids.intersection(ids | REGIONAL_IDS[market][game]) and game not in matches),
                "alternate_region_id": sorted(
                    game for game in matches if not available_ids.intersection(OFFICIAL_APP_IDS[game] | REGIONAL_IDS[market][game])),
                "note": "Apple lookupでIDが見つからない場合も、別ID・地域差の可能性があるため配信終了や未配信とは断定しない"}
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            lookup = {"ok": False, "error": str(exc)[:150]}
        status[market] = {"ok": True, "chart_depth": len(entries),
                          "matched": sorted(matches),
                          "not_seen_in_top_chart": sorted(set(ALIASES) - matches),
                          "app_store_lookup": lookup,
                          "checked_at": now}
        print(f"{market}: top {len(entries)}, matched {sorted(matches)}")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        status[market] = {"ok": False, "error": str(exc)[:150], "checked_at": now}
        print(f"{market}: unavailable: {exc}")
# Only append positive observations. A missing game might be beyond chart depth,
# unavailable in the country, or published under another localized title.
# Deduplicate within a run as well as against previous observations.
by_key = {}
for record in [*past, *new]:
    if not isinstance(record, dict):
        continue
    if record.get("game") not in ALIASES or record.get("region") not in MARKETS:
        continue
    value = record.get("value")
    if not isinstance(value, int) or value <= 0:
        continue
    key = (record.get("game"), record.get("region"), record.get("date"))
    by_key[key] = record
# Keep every valid historical observation. Truncating to the latest 5,000
# silently destroyed older banner-window rankings as the archive grew.
past = sorted(by_key.values(), key=lambda r: r.get("date") or "")
# Verify every successful chart match produced a real observation during this run.
# This is a diagnostic only: never create artificial rank records to fill gaps.
by_market = {}
for record in new:
    by_market.setdefault(record["region"], set()).add(record["game"])
integrity = {}
for market, st in status.items():
    if st.get("ok"):
        missing = sorted(set(st.get("matched", [])) - by_market.get(market, set()))
        integrity[market] = {"ok": not missing, "missing_rank_records": missing,
                             "matched_count": len(st.get("matched", [])),
                             "recorded_count": len(by_market.get(market, set()))}
    else:
        integrity[market] = {"ok": None, "reason": "chart_fetch_failed"}
OUTPUT.write_text(json.dumps({
    "schema": "gacha-wars-ios-v1", "updated_at": now,
    "market_status": status, "integrity": integrity, "records": past
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
