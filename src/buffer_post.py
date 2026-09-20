"""Send freshly made Facebook cards to Buffer.

For every out/*_facebook.jpg made this run, create one Buffer post on the
main Celts Are Here Facebook page:
  * image  = the card, as published on the writers' page (GitHub Pages)
  * text   = the headline
  * first comment = the article link

Needs the BUFFER_API_KEY secret. Settings come from env:
  BUFFER_CHANNEL_ID  Facebook channel (default: main Celts Are Here page)
  BUFFER_MODE        addToQueue | shareNow | shareNext | test   (default addToQueue)
                     "test" schedules the post 7 days ahead so it can be
                     checked in Buffer and deleted before it goes out.
  PAGES_BASE         public base URL of the cards folder
  BUFFER_FORCE       "true" = post even if this article already went to Buffer

Every article sent is recorded in state/buffered.json, so a re-run (for
example a writer pressing "Resend social card" in WordPress) never posts the
same article to Facebook twice. Buffer is tried three times before giving up;
a failure is printed as a GitHub ::error:: so the run shows red.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
SENT_FILE = ROOT / "state" / "buffered.json"
KEEP_SENT = 400
FORCE = os.environ.get("BUFFER_FORCE", "").strip().lower() in ("1", "true", "yes")
RETRY_WAITS = (0, 20, 60)
API = "https://api.buffer.com"

CHANNEL = os.environ.get("BUFFER_CHANNEL_ID") or "6aadba11ea19ca0bde7f8ac0"
MODE = (os.environ.get("BUFFER_MODE") or "addToQueue").strip()
PAGES_BASE = (os.environ.get("PAGES_BASE")
              or "https://craigfinn-coder.github.io/celts-social/cards").rstrip("/")
COMMENT_PREFIX = os.environ.get("BUFFER_COMMENT_PREFIX", "Full story: ")

MUTATION = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}
"""


def article_key(card: Path) -> str:
    """2026-09-19_some-slug_facebook.jpg -> some-slug"""
    stem = card.stem.rsplit("_", 1)[0]
    return stem.split("_", 1)[1] if "_" in stem else stem


def load_sent() -> dict:
    try:
        return json.loads(SENT_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_sent(sent: dict) -> None:
    keep = sorted(sent.items(), key=lambda kv: kv[1].get("at", ""))[-KEEP_SENT:]
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(dict(keep), indent=2) + "\n")


def read_caption(card: Path) -> tuple[str, str] | None:
    """Card 2026-09-19_slug_facebook.jpg -> caption file 2026-09-19_slug.txt"""
    stem = card.stem.rsplit("_", 1)[0]
    txt = card.with_name(f"{stem}.txt")
    if not txt.exists():
        print(f"! no caption file for {card.name} - skipped")
        return None
    lines = txt.read_text().splitlines()
    headline = lines[0].strip() if lines else ""
    link = lines[2].strip() if len(lines) > 2 else ""
    if not headline or not link:
        print(f"! caption file {txt.name} is missing headline or link - skipped")
        return None
    return headline, link


def wait_until_live(url: str, limit: int = 420) -> bool:
    """GitHub Pages takes a minute or so to publish. Buffer must be able to
    fetch the image, so wait for it (with a cache-buster)."""
    end = time.time() + limit
    while time.time() < end:
        try:
            r = requests.head(f"{url}?_cb={int(time.time())}", timeout=15,
                              allow_redirects=True)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(15)
    return False


def build_input(headline: str, link: str, image_url: str) -> dict:
    inp = {
        "channelId": CHANNEL,
        "text": headline,
        "schedulingType": "automatic",
        "assets": [{"image": {"url": image_url,
                              "metadata": {"altText": headline}}}],
        "metadata": {"facebook": {"type": "post",
                                  "firstComment": f"{COMMENT_PREFIX}{link}"}},
    }
    if MODE == "test":
        due = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=7)).replace(
            hour=8, minute=0, second=0, microsecond=0)
        inp["mode"] = "customScheduled"
        inp["dueAt"] = due.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    else:
        inp["mode"] = MODE
    return inp


def create_post_with_retries(key: str, inp: dict) -> tuple[bool, str]:
    msg = ""
    for n, wait in enumerate(RETRY_WAITS, 1):
        if wait:
            print(f"  retrying in {wait}s (attempt {n}/{len(RETRY_WAITS)})")
            time.sleep(wait)
        try:
            ok, msg = create_post(key, inp)
        except requests.RequestException as exc:
            ok, msg = False, f"network error: {exc}"
        if ok:
            return ok, msg
        print(f"  Buffer said no: {msg}")
    return False, msg


def create_post(key: str, inp: dict) -> tuple[bool, str]:
    r = requests.post(API, timeout=60,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"},
                      json={"query": MUTATION, "variables": {"input": inp}})
    try:
        body = r.json()
    except ValueError:
        return False, f"HTTP {r.status_code}: {r.text[:300]}"
    if body.get("errors"):
        return False, json.dumps(body["errors"])[:500]
    res = (body.get("data") or {}).get("createPost") or {}
    if "post" in res:
        return True, f"post {res['post']['id']} due {res['post'].get('dueAt')}"
    return False, res.get("message") or json.dumps(body)[:500]


def main() -> int:
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not key:
        print("BUFFER_API_KEY not set - nothing sent to Buffer.")
        return 0
    cards = sorted(OUT_DIR.glob("*_facebook.jpg"))
    if not cards:
        print("No Facebook cards this run - nothing sent to Buffer.")
        return 0

    sent = load_sent()
    failed = 0
    for card in cards:
        art = article_key(card)
        print(f"- {card.name}")
        if art in sent and not FORCE and MODE != "test":
            print(f"  already sent to Buffer {sent[art].get('at', '')} "
                  "- not posting it twice")
            continue
        cap = read_caption(card)
        if not cap:
            print(f"::error::Buffer: no caption for {card.name}")
            failed += 1
            continue
        headline, link = cap
        image_url = f"{PAGES_BASE}/{card.name}"
        if not wait_until_live(image_url):
            print(f"::error::Buffer: card never went live at {image_url} "
                  "- NOT posted. Use 'Resend social card' in WordPress.")
            failed += 1
            continue
        ok, msg = create_post_with_retries(key, build_input(headline, link, image_url))
        if ok:
            print(f"  sent to Buffer ({MODE}): {msg}")
            if MODE != "test":
                sent[art] = {"at": dt.datetime.now(dt.timezone.utc).isoformat(
                    timespec="seconds"), "link": link, "buffer": msg}
                save_sent(sent)
        else:
            print(f"::error::Buffer rejected '{headline}' after "
                  f"{len(RETRY_WAITS)} tries: {msg}. NOT posted to Facebook. "
                  "Use 'Resend social card' in WordPress to try again.")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
