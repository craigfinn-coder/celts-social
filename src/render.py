"""
Renders a CeltsAreHere social card from a photo + headline.

    from render import render_card
    img = render_card(photo_bytes, "CELTIC STAR SET FOR EXIT", variant="facebook")
    img.save("card.jpg", quality=92)
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import brand


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(brand.HEADLINE_FONT), size)


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
    Pick the largest size at which the wrapped headline still sits inside the
    band between the kicker and the footer. Returns (font, lines, pitch).
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
            cap_h = _ink(font, "H")[3] - _ink(font, "H")[1]
            block_h = (len(lines) - 1) * pitch + cap_h
            if bottom - block_h >= top_limit:
                return font, lines, pitch
        size -= 3

    # Floor reached: use the smallest size and let it wrap as far as it must.
    font = _font(brand.MIN_HEADLINE_SIZE)
    lines = _wrap(font, text, max_w) or [text]
    return font, lines, round(brand.MIN_HEADLINE_SIZE * brand.LINE_PITCH_RATIO)


def _draw_tracked(draw, xy, text, font, fill, tracking: float):
    """Draw `text` with per-character tracking, x is the left ink edge."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += _width(font, ch) + tracking


def _tracked_width(font, text, tracking):
    return sum(_width(font, c) for c in text) + tracking * (len(text) - 1)


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


def _vignette(size, strength: float) -> Image.Image:
    """Soft edge darkening as an L-mode multiply mask."""
    w, h = size
    small = (64, int(64 * h / w))
    mask = Image.new("L", small, 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((-small[0] * 0.30, -small[1] * 0.22,
               small[0] * 1.30, small[1] * 1.22), fill=255)
    mask = mask.resize(size, Image.BICUBIC)
    floor = int(255 * (1 - strength))
    return mask.point(lambda v: floor + (v * (255 - floor)) // 255)


def _scrim(size, start_y: int, end_y: int) -> Image.Image:
    """Black gradient from transparent at start_y to solid at end_y."""
    w, h = size
    a = Image.new("L", (1, h), 0)
    px = a.load()
    span = max(1, end_y - start_y)
    for y in range(h):
        if y <= start_y:
            v = 0
        elif y >= end_y:
            v = 255
        else:
            t = (y - start_y) / span
            v = int(255 * (t ** 1.7))
        px[0, y] = v
    a = a.resize((w, h))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    layer.putalpha(a)
    return layer


def treat_photo(img: Image.Image, layout: dict) -> Image.Image:
    size = tuple(layout["size"])
    base = cover_crop(img.convert("RGB"), size, brand.FOCAL_Y)

    if brand.PHOTO_DARKEN < 1:
        base = Image.blend(Image.new("RGB", size, brand.BLACK),
                           base, brand.PHOTO_DARKEN)

    base = Image.composite(base, Image.new("RGB", size, brand.BLACK),
                           _vignette(size, brand.VIGNETTE_STRENGTH))

    base = base.convert("RGBA")
    base.alpha_composite(_scrim(size, *layout["scrim"]))
    return base


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
    w, h = layout["size"]

    if isinstance(photo, (bytes, bytearray)):
        photo = Image.open(io.BytesIO(photo))
    elif isinstance(photo, (str, Path)):
        photo = Image.open(photo)

    canvas = treat_photo(photo, layout)
    draw = ImageDraw.Draw(canvas)

    # --- green corner flag -------------------------------------------------
    tag = Image.open(brand.TAG_IMG).convert("RGBA")
    canvas.alpha_composite(tag, tuple(layout["tag_xy"]))

    # --- LATEST kicker -----------------------------------------------------
    ksize = 1
    while True:
        kf = _font(ksize + 1)
        b = _ink(kf, "H")
        if b[3] - b[1] > brand.KICKER_CAP_H:
            break
        ksize += 1
    kf = _font(ksize)
    natural = sum(_width(kf, c) for c in brand.KICKER_TEXT)
    tracking = (brand.KICKER_WIDTH - natural) / max(1, len(brand.KICKER_TEXT) - 1)
    kw = _tracked_width(kf, brand.KICKER_TEXT, tracking)
    # --- headline ----------------------------------------------------------
    text = clean_headline(headline)
    font, lines, pitch = fit_headline(text, layout)
    cap_h = _ink(font, "H")[3] - _ink(font, "H")[1]
    block_h = (len(lines) - 1) * pitch + cap_h
    cap_top = layout["headline_cap_bottom"] - block_h

    # kicker rides just above the headline block, so short headlines
    # do not leave a hole where the reference had a third line
    kb = _ink(kf, brand.KICKER_TEXT)
    kicker_cap_top = cap_top - brand.KICKER_GAP - brand.KICKER_CAP_H
    _draw_tracked(draw,
                  ((w - kw) / 2, kicker_cap_top - kb[1]),
                  brand.KICKER_TEXT, kf, brand.GREEN, tracking)

    for i, line in enumerate(lines):
        b = _ink(font, line)
        x = (w - (b[2] - b[0])) / 2 - b[0]
        y = cap_top + i * pitch - b[1]
        draw.text((x, y), line, font=font, fill=brand.WHITE)

    # --- footer logo -------------------------------------------------------
    footer = Image.open(brand.FOOTER_IMG).convert("RGBA")
    canvas.alpha_composite(footer, tuple(layout["footer_xy"]))

    return canvas.convert("RGB")


def slugify(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:limit].strip("-") or "post"
