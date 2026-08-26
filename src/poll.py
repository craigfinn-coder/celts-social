#!/usr/bin/env python3
"""
Poll celtsarehere.com for new articles and render social cards for each one.

Normal (scheduled) run:
    python src/poll.py

First ever run - mark everything currently published as already seen so you
don't get 20 cards in one go:
    python src/poll.py --bootstrap

Regenerate a card by hand for any article:
    python src/poll.py --url https://celtsarehere.com/some-article/

Override the headline (for when the SEO title isn't the social hook):
    python src/poll.py --url https://... --headline "Your Punchier Line"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import render_card, slugify, clean_headline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "seen.json"
OUT_DIR = ROOT / "out"

SITE = os.environ.get("CAH_SITE", "https://celtsarehere.com")
API = f"{SITE}/wp-json/wp/v2/posts"
VARIANTS = [v.strip() for v in
            os.environ.get("CAH_VARIANTS", "facebook,story").split(",") if v.strip()]
PER_PAGE = int(os.environ.get("CAH_PER_PAGE", "15"))
MAX_PER_RUN = int(os.environ.get("CAH_MAX_PER_RUN", "6"))
KEEP_SEEN = 400

UA = {"User-Agent": "CeltsAreHere-SocialBot/1.0 (+https://celtsarehere.com)"}


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            print("! state file corrupt, starting fresh", file=sys.stderr)
    return {"seen": [], "last_run": None}


def save_state(state: dict) -> None:
    state["seen"] = state["seen"][-KEEP_SEEN:]
    state["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def _get(url: str, **kw):
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=30, **kw)
            r.raise_for_status()
            return r
        except Exception as exc:            # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after 3 tries: {last}")


def fetch_posts(per_page: int = PER_PAGE, slug: str | None = None) -> list[dict]:
    params = {
        "per_page": 1 if slug else per_page,
        "_embed": "wp:featuredmedia",
        "orderby": "date",
        "order": "desc",
    }
    if slug:
        params["slug"] = slug
    return _get(API, params=params).json()


def og_image(article_url: str) -> str | None:
    """Last resort: read og:image off the article page itself."""
    import re as _re
    try:
        html = _get(article_url).content.decode("utf-8", "replace")
    except Exception:                       # noqa: BLE001
        return None
    m = _re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        html, _re.I)
    return m.group(1) if m else None


def featured_image_url(post: dict) -> str | None:
    """Jetpack exposes it directly; fall back to embedded media, then og:image."""
    direct = post.get("jetpack_featured_media_url")
    if direct:
        return direct

    media = (post.get("_embedded") or {}).get("wp:featuredmedia") or []
    if media and isinstance(media[0], dict):
        sizes = (media[0].get("media_details") or {}).get("sizes") or {}
        for name in ("full", "1536x1536", "large", "medium_large"):
            if name in sizes and sizes[name].get("source_url"):
                return sizes[name]["source_url"]
        if media[0].get("source_url"):
            return media[0]["source_url"]

    if post.get("link"):
        return og_image(post["link"])
    return None


# --------------------------------------------------------------------------
# delivery
# --------------------------------------------------------------------------

def rclone_upload(paths: list[Path]) -> None:
    """Copy finished cards to the shared cloud folder, if one is configured."""
    remote = os.environ.get("RCLONE_REMOTE")
    if not remote:
        print("· RCLONE_REMOTE unset - leaving cards in out/ only")
        return
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = f"{remote.rstrip('/')}/{day}"
    for p in paths:
        try:
            subprocess.run(["rclone", "copy", str(p), dest, "--no-traverse"],
                           check=True, capture_output=True, timeout=180)
            print(f"  -> uploaded {p.name} to {dest}")
        except subprocess.CalledProcessError as exc:
            print(f"  ! upload failed for {p.name}: "
                  f"{exc.stderr.decode(errors='replace')[:300]}", file=sys.stderr)
        except Exception as exc:            # noqa: BLE001
            print(f"  ! upload failed for {p.name}: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# the job
# --------------------------------------------------------------------------

def process(post: dict, headline_override: str | None = None) -> list[Path]:
    title = headline_override or (post.get("title") or {}).get("rendered", "")
    link = post.get("link", "")
    img_url = featured_image_url(post)

    if not img_url:
        print(f"  ! no featured image on {link} - skipped")
        return []

    print(f"  photo: {img_url}")
    photo = _get(img_url).content

    date = (post.get("date_gmt") or datetime.now(timezone.utc).isoformat())[:10]
    slug = slugify(post.get("slug") or clean_headline(title).lower())
    written: list[Path] = []

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        card = render_card(photo, title, variant=variant)
        out = OUT_DIR / f"{date}_{slug}_{variant}.jpg"
        card.save(out, quality=92, optimize=True, progressive=True)
        written.append(out)
        print(f"  wrote {out.name} ({card.size[0]}x{card.size[1]})")

    caption = OUT_DIR / f"{date}_{slug}.txt"
    caption.write_text(f"{clean_headline(title).title()}\n\n{link}\n")
    written.append(caption)
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true",
                    help="mark current posts as seen without rendering")
    ap.add_argument("--url", help="render one article by URL, ignoring state")
    ap.add_argument("--headline", help="override the headline text")
    ap.add_argument("--no-upload", action="store_true")
    args = ap.parse_args()

    # ---- manual single-article mode
    if args.url:
        slug = [s for s in args.url.rstrip("/").split("/") if s][-1]
        posts = fetch_posts(slug=slug)
        if not posts:
            print(f"No post found for slug {slug!r}", file=sys.stderr)
            return 1
        print(f"Rendering {posts[0]['link']}")
        files = process(posts[0], args.headline)
        if files and not args.no_upload:
            rclone_upload([f for f in files if f.suffix == ".jpg"])
        return 0

    state = load_state()
    seen = set(state["seen"])
    posts = fetch_posts()
    print(f"Feed returned {len(posts)} posts, {len(seen)} already seen")

    if args.bootstrap or (not seen and not os.environ.get("CAH_BACKFILL")):
        state["seen"] = [p["id"] for p in posts]
        save_state(state)
        print(f"Bootstrapped: {len(state['seen'])} existing posts marked seen. "
              "Future runs will only pick up genuinely new articles.")
        return 0

    fresh = [p for p in posts if p["id"] not in seen]
    fresh.sort(key=lambda p: p.get("date_gmt") or "")

    if not fresh:
        print("No new articles.")
        save_state(state)
        return 0

    if len(fresh) > MAX_PER_RUN:
        print(f"! {len(fresh)} new posts, capping this run at {MAX_PER_RUN}")
        fresh = fresh[-MAX_PER_RUN:]

    produced: list[Path] = []
    for post in fresh:
        title = (post.get("title") or {}).get("rendered", "")
        print(f"\nNEW #{post['id']}: {clean_headline(title)}")
        try:
            produced += process(post)
            state["seen"].append(post["id"])
        except Exception as exc:            # noqa: BLE001
            # Leave it unseen so the next run retries it.
            print(f"  ! failed: {exc}", file=sys.stderr)

    save_state(state)

    if produced and not args.no_upload:
        rclone_upload([p for p in produced if p.suffix == ".jpg"])

    print(f"\nDone: {len([p for p in produced if p.suffix == '.jpg'])} cards from "
          f"{len(fresh)} article(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
