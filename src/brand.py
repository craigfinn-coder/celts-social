"""
Brand constants for CeltsAreHere social cards.

Every number here was measured off the two approved reference graphics,
so changing one changes the look. Sizes are for the 1080-wide canvas;
the story variant reuses the same type sizes and just moves blocks.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ---------------------------------------------------------------- colours
GREEN = (193, 255, 114)          # #C1FF72 - sampled from the reference tag
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# ---------------------------------------------------------------- type
HEADLINE_FONT = ASSETS / "fonts" / "BarlowCondensed-ExtraBold.ttf"
HEADLINE_SIZE = 100              # cap height 71px, matches reference exactly
LINE_PITCH_RATIO = 0.99          # measured 99px pitch at size 100
MIN_HEADLINE_SIZE = 62           # auto-shrink floor for very long headlines

KICKER_TEXT = "LATEST"
KICKER_CAP_H = 16
KICKER_WIDTH = 118               # tracking is solved to hit this width
KICKER_GAP = 61                  # cap-bottom of kicker to cap-top of headline

# ---------------------------------------------------------------- assets
TAG_IMG = ASSETS / "tag.png"     # "CELTSAREHERE LATEST" green flag
FOOTER_IMG = ASSETS / "footer.png"  # dotted arrows + CELTS ARE HERE logo

# ---------------------------------------------------------------- treatment
PHOTO_DARKEN = 0.86              # global multiply applied to the photo
VIGNETTE_STRENGTH = 0.55         # edge darkening
FOCAL_Y = 0.36                   # crop anchor - keeps heads in frame

# ---------------------------------------------------------------- layouts
# scrim: (start_y, end_y) of the black gradient, then solid below end_y
LAYOUTS = {
    "facebook": {
        "size": (1080, 1380),
        "tag_xy": (0, 56),
        "headline_cap_bottom": 1173,
        "headline_cap_top_limit": 872,
        "headline_max_width": 890,
        "footer_xy": (300, 1235),
        "scrim": (560, 1250),
    },
    "story": {
        # Instagram reserves roughly the top 250px and bottom 300px for its own
        # UI - the link sticker and the bin land there. Everything sits high
        # enough to leave ~418px clear underneath the logo.
        "size": (1080, 1920),
        "tag_xy": (0, 300),
        "headline_cap_bottom": 1340,
        "headline_cap_top_limit": 1040,
        "headline_max_width": 890,
        "footer_xy": (300, 1402),
        "scrim": (760, 1430),
    },
}
