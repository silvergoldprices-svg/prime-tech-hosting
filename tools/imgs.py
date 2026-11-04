#!/usr/bin/env python3
"""Placeholder JPG generator for the Arabic site.

Every placeholder is a 1200x675 JPG with the topic written on it and the exact file name at the bottom.
To use your own picture: save it as JPG, rename it to that file name, put it in images-ar/<article>/ (overwrite), run build.py.

CLI (for NEW articles written in content-ar/articles/*.md):
    python3 tools/imgs.py new <slug> "<article title>" [count]
creates images-ar/<slug>/<slug>-01.jpg ... and prints the Markdown lines to paste between your paragraphs.
Existing files are never overwritten.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parent.parent
FONT_BOLD = ROOT / "assets-ar" / "fonts" / "DejaVuSans-Bold.ttf"   # bundled (has all Arabic presentation forms)
FONT_MED = ROOT / "assets-ar" / "fonts" / "DejaVuSans.ttf"
W, H = 1200, 675
NAVY, TEAL = (11, 37, 69), (19, 168, 158)
_reshaper = arabic_reshaper.ArabicReshaper()


def _font(path, size):
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.BASIC)   # we shape Arabic ourselves (reshaper + bidi), same result on every OS


def _shape(s):
    return get_display(_reshaper.reshape(s))


def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(_shape(t), font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_placeholder(path, title, filename, kicker="نبض الاستضافة", note="صورة مؤقتة: استبدلها بصورتك"):
    path = Path(path)
    if path.exists():
        return False                      # never overwrite a real picture
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (W, H), NAVY)
    px = img.load()
    for y in range(H):                    # vertical gradient navy -> teal
        t = y / (H - 1)
        row = tuple(int(NAVY[i] + (TEAL[i] - NAVY[i]) * t * 0.85) for i in range(3))
        for x in range(W):
            px[x, y] = row
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((24, 24, W - 24, H - 24), radius=28, outline=(255, 255, 255), width=3)
    f_k, f_t, f_n = (_font(FONT_MED, 34), _font(FONT_BOLD, 62),
                     _font(FONT_MED, 30))
    f_f = _font(FONT_BOLD, 34)
    # kicker (top right, RTL)
    ks = _shape(kicker)
    d.text((W - 70 - d.textlength(ks, font=f_k), 62), ks, font=f_k, fill=(190, 240, 236))
    # title, centred, shrink until it fits in 5 lines
    size, lines = 56, []
    while size >= 36:
        f_t = _font(FONT_BOLD, size)
        lines = _wrap(d, title, f_t, W - 200)
        if len(lines) <= 4:
            break
        size -= 3
    lh = int(size * 1.45)
    y = (H - lh * len(lines)) // 2 - 10
    for ln in lines:
        s = _shape(ln)
        d.text(((W - d.textlength(s, font=f_t)) / 2, y), s, font=f_t, fill=(255, 255, 255))
        y += lh
    # bottom: file name (latin, big, easy to copy) + note
    fn_w = d.textlength(filename, font=f_f)
    d.rounded_rectangle(((W - fn_w) / 2 - 26, H - 150, (W + fn_w) / 2 + 26, H - 92), radius=16, fill=(255, 255, 255))
    d.text(((W - fn_w) / 2, H - 146), filename, font=f_f, fill=NAVY)
    ns = _shape(note)
    d.text(((W - d.textlength(ns, font=f_n)) / 2, H - 80), ns, font=f_n, fill=(220, 245, 242))
    img.save(path, "JPEG", quality=80, optimize=True, progressive=True)
    return True


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "new":
        slug, title = sys.argv[2], sys.argv[3]
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        for i in range(1, n + 1):
            fn = f"{slug}-{i:02d}.jpg"
            made = make_placeholder(ROOT / "images-ar" / slug / fn, title if i == 1 else f"{title} ({i})", fn)
            print(("created " if made else "exists  ") + f"images-ar/{slug}/{fn}")
            print(f"![وصف الصورة](/images/ar/{slug}/{fn})")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
