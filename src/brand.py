"""
Brand constants for CeltsAreHere social cards - "news card" style (Sept 2026).

Every number here was measured off the approved 1080x1380 news-card mockup,
so changing one changes the look. The story variant reuses the same type
sizes and just moves blocks clear of Instagram's own UI.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# ---------------------------------------------------------------- colours
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
INK = (13, 33, 21)               # #0D2115 - label text
DEEP = (8, 21, 14)               # #08150E - solid fill under the headline
BAND = (46, 107, 65)             # #2E6B41 - footer band
SUB_GREEN = (101, 212, 133)      # #65D485 - subheading

# ---------------------------------------------------------------- fonts
HEADLINE_FONT = ASSETS / "fonts" / "Anton-Regular.ttf"
UI_FONT = ASSETS / "fonts" / "Archivo-Bold.ttf"

# ---------------------------------------------------------------- headline
HEADLINE_SIZE = 87               # cap height 75px, matches mockup
LINE_PITCH_RATIO = 90 / 87       # measured 90px baseline-to-baseline
MIN_HEADLINE_SIZE = 60           # auto-shrink floor for very long headlines
MARGIN_X = 64                    # left edge of label, subheading, headline

# ---------------------------------------------------------------- label (white box, top left)
LABEL_TEXT = "NEWS"
LABEL_SIZE = 29                  # cap 20px
LABEL_TRACKING = 4.4             # px between letters
LABEL_PAD_X = 31
LABEL_BOX_H = 61

# ---------------------------------------------------------------- subheading
SUB_TEXT = "CELTIC NEWS"
SUB_SIZE = 22                    # cap 16px
SUB_TRACKING = 3.9
SUB_GAP = 55                     # sub cap-bottom -> headline cap-top

# ---------------------------------------------------------------- logo (top right)
LOGO_IMG = ASSETS / "logo-white.png"
LOGO_W = 171
LOGO_RIGHT = 1008                # right ink edge

# ---------------------------------------------------------------- footer band
CTA_SIZE = 29                    # cap 20px
CTA_TRACKING = 2.4
CTA_X = 144
ICON_D = 53                      # circle diameter
ICON_CX = 90
ICON_STROKE = 3

# ---------------------------------------------------------------- photo treatment
FOCAL_Y = 0.30                   # crop anchor - keeps heads in frame
TOP_SHADE = 0.35                 # max darkening at the very top (logo legibility)
TOP_SHADE_H = 300
SCRIM_H = 440                    # photo -> solid DEEP fade length
SCRIM_BELOW_CAP = 105            # solid starts this far below headline cap-top

# ---------------------------------------------------------------- story frame
STORY_BLUR = 40                  # backdrop blur radius
STORY_BG_KEEP = 0.45             # how much photo shows through the deep green
STORY_RADIUS = 28                # panel corner radius

# ---------------------------------------------------------------- layouts
LAYOUTS = {
    "facebook": {
        "size": (1080, 1380),
        "top_y": 78,                     # label box top / logo top
        "headline_cap_bottom": 1180,
        "headline_cap_top_limit": 700,   # tallest the block may grow to
        "headline_max_width": 1080 - 2 * MARGIN_X,
        "band": (1243, 1380),            # green footer band y-range
        "cta": "FULL STORY IN THE FIRST COMMENT",
    },
    # The card used inside the story frame: same design, CTA wording
    # dropped, band reduced to a slim green strip, headline nudged down
    # to close the gap.
    "panel": {
        "size": (1080, 1380),
        "top_y": 78,
        "headline_cap_bottom": 1280,
        "headline_cap_top_limit": 800,
        "headline_max_width": 1080 - 2 * MARGIN_X,
        "band": (1356, 1380),
        "cta": None,
    },
    "story": {
        # Framed: the panel above, scaled to panel_w, over a blurred copy of
        # the photo. Instagram's top UI sits over the blurred area above the
        # panel; the space below is where the link sticker goes.
        "size": (1080, 1920),
        "framed": True,
        "panel": "panel",
        "panel_w": 940,
        "panel_y": 280,
    },
}
