"""
Renders a CeltsAreHere social card from a photo + headline.

    from render import render_card
    img = render_card(photo_bytes, "CELTIC STAR SET FOR EXIT", variant="facebook")
    img.save("card.jpg", quality=92)

Layout: "news card" - NEWS label + logo on top, left-aligned Anton headline
over a dark green fade, green CTA band along the bottom. Stories show the
card (without CTA wording) as a rounded panel over a blurred copy of the photo.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import brand


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

def _font(size: int, path=None) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path or brand.HEADLINE_FONT), size)


def _ink(font: ImageFont.FreeTypeFont, text: str):
    """Ink box of `text` when drawn at origin with the default 'la' anchor."""
    return font.getbbox(text)


def _width(font: ImageFont.FreeTypeFont, text: str) -> int:
    b = _ink(font, text)
    return b[2] - b[0]


def clean_headline(raw: str) -> str:
    """WordPress titles arrive with entities and curly punctuation."""
    import html

    t = html.unescape(raw or "")
    t = (t.replace("‘", "'").replace("’", "'")
          .replace("“", '"').replace("”", '"')
          .replace("–", "-").replace("—", "-")
          .replace(" ", " "))
    t = re.sub(r"\s+", " ", t).strip()
    return t.upper()


def _wrap(font: ImageFont.FreeTypeFont, text: str, max_w: int):
    """Greedy wrap. Returns None if any single word overflows."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if _width(font, w) > max_w:
            return None
        trial = f"{cur} {w}".strip()
        if _width(font, trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_headline(text: str, layout: dict):
    """
    Largest size at which the wrapped headline fits between the top limit and
    its fixed cap-bottom line. Returns (font, lines, pitch).
    """
    max_w = layout["headline_max_width"]
    bottom = layout["headline_cap_bottom"]
    top_limit = layout["headline_cap_top_limit"]

    size = brand.HEADLINE_SIZE
    while size >= brand.MIN_HEADLINE_SIZE:
        font = _font(size)
        lines = _wrap(font, text, max_w)
        if lines:
            pitch = round(size * brand.LINE_PITCH_RATIO)
            cap_h = _cap_h(font)
            if bottom - ((len(lines) - 1) * pitch + cap_h) >= top_limit:
                return font, lines, pitch
        size -= 3

    font = _font(brand.MIN_HEADLINE_SIZE)
    lines = _wrap(font, text, max_w) or [text]
    return font, lines, round(brand.MIN_HEADLINE_SIZE * brand.LINE_PITCH_RATIO)


def _cap_h(font) -> int:
    b = _ink(font, "H")
    return b[3] - b[1]


def _draw_tracked(draw, x, cap_top, text, font, fill, tracking: float) -> float:
    """Draw `text` letter-spaced, left ink edge at x, caps starting at cap_top.
    Returns the right ink edge."""
    top = _ink(font, "H")[1]
    x -= _ink(font, text[:1])[0] if text else 0
    right = x
    for i, ch in enumerate(text):
        draw.text((x, cap_top - top), ch, font=font, fill=fill)
        if ch.strip():
            right = x + _ink(font, ch)[2]
        x += font.getlength(ch) + tracking
    return right


def _tracked_width(font, text, tracking) -> float:
    if not text:
        return 0
    adv = sum(font.getlength(c) for c in text[:-1]) + tracking * (len(text) - 1)
    return adv + _ink(font, text[-1])[2] - _ink(font, text[:1])[0]


# --------------------------------------------------------------------------
# photo treatment
# --------------------------------------------------------------------------

def cover_crop(img: Image.Image, size, focal_y: float) -> Image.Image:
    """Scale to fill `size`, cropping the overflow around a focal point."""
    tw, th = size
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = max(tw, int(round(sw * scale))), max(th, int(round(sh * scale)))
    img = img.resize((nw, nh), Image.LANCZOS)

    left = (nw - tw) // 2
    top = int(round((nh - th) * focal_y))
    top = max(0, min(nh - th, top))
    return img.crop((left, top, left + tw, top + th))


def _gradient_layer(size, colour, stops) -> Image.Image:
    """Full-width colour layer whose alpha follows `stops(y) -> 0..255`."""
    w, h = size
    a = Image.new("L", (1, h))
    a.putdata([max(0, min(255, int(stops(y)))) for y in range(h)])
    layer = Image.new("RGBA", (w, h), colour + (255,))
    layer.putalpha(a.resize((w, h)))
    return layer


def treat_photo(img: Image.Image, layout: dict, solid_from: int) -> Image.Image:
    size = tuple(layout["size"])
    base = cover_crop(img.convert("RGB"), size, brand.FOCAL_Y).convert("RGBA")

    # light shade across the top so the white logo holds on bright skies
    th, tmax = brand.TOP_SHADE_H, 255 * brand.TOP_SHADE
    base.alpha_composite(_gradient_layer(
        size, brand.BLACK, lambda y: tmax * (1 - y / th) ** 2 if y < th else 0))

    # photo fades into the deep green that carries the headline
    start = solid_from - brand.SCRIM_H

    def fade(y):
        if y <= start:
            return 0
        if y >= solid_from:
            return 255
        return 255 * ((y - start) / brand.SCRIM_H) ** 1.15

    base.alpha_composite(_gradient_layer(size, brand.DEEP, fade))
    return base


# --------------------------------------------------------------------------
# furniture
# --------------------------------------------------------------------------

def _down_icon(d: int, stroke: int) -> Image.Image:
    """White ring with a down arrow, drawn 4x and scaled for clean edges."""
    s = 4
    D, sw = d * s, stroke * s
    im = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    g.ellipse((sw // 2, sw // 2, D - sw // 2 - 1, D - sw // 2 - 1),
              outline=brand.WHITE, width=sw)
    cx = D / 2
    top, tip = D * 0.30, D * 0.68
    arm = D * 0.16
    g.line((cx, top, cx, tip), fill=brand.WHITE, width=sw)
    g.line((cx - arm, tip - arm, cx, tip), fill=brand.WHITE, width=sw, joint="curve")
    g.line((cx + arm, tip - arm, cx, tip), fill=brand.WHITE, width=sw, joint="curve")
    r = sw / 2
    for px, py in ((cx, top), (cx - arm, tip - arm), (cx + arm, tip - arm), (cx, tip)):
        g.ellipse((px - r, py - r, px + r, py + r), fill=brand.WHITE)
    return im.resize((d, d), Image.LANCZOS)


# --------------------------------------------------------------------------
# the card
# --------------------------------------------------------------------------

def render_card(photo, headline: str, variant: str = "facebook") -> Image.Image:
    """
    photo    : bytes, path, or PIL Image of the article's featured image
    headline : the article title (case is normalised to caps)
    variant  : "facebook" (1080x1380) or "story" (1080x1920)
    """
    if variant not in brand.LAYOUTS:
        raise ValueError(f"unknown variant {variant!r}")
    layout = brand.LAYOUTS[variant]

    if isinstance(photo, (bytes, bytearray)):
        photo = Image.open(io.BytesIO(photo))
    elif isinstance(photo, (str, Path)):
        photo = Image.open(photo)

    if layout.get("framed"):
        return _framed_story(photo, headline, layout)
    return _card(photo, headline, layout)


def _framed_story(photo, headline: str, layout: dict) -> Image.Image:
    """Story: the news card as a rounded panel over a blurred copy of the
    photo. Space under the panel is left for Instagram's link sticker."""
    w, h = layout["size"]
    panel = _card(photo, headline, brand.LAYOUTS[layout["panel"]])

    bg = cover_crop(photo.convert("RGB"), (w, h), 0.4)
    bg = bg.filter(ImageFilter.GaussianBlur(brand.STORY_BLUR))
    bg = Image.blend(Image.new("RGB", (w, h), brand.DEEP), bg, brand.STORY_BG_KEEP)

    pw = layout["panel_w"]
    ph = round(panel.height * pw / panel.width)
    px, py = (w - pw) // 2, layout["panel_y"]
    r = brand.STORY_RADIUS

    shadow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        (px, py + 20, px + pw, py + ph + 20), r, fill=160)
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    bg.paste(Image.new("RGB", (w, h), brand.BLACK), (0, 0), shadow)

    # draw the rounded mask 4x for smooth corners
    m = Image.new("L", (pw * 4, ph * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, pw * 4 - 1, ph * 4 - 1), r * 4, fill=255)
    bg.paste(panel.resize((pw, ph), Image.LANCZOS), (px, py),
             m.resize((pw, ph), Image.LANCZOS))
    return bg


def _card(photo, headline: str, layout: dict) -> Image.Image:
    w, h = layout["size"]

    # --- headline geometry first: the fade is placed relative to it --------
    text = clean_headline(headline)
    font, lines, pitch = fit_headline(text, layout)
    cap_h = _cap_h(font)
    cap_top = layout["headline_cap_bottom"] - ((len(lines) - 1) * pitch + cap_h)

    sub_font = _font(brand.SUB_SIZE, brand.UI_FONT)
    sub_cap_top = cap_top - brand.SUB_GAP - _cap_h(sub_font)
    band = layout.get("band")
    solid_from = cap_top + brand.SCRIM_BELOW_CAP
    if band:
        solid_from = min(band[0], solid_from)

    canvas = treat_photo(photo, layout, solid_from)
    draw = ImageDraw.Draw(canvas)
    # --- NEWS label -----------------------------------------------------------
    top_y = layout["top_y"]
    lf = _font(brand.LABEL_SIZE, brand.UI_FONT)
    lw = _tracked_width(lf, brand.LABEL_TEXT, brand.LABEL_TRACKING)
    box = (brand.MARGIN_X, top_y,
           brand.MARGIN_X + round(lw) + 2 * brand.LABEL_PAD_X - 1,
           top_y + brand.LABEL_BOX_H - 1)
    draw.rectangle(box, fill=brand.WHITE)
    _draw_tracked(draw, brand.MARGIN_X + brand.LABEL_PAD_X,
                  top_y + (brand.LABEL_BOX_H - _cap_h(lf)) / 2,
                  brand.LABEL_TEXT, lf, brand.INK, brand.LABEL_TRACKING)

    # --- logo -----------------------------------------------------------------
    logo = Image.open(brand.LOGO_IMG).convert("RGBA")
    lh = round(logo.height * brand.LOGO_W / logo.width)
    logo = logo.resize((brand.LOGO_W, lh), Image.LANCZOS)
    canvas.alpha_composite(logo, (brand.LOGO_RIGHT - brand.LOGO_W, top_y - 1))

    # --- subheading + headline -------------------------------------------------
    if brand.SUB_TEXT:
        _draw_tracked(draw, brand.MARGIN_X, sub_cap_top, brand.SUB_TEXT,
                      sub_font, brand.SUB_GREEN, brand.SUB_TRACKING)

    top = _ink(font, "H")[1]
    for i, line in enumerate(lines):
        x = brand.MARGIN_X - _ink(font, line)[0]
        draw.text((x, cap_top + i * pitch - top), line, font=font, fill=brand.WHITE)

    # --- CTA band (feed only) ------------------------------------------------------
    if not band:
        return canvas.convert("RGB")
    band_top, band_bot = band
    draw.rectangle((0, band_top, w, band_bot - 1), fill=brand.BAND)
    if not layout.get("cta"):
        return canvas.convert("RGB")
    mid = (band_top + band_bot) / 2
    icon = _down_icon(brand.ICON_D, brand.ICON_STROKE)
    canvas.alpha_composite(icon, (round(brand.ICON_CX - brand.ICON_D / 2),
                                  round(mid - brand.ICON_D / 2)))
    cf = _font(brand.CTA_SIZE, brand.UI_FONT)
    _draw_tracked(draw, brand.CTA_X, mid - _cap_h(cf) / 2, layout["cta"],
                  cf, brand.WHITE, brand.CTA_TRACKING)

    return canvas.convert("RGB")


def slugify(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:limit].strip("-") or "post"
