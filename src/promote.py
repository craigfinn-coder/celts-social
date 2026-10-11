"""Repost proven winners to the second Facebook page (80k followers).

WordPress pings GitHub every hour (repository_dispatch "promote-check") with
the posts published in the last few hours and how many views each has today
(from Jetpack Stats). This script picks the best one and sends its existing
card to the second page through Buffer, link in the first comment.

Guard rails (all overridable with env / repo variables):
  PROMOTE_CHANNEL_ID   Buffer channel of the second page
  PROMOTE_MODE         shareNow | addToQueue | test | off   (default shareNow)
  PROMOTE_MIN_VIEWS    a story needs at least this many views   (default 500)
  PROMOTE_MAX_PER_DAY  cap per UK day                            (default 6)
  PROMOTE_GAP_MIN      minutes between promotions                (default 50)
  PROMOTE_MIN_AGE_MIN  story must be at least this old           (default 45)
  PROMOTE_MAX_AGE_MIN  ...and no older than this                 (default 300)
  PROMOTE_QUIET        UK hours with no posting, "23-7"          (default 23-7)

Only stories already sent to the main page (state/buffered.json) qualify, and
each story is promoted once at most (state/promoted.json).

    python src/promote.py --payload '<json>'      # from the workflow
    python src/promote.py --payload '<json>' --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buffer_post as bp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMOTED_FILE = ROOT / "state" / "promoted.json"
UK = ZoneInfo("Europe/London")
KEEP = 400


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


CHANNEL = os.environ.get("PROMOTE_CHANNEL_ID") or "67b9ce543b85969eafc88ecd"
MODE = (os.environ.get("PROMOTE_MODE") or "shareNow").strip()
MIN_VIEWS = env_int("PROMOTE_MIN_VIEWS", 500)
MAX_PER_DAY = env_int("PROMOTE_MAX_PER_DAY", 6)
GAP_MIN = env_int("PROMOTE_GAP_MIN", 50)
MIN_AGE = env_int("PROMOTE_MIN_AGE_MIN", 45)
MAX_AGE = env_int("PROMOTE_MAX_AGE_MIN", 300)
QUIET = os.environ.get("PROMOTE_QUIET") or "23-7"


def slug_of(url: str) -> str:
    return unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_promoted(data: dict) -> None:
    keep = sorted(data.items(), key=lambda kv: kv[1].get("at", ""))[-KEEP:]
    PROMOTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROMOTED_FILE.write_text(json.dumps(dict(keep), indent=2) + "\n")


def parse_time(s: str) -> dt.datetime | None:
    """date_gmt from WordPress ('2026-10-11T15:04:05', no zone = UTC)."""
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def in_quiet_hours(now_uk: dt.datetime) -> bool:
    try:
        start, end = (int(x) for x in QUIET.split("-"))
    except ValueError:
        return False
    h = now_uk.hour
    return (start <= h or h < end) if start > end else (start <= h < end)


def gate(promoted: dict, now: dt.datetime) -> str | None:
    """Reason not to post at all this hour, or None."""
    now_uk = now.astimezone(UK)
    if in_quiet_hours(now_uk):
        return f"quiet hours ({QUIET} UK) - nothing posted"
    times = [parse_time(v.get("at", "")) for v in promoted.values()
             if v.get("mode") != "test"]
    times = [t for t in times if t]
    today = [t for t in times if t.astimezone(UK).date() == now_uk.date()]
    if len(today) >= MAX_PER_DAY:
        return f"daily cap reached ({len(today)}/{MAX_PER_DAY})"
    if times:
        gap = (now - max(times)).total_seconds() / 60
        if gap < GAP_MIN:
            return f"last promotion {gap:.0f} min ago (gap {GAP_MIN} min)"
    return None


def rank(cands: list[dict], promoted: dict, buffered: dict,
         now: dt.datetime) -> list[dict]:
    """Eligible candidates, best first (views per hour since publish)."""
    out = []
    for c in cands:
        link = c.get("link") or ""
        slug = c.get("slug") or slug_of(link)
        views = int(c.get("views") or 0)
        pub = parse_time(c.get("date_gmt") or "")
        why = None
        if not slug or not pub:
            why = "missing slug/date"
        elif slug in promoted:
            why = "already on the 80k page"
        elif slug not in buffered:
            why = "not on the main page yet"
        else:
            age = (now - pub).total_seconds() / 60
            if age < MIN_AGE:
                why = f"too fresh ({age:.0f} min)"
            elif age > MAX_AGE:
                why = f"too old ({age:.0f} min)"
            elif views < MIN_VIEWS:
                why = f"{views} views < {MIN_VIEWS}"
        print(f"  {views:>6} views  {slug}  -> {why or 'ELIGIBLE'}")
        if why:
            continue
        hours = max((now - pub).total_seconds() / 3600, 0.5)
        out.append({**c, "slug": slug, "views": views, "pub": pub,
                    "rate": views / hours, "link": link or buffered[slug].get("link")})
    return sorted(out, key=lambda c: c["rate"], reverse=True)


def caption_for(c: dict) -> tuple[str, str]:
    """Headline + link from the card's caption file on the writers' page."""
    date = c["pub"].strftime("%Y-%m-%d")
    url = f"{bp.PAGES_BASE}/{date}_{c['slug']}.txt"
    try:
        r = requests.get(url, timeout=20)
        if r.ok:
            lines = r.text.splitlines()
            if lines and lines[0].strip():
                link = lines[2].strip() if len(lines) > 2 else c["link"]
                return lines[0].strip(), link or c["link"]
    except requests.RequestException:
        pass
    return (c.get("title") or "").strip(), c["link"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", default=os.environ.get("PING_PAYLOAD", ""))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", help="pretend time (ISO, for tests)")
    args = ap.parse_args()

    try:
        payload = json.loads(args.payload or "{}") or {}
    except ValueError:
        print("::error::promote: payload is not JSON")
        return 1
    mode = (payload.get("mode") or MODE).strip()
    if mode == "off":
        print("Promotion switched off.")
        return 0

    now = parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    promoted = load(PROMOTED_FILE)
    buffered = load(bp.SENT_FILE)
    cands = payload.get("candidates") or []
    print(f"{now.astimezone(UK):%a %H:%M} UK - {len(cands)} candidates, mode {mode}")

    if mode != "test":
        stop = gate(promoted, now)
        if stop:
            print(stop)
            return 0

    ranked = rank(cands, promoted, buffered, now)
    if not ranked:
        print("No proven winner this hour.")
        return 0
    best = ranked[0]
    headline, link = caption_for(best)
    if not headline:
        print(f"::error::promote: no headline for {best['slug']}")
        return 1
    image = f"{bp.PAGES_BASE}/{best['pub']:%Y-%m-%d}_{best['slug']}_facebook.jpg"
    print(f"Winner: {headline} ({best['views']} views, {best['rate']:.0f}/h)\n  {image}")
    if args.dry_run:
        return 0

    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        print("::error::promote: BUFFER_API_KEY not set")
        return 1
    if not bp.wait_until_live(image, limit=60):
        print(f"::error::promote: card not found at {image}")
        return 1
    inp = bp.build_input(headline, link, image, channel=CHANNEL, mode=mode)
    ok, msg = bp.create_post_with_retries(key, inp)
    if not ok:
        print(f"::error::promote: Buffer rejected '{headline}': {msg}")
        return 1
    print(f"  sent to the 80k page ({mode}): {msg}")
    if mode == "test":
        print("  test post: scheduled 7 days ahead - delete it in Buffer")
        return 0
    promoted[best["slug"]] = {
        "at": now.isoformat(timespec="seconds"), "views": best["views"],
        "link": link, "mode": mode, "buffer": msg}
    save_promoted(promoted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
