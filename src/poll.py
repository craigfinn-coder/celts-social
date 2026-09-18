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
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
PUBLISH_RECHECKS = 36
PUBLISH_RECHECK_SECONDS = 10


def article_slug(url: str) -> str:
    """Compare article URLs independently of query strings and trailing slashes."""
    return unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])

# Identify honestly, but in the conventional shape security plugins expect.
# An anonymous bot signature is what got this blocked in the first place;
# this string is also what you would allowlist if it ever happens again.
UA = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CeltsAreHereCards/1.0; "
        "+https://celtsarehere.com) social-card-generator"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


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


def fetch_posts(per_page: int = PER_PAGE) -> list[dict]:
    """The latest-posts list. NOTE: can be up to five minutes stale.

    celtsarehere.com's BunnyCDN caches /wp-json by PATH ONLY - it ignores the
    query string entirely. So per_page, slug= and any cache-buster make no
    difference: every /wp-json/wp/v2/posts?... request gets whatever list was
    cached first, for up to 5 minutes. That is what made every card ~6 minutes
    late. Never use this list to find a specific, just-published article - use
    fetch_post_by_id / fetch_post_by_url, which hit unique paths instead.
    """
    params = {
        "per_page": per_page,
        "_embed": "wp:featuredmedia",
        "orderby": "date",
        "order": "desc",
        "_cb": f"{int(time.time() * 1000)}{os.getpid()}",  # harmless if ignored
    }
    return _get(API, params=params).json()


def _usable(post, want_id: int | None = None) -> bool:
    return (isinstance(post, dict) and post.get("id")
            and (want_id is None or int(post["id"]) == int(want_id))
            and post.get("status", "publish") == "publish"
            and (post.get("title") or {}).get("rendered"))


def fetch_post_by_id(post_id) -> dict | None:
    """/wp-json/wp/v2/posts/<id> is a unique path, so the CDN has nothing
    stale for it the first time it is asked for straight after publishing."""
    try:
        r = requests.get(f"{API}/{int(post_id)}",
                         params={"_embed": "wp:featuredmedia"},
                         headers=UA, timeout=20)
        if r.status_code != 200:
            print(f"  · post {post_id}: HTTP {r.status_code}", file=sys.stderr)
            return None
        post = r.json()
    except Exception as exc:                # noqa: BLE001
        print(f"  · post {post_id}: {exc}", file=sys.stderr)
        return None
    return post if _usable(post, post_id) else None


def _article_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200:
            print(f"  · {url}: HTTP {r.status_code}", file=sys.stderr)
            return None
        return r.content.decode("utf-8", "replace")
    except Exception as exc:                # noqa: BLE001
        print(f"  · {url}: {exc}", file=sys.stderr)
        return None


