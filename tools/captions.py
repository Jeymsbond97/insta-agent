"""Word-timed captions shared by the intro parts: key words larger, heavier and coloured, the rest smaller and white.

words: [{"w", "s", "e"}] with times on the caption clock; phrases: lists of word indexes shown together;
keys: {index: colour}; skip: indexes never shown (words already on screen elsewhere).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FONTS = Path(__file__).resolve().parent.parent / "brand/fonts"
TEAL, ORANGE, YELLOW = (0, 214, 170), (255, 138, 0), (255, 214, 0)
_cache = {}


def font(name, size):
    key = (name, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONTS / f"Inter-{name}.ttf"), size)
    return _cache[key]


def _ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def _out4(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 4


def draw(img, t, words, phrases, keys, base=1680, end_time=None, until=None):
    """until: optional {phrase_start_index: time} to end a phrase early."""
    idx = None
    for n, ph in enumerate(phrases):
        start = words[ph[0]]["s"]
        end = words[phrases[n + 1][0]]["s"] - 0.02 if n + 1 < len(phrases) else (end_time or 1e9)
        if until and ph[0] in until:
            end = until[ph[0]]
        if start - 0.06 <= t < end:
            idx = ph
            break
    if idx is None:
        return img
    d = ImageDraw.Draw(img)
    items = [(i, words[i]["w"].strip('".,?—'), i in keys) for i in idx]
    size = lambda key: 104 if key else 74
    space = 24
    total = sum(d.textlength(w, font=font("Black" if k else "ExtraBold", size(k))) for _, w, k in items) + space * (len(items) - 1)
    scale = min(1.0, 990 / total)
    slide = _out4((t - words[idx[0]]["s"] + 0.06) / 0.16)
    x = (W - total * scale) / 2 - 260 * (1 - slide)
    shadow = Image.new("L", (W, H), 0)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd, ld = ImageDraw.Draw(shadow), ImageDraw.Draw(layer)
    for i, text, key in items:
        f = font("Black" if key else "ExtraBold", int(size(key) * scale))
        p = _ease((t - words[i]["s"] + 0.06) / 0.1) * slide
        if p > 0:
            pop = 1 + 0.12 * (1 - _out4((t - words[i]["s"]) / 0.2)) if key else 1.0
            ff = font("Black", int(size(key) * scale * pop)) if pop > 1.01 else f
            col = keys.get(i, (255, 255, 255))
            sd.text((x, base + 6), text, font=ff, fill=int(220 * p), anchor="ls", stroke_width=10, stroke_fill=int(220 * p))
            ld.text((x, base), text, font=ff, fill=col + (int(255 * p),), anchor="ls", stroke_width=5,
                    stroke_fill=(8, 12, 18, int(235 * p)))
        x += d.textlength(text, font=f) + space * scale
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    out = Image.composite(Image.new("RGB", (W, H)), img, shadow.point(lambda v: int(v * 0.7)))
    out.paste(layer, (0, 0), layer)
    return out
