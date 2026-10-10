#!/usr/bin/env python3
"""Collect YouTube video stats using a private GitHub Actions secret."""
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
target = root / "gacha-wars" / "youtube-targets.json"
output = root / "gacha-wars" / "youtube-data.json"
config = json.loads(target.read_text(encoding="utf-8"))
games = {"ww", "gi", "hsr", "zzz", "nte", "end"}
videos = [v for v in config.get("videos", []) if v.get("game") in games
          and re.fullmatch(r"[A-Za-z0-9_-]{11}", v.get("video_id", ""))]
key = os.environ.get("YOUTUBE_API_KEY", "").strip()
previous = {}
if output.exists():
    try:
        previous = json.loads(output.read_text(encoding="utf-8"))
    except ValueError:
        pass
records = previous.get("records", [])
status = "missing_api_key" if not key else "no_targets" if not videos else "ok"
now = datetime.now(timezone.utc).isoformat(timespec="seconds")
if key and videos:
    ids = list(dict.fromkeys(v["video_id"] for v in videos))[:50]
    url = "https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(
        {"part": "statistics,snippet", "id": ",".join(ids), "key": key})
    try:
        with urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "GACHA-WARS/1.0"}), timeout=25) as r:
            results = json.load(r).get("items", [])
        lookup = {v["id"]: v for v in results}
        for item in videos:
            vid = item["video_id"]
            res = lookup.get(vid, {})
            count = res.get("statistics", {}).get("viewCount")
            if count is None:
                continue
            count = int(count)
            if count < 0:
                continue
            records.append({
                "game": item["game"], "region": "global", "kind": "sns",
                "store": "youtube", "value": count, "date": now,
                "source": "YouTube Data API v3",
                "source_url": "https://www.youtube.com/watch?v=" + vid,
                "video_id": vid,
                "video_title": res.get("snippet", {}).get("title", "")
            })
        print("video observations:", len(records))
    except (OSError, ValueError, KeyError) as exc:
        status = "fetch_failed"
        print("YouTube stats unavailable:", type(exc).__name__, str(exc)[:120])
# Preserve every valid historical observation. Never discard old snapshots
# merely because the archive exceeded an arbitrary row limit.
def valid(record):
    return (
        isinstance(record, dict)
        and record.get("game") in games
        and record.get("kind") == "sns"
        and record.get("store") == "youtube"
        and isinstance(record.get("video_id"), str)
        and re.fullmatch(r"[A-Za-z0-9_-]{11}", record["video_id"])
        and isinstance(record.get("date"), str)
        and type(record.get("value")) is int
        and record["value"] >= 0
    )

original_keys = {
    (r["game"], r["video_id"], r["date"])
    for r in previous.get("records", []) if valid(r)
}
dedup = {
    (r["game"], r["video_id"], r["date"]): r
    for r in records if valid(r)
}
if original_keys - dedup.keys():
    raise RuntimeError("YouTube observation history would lose saved records")
records = sorted(dedup.values(), key=lambda x: x["date"])
output.write_text(json.dumps({
    "schema": "gacha-wars-youtube-v1", "updated_at": now,
    "status": status, "tracked_videos": len(videos), "records": records
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