def _meta(html: str, prop: str) -> str | None:
    for pat in (rf'<meta[^>]+property=["\']{prop}["\'][^>]+content=["\']([^"\']+)',
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{prop}["\']'):
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1)
    return None


def fetch_post_by_url(url: str, post_id=None) -> dict | None:
    """Find one specific article without touching the stale list.

    1. by ID (from the ping) -> /wp-json/wp/v2/posts/<id>
    2. read the article page (its own unique URL), pull the ID out of it, 1.
    3. build the post from the page's og:title / og:image as a last resort.
    """
    if post_id:
        post = fetch_post_by_id(post_id)
        if post:
            return post
    if not url:
        return None
    html = _article_html(url)
    if not html:
        return None
    m = (re.search(r'/wp-json/wp/v2/posts/(\d+)', html)
         or re.search(r'\bpostid-(\d+)', html))
    if m and str(m.group(1)) != str(post_id or ""):
        post = fetch_post_by_id(m.group(1))
        if post:
            return post
    title, image = _meta(html, "og:title"), _meta(html, "og:image")
    if not (m and title and image):
        return None
    import html as _html
    title = re.sub(r"\s*[|\u2013-]\s*Celts Are Here\s*$", "",
                   _html.unescape(title), flags=re.I)
    published = _meta(html, "article:published_time") or ""
    return {"id": int(m.group(1)), "slug": article_slug(url), "link": url,
            "status": "publish", "title": {"rendered": title},
            "date_gmt": published[:19], "jetpack_featured_media_url": image}


def fetch_hinted(urls: list[str], ids: list = ()) -> list[dict]:
    """Fetch the specific articles WordPress told us about."""
    found: list[dict] = []
    ids = list(ids)
    for i, url in enumerate(urls):
        pid = ids[i] if i < len(ids) else None
        post = fetch_post_by_url(url, pid)
        if post:
            found.append(post)
    return found


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
        print("\u00b7 RCLONE_REMOTE unset - leaving cards in out/ only")
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

    # Caption file: headline as written (not shouted, not title-cased - that
    # was turning "McGowan's" into "Mcgowan'S"), then the publish time so the
    # gallery can order same-day cards properly, then the link.
    import html as _html
    nice = re.sub(r"\s+", " ", _html.unescape(title or "")).strip()
    caption = OUT_DIR / f"{date}_{slug}.txt"
    caption.write_text(f"{nice}\n{post.get('date_gmt', '')}\n{link}\n")
    written.append(caption)
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true",
                    help="mark current posts as seen without rendering")
    ap.add_argument("--url", help="render one article by URL, ignoring state")
    ap.add_argument("--headline", help="override the headline text")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--expect-new", action="store_true",
                    help="run was triggered by a publish ping: if nothing new "
                         "shows up yet, re-check for up to six minutes")
    ap.add_argument("--hint-id", action="append", default=[],
                    help="post ID from the ping, same order as --hint")
    ap.add_argument("--hint", action="append", default=[],
                    help="article URL the ping said was just published "
                         "(may be given more than once)")
    args = ap.parse_args()

    # ---- manual single-article mode
    if args.url:
        # (The old ?slug= lookup silently returned the cached latest-posts
        # list, so a hand-run could render the WRONG article.)
        post = fetch_post_by_url(args.url.split("?")[0])
        if not post:
            print(f"Couldn't find the article at {args.url}", file=sys.stderr)
            return 1
        print(f"Rendering {post['link']}")
        files = process(post, args.headline)
        if files and not args.no_upload:
            rclone_upload([f for f in files if f.suffix == ".jpg"])
        return 0

    state = load_state()
    seen = set(state["seen"])

    hints = [u for u in args.hint if u]
    expected_slugs = {article_slug(u) for u in hints if article_slug(u)}
    observed: dict[int, dict] = {}

    def look() -> tuple[list[dict], list[dict]]:
        # The exact article first - that is the one a writer is waiting for.
        hinted = [p for p in fetch_hinted(hints, args.hint_id)
                  if p.get("status", "publish") == "publish"]
        try:
            posts = fetch_posts()
        except Exception as exc:            # noqa: BLE001
            # The list is only a backstop for missed pings; never let it
            # stop the pinged article from being made.
            if not hinted:
                raise
            print(f"  · latest-posts list unavailable: {exc}", file=sys.stderr)
            posts = []
        # Keep discoveries across retries; a stale response must not erase one.
        for p in posts + hinted:
            if p.get("status", "publish") == "publish":
                observed[p["id"]] = p
        fresh = [p for p in observed.values() if p["id"] not in seen]
        fresh.sort(key=lambda p: p.get("date_gmt") or "")
        return posts, fresh

    posts, fresh = look()
    print(f"Feed returned {len(posts)} posts, {len(seen)} already seen")

    if args.bootstrap or (not seen and not os.environ.get("CAH_BACKFILL")):
        state["seen"] = [p["id"] for p in posts]
        save_state(state)
        print(f"Bootstrapped: {len(state['seen'])} existing posts marked seen. "
              "Future runs will only pick up genuinely new articles.")
        return 0

    # An older unseen post does NOT satisfy a ping for a different article.
    # That used to end retries early and keep the gallery exactly one behind.
    def waiting_for_publish() -> bool:
        if expected_slugs:
            available = {p.get("slug") or article_slug(p.get("link", ""))
                         for p in observed.values()}
            return not expected_slugs.issubset(available)
        return not fresh

    tries = 0
    while args.expect_new and waiting_for_publish() and tries < PUBLISH_RECHECKS:
        tries += 1
        print(f"  waiting for the published article "
              f"- re-checking in {PUBLISH_RECHECK_SECONDS}s "
              f"({tries}/{PUBLISH_RECHECKS})", flush=True)
        time.sleep(PUBLISH_RECHECK_SECONDS)
        posts, fresh = look()

    if args.expect_new and waiting_for_publish():
        print("::warning::The published article is still unavailable after "
              "six minutes. Check the WordPress API/publish hook; "
              "this ping has not been fulfilled.", file=sys.stderr)

    if not fresh:
        print("No new articles.")
        save_state(state)
        return 0

    if len(fresh) > MAX_PER_RUN:
        print(f"! {len(fresh)} new posts, capping this run at {MAX_PER_RUN}")
        # Make room for the ping's exact article even when clearing a backlog.
        fresh.sort(key=lambda p: (p.get("slug") in expected_slugs,
                                 p.get("date_gmt") or ""))
        fresh = fresh[-MAX_PER_RUN:]

    produced: list[Path] = []
    for post in fresh:
        title = (post.get("title") or {}).get("rendered", "")
        print(f"\nNEW #{post['id']}: {clean_headline(title)}")
        try:
            files = process(post)
            produced += files
            if files:
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
