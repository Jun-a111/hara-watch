#!/usr/bin/env python3
"""Fetch official Steam current-player snapshots; leave missing data missing."""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "gacha-wars" / "steam-data.json"
GAMES = {"ww": 3513350, "zzz": 4162040, "nte": 4508340}
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
try:
    previous = json.loads(OUT.read_text(encoding="utf-8"))
    history = previous.get("records", [])
except (FileNotFoundError, ValueError):
    history = []
added = []
status = {}
for game, appid in GAMES.items():
    url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={appid}"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "GachaWarsStats/1.0"})
        with urllib.request.urlopen(request, timeout=18) as response:
            data = json.load(response).get("response", {})
        count = data.get("player_count")
        if data.get("result") != 1 or not isinstance(count, int) or count < 0:
            raise ValueError("Steam API did not return a valid count")
        added.append({"game": game, "region": "global", "kind": "steam",
                      "store": "steam", "value": count, "date": now,
                      "source": "Steam Web API", "source_url": url})
        status[game] = {"ok": True, "checked_at": now, "players": count}
        print(f"{game}: {count}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        status[game] = {"ok": False, "checked_at": now, "error": str(error)[:150]}
        print(f"{game}: unavailable: {error}")
# Record no false zeros on transient API failures; retain historical snapshots.
# Deduplicate existing and newly sampled observations, rejecting bad records.
by_key = {}
for record in [*history, *added]:
    if not isinstance(record, dict):
        continue
    if record.get("game") not in GAMES or record.get("store") != "steam":
        continue
    if not isinstance(record.get("value"), int) or record["value"] < 0:
        continue
    if not isinstance(record.get("date"), str):
        continue
    by_key[(record["game"], record["date"])] = record
# Never truncate valid historical measurements. The old 2,000-row cap
# would silently destroy older Steam trend observations.
previous_keys = {
    (row["game"], row["date"])
    for row in history
    if isinstance(row, dict)
    and row.get("game") in GAMES and row.get("store") == "steam"
    and type(row.get("value")) is int and row["value"] >= 0
    and isinstance(row.get("date"), str)
}
missing = previous_keys - set(by_key)
if missing:
    raise RuntimeError(f"Steam history loss prevented: {len(missing)} snapshots missing")
history = sorted(by_key.values(), key=lambda r: r["date"])
OUT.write_text(json.dumps({"schema": "gacha-wars-steam-v1", "updated_at": now,
                            "game_status": status, "records": history}, ensure_ascii=False, indent=2) + "\n",
               encoding="utf-8")
