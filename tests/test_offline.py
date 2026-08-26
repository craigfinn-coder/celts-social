"""
Offline smoke test: exercises poll.py's full path with the network stubbed out,
so you can verify rendering and state handling without hitting the site.

    python tests/test_offline.py
"""
import io
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

import poll  # noqa: E402

# --- a stand-in featured image -------------------------------------------
_photo = Image.new("RGB", (1600, 1067), (24, 60, 38))
for y in range(1067):
    for x in range(0, 1600, 40):
        _photo.putpixel((x, y), (200, 220, 200))
_buf = io.BytesIO()
_photo.save(_buf, "JPEG", quality=90)
PHOTO_BYTES = _buf.getvalue()

POSTS = [
    {"id": 101, "slug": "celtic-lask-worst-ever-alan-brazil",
     "link": "https://celtsarehere.com/celtic-lask-worst-ever-alan-brazil/",
     "date_gmt": "2026-08-26T12:09:14",
     "title": {"rendered": "&#8216;I Was Screaming&#8217; &#8211; Celtic LASK "
                           "Defeat Branded &#8216;Worst Ever&#8217;"},
     "jetpack_featured_media_url": "https://celtsarehere.com/x.jpg"},
    {"id": 102, "slug": "celtic-transfers-spfl",
     "link": "https://celtsarehere.com/celtic-transfers-spfl/",
     "date_gmt": "2026-08-26T11:32:39",
     "title": {"rendered": "Celtic Alarming Transfer Issue Laid Bare After "
                           "Champions League Disaster"},
     "jetpack_featured_media_url": "https://celtsarehere.com/y.jpg"},
    {"id": 103, "slug": "no-image-post",
     "link": "https://celtsarehere.com/no-image-post/",
     "date_gmt": "2026-08-26T10:00:00",
     "title": {"rendered": "A Post With No Featured Image"}},
]


def stub_get(url, **kw):
    r = types.SimpleNamespace()
    if "wp-json" in url:
        slug = (kw.get("params") or {}).get("slug")
        data = [p for p in POSTS if p["slug"] == slug] if slug else POSTS
        r.json = lambda: data
        r.content = json.dumps(data).encode()
    else:
        r.json = lambda: {}
        r.content = PHOTO_BYTES
    return r


def run():
    poll._get = stub_get
    poll.rclone_upload = lambda paths: print(f"· (stub) would upload {len(paths)} files")

    state_file = ROOT / "state" / "seen.json"
    backup = state_file.read_text() if state_file.exists() else None
    state_file.write_text(json.dumps({"seen": [], "last_run": None}))

    try:
        print("\n--- run 1: bootstrap ---")
        sys.argv = ["poll.py"]
        assert poll.main() == 0
        seen = json.loads(state_file.read_text())["seen"]
        assert seen == [101, 102, 103], seen

        print("\n--- run 2: no new posts ---")
        assert poll.main() == 0

        print("\n--- run 3: one new post arrives ---")
        POSTS.insert(0, {
            "id": 104, "slug": "celtic-europa-league-pots",
            "link": "https://celtsarehere.com/celtic-europa-league-pots/",
            "date_gmt": "2026-08-26T13:47:06",
            "title": {"rendered": "Celtic Potential Europa League Opponents "
                                  "Revealed as Pot Places Emerge"},
            "jetpack_featured_media_url": "https://celtsarehere.com/z.jpg"})
        assert poll.main() == 0
        seen = json.loads(state_file.read_text())["seen"]
        assert 104 in seen, seen

        print("\n--- run 4: single-article mode ---")
        sys.argv = ["poll.py", "--url",
                    "https://celtsarehere.com/celtic-transfers-spfl/"]
        assert poll.main() == 0

        made = sorted(p.name for p in (ROOT / "out").glob("*.jpg"))
        print("\nRendered files:")
        for m in made:
            print("  ", m)

        for m in (ROOT / "out").glob("*_facebook.jpg"):
            assert Image.open(m).size == (1080, 1380), m
        for m in (ROOT / "out").glob("*_story.jpg"):
            assert Image.open(m).size == (1080, 1920), m

        print("\nAll assertions passed.")
    finally:
        if backup is not None:
            state_file.write_text(backup)


if __name__ == "__main__":
    run()
