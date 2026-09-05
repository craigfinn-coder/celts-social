#!/usr/bin/env python3
"""
Builds the writers' gallery page from whatever cards are in <pages>/cards,
newest first, and prunes the oldest so the site never grows without limit.

    python src/gallery.py pages
"""

from __future__ import annotations

import html
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")

KEEP = int(os.environ.get("CAH_GALLERY_KEEP", "240"))   # cards kept on the site


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>CeltsAreHere - Social Cards</title>
<style>
  :root {{ --green:#C1FF72; --bg:#0b0b0b; --card:#161616; --line:#262626; --dim:#8b8b8b; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:#fff;
         font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }}
  header {{ padding:28px 24px 20px; border-bottom:1px solid var(--line); }}
  .flag {{ display:inline-block; background:var(--green); color:#000; font-weight:700;
           letter-spacing:.18em; font-size:12px; padding:5px 12px; }}
  h1 {{ font-size:24px; margin:14px 0 6px; }}
  .sub {{ color:var(--dim); font-size:13px; margin:0; }}
  main {{ padding:24px; display:grid; gap:22px;
          grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); max-width:1600px; }}
  .item {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
           overflow:hidden; display:flex; flex-direction:column; }}
  .item img {{ width:100%; display:block; background:#000; }}
  .meta {{ padding:12px 14px 14px; }}
  .hl {{ font-weight:600; font-size:14px; margin:0 0 4px; }}
  .when {{ color:var(--dim); font-size:12px; margin:0 0 10px; }}
  .row {{ display:flex; gap:8px; flex-wrap:wrap; }}
  a.btn {{ background:var(--green); color:#000; text-decoration:none; font-weight:700;
           font-size:12px; padding:7px 12px; border-radius:5px; }}
  a.btn.ghost {{ background:transparent; color:var(--green); border:1px solid var(--green); }}
  .empty {{ padding:60px 24px; color:var(--dim); }}
  footer {{ padding:20px 24px 40px; color:var(--dim); font-size:12px;
            border-top:1px solid var(--line); }}
</style>
</head>
<body>
<header>
  <span class="flag">CELTSAREHERE LATEST</span>
  <h1>Social cards</h1>
  <p class="sub">Auto-generated from new articles. Updated {updated} &middot; {count} cards</p>
</header>
<main>
{items}
</main>
<footer>
  Right-click any image and choose &ldquo;Save Image As&rdquo;, or use the Download button.
  Cards are removed from this page after the newest {keep} - grab anything you want to keep.
</footer>
</body>
</html>
"""

ITEM = """  <div class="item">
    <img src="cards/{fb}" alt="{alt}" loading="lazy">
    <div class="meta">
      <p class="hl">{headline}</p>
      <p class="when">{when}</p>
      <div class="row">
        <a class="btn" href="cards/{fb}" download>Download 4:5</a>
        {story_btn}
      </div>
    </div>
  </div>
"""

STORY_BTN = '<a class="btn ghost" href="cards/{story}" download>Story 9:16</a>'
LINK_BTN = '<a class="btn ghost" href="{link}" target="_blank" rel="noopener">Article</a>'


def headline_from(stem: str) -> str:
    """'2026-08-26_celtic-transfers-spfl_facebook' -> 'Celtic Transfers Spfl'"""
    body = stem.split("_", 1)[1] if "_" in stem else stem
    for suffix in ("_facebook", "_story"):
        if body.endswith(suffix):
            body = body[: -len(suffix)]
    return body.replace("-", " ").strip().title() or "Untitled"


def caption_for(cards: Path, key: str, stem_fallback: str):
    """
    poll.py drops a '<date>_<slug>.txt' beside each card holding the real
    headline and the article URL. Prefer that over guessing from the filename.
    """
    f = cards / f"{key}.txt"
    if f.exists():
        parts = [p.strip() for p in f.read_text().split("\n") if p.strip()]
        if parts:
            link = parts[-1] if parts[-1].startswith("http") else ""
            when = next((p for p in parts[1:] if ISO_RE.match(p)), "")
            return parts[0], link, when
    return headline_from(stem_fallback), "", ""


def build(pages_dir: Path) -> None:
    cards = pages_dir / "cards"
    cards.mkdir(parents=True, exist_ok=True)

    # Group the two variants of each article together.
    groups: dict[str, dict[str, Path]] = {}
    for p in cards.glob("*.jpg"):
        stem = p.stem
        if stem.endswith("_facebook"):
            key, variant = stem[: -len("_facebook")], "facebook"
        elif stem.endswith("_story"):
            key, variant = stem[: -len("_story")], "story"
        else:
            key, variant = stem, "facebook"
        groups.setdefault(key, {})[variant] = p

    # Newest first. Same-day cards used to sort alphabetically by slug, which
    # put the day's stories in the wrong order; use the publish time when the
    # caption file carries it, and fall back to the filename key.
    def sort_key(kv):
        _, when = kv[0], caption_for(cards, kv[0], kv[0])[2]
        return (when or kv[0][:10], kv[0])

    ordered = sorted(groups.items(), key=sort_key, reverse=True)

    # Prune: keep the newest KEEP articles, delete the rest off the site.
    for key, variants in ordered[KEEP:]:
        for p in variants.values():
            p.unlink(missing_ok=True)
        caption = cards / f"{key}.txt"
        caption.unlink(missing_ok=True)
    ordered = ordered[:KEEP]

    items = []
    for key, variants in ordered:
        fb = variants.get("facebook") or next(iter(variants.values()))
        story = variants.get("story")
        when = key.split("_", 1)[0]
        raw_headline, link, _when = caption_for(cards, key, key)
        headline = html.escape(raw_headline)
        buttons = ""
        if story:
            buttons += STORY_BTN.format(story=html.escape(story.name))
        if link:
            buttons += LINK_BTN.format(link=html.escape(link, quote=True))
        items.append(ITEM.format(
            fb=html.escape(fb.name),
            alt=headline,
            headline=headline,
            when=html.escape(when),
            story_btn=buttons,
        ))

    body = "".join(items) or '<p class="empty">No cards yet. The next new article will appear here.</p>'
    (pages_dir / "index.html").write_text(PAGE.format(
        updated=datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        count=len(ordered),
        keep=KEEP,
        items=body,
    ))
    (pages_dir / ".nojekyll").write_text("")
    print(f"gallery: {len(ordered)} cards")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "pages"))
