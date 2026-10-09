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
        print(f"{game}: {count}")
    except (OSError, ValueError, KeyError) as error:
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
history = sorted(by_key.values(), key=lambda r: r["date"])[-2000:]
OUT.write_text(json.dumps({"schema": "gacha-wars-steam-v1", "updated_at": now,
                            "records": history}, ensure_ascii=False, indent=2) + "\n",
               encoding="utf-8")
