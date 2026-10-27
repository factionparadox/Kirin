#!/usr/bin/env python3
"""Render Kirin's default wallpaper (packaging/branding/wallpaper/) from the logo.

A dark low-poly background in Kirin's terminal palette, echoing the logo's
faceted style, with a soft glow and the logo at the lower right. 3:2 like the
Framework 13 Pro's screen, large enough to downscale cleanly to any display.
    python3 scripts/dev/make-wallpaper.py
"""
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parents[2]
W, H = 3840, 2560
TOP, BOTTOM = (20, 27, 38), (9, 12, 19)          # #141b26 -> #090c13


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def main():
    rng = random.Random(1)                           # reproducible
    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)
    # Low-poly field: a jittered grid split into triangles, shaded around the vertical gradient.
    cols, rows = 16, 11
    pts = [[(x * W / cols + (rng.uniform(-0.35, 0.35) * W / cols if 0 < x < cols else 0),
             y * H / rows + (rng.uniform(-0.35, 0.35) * H / rows if 0 < y < rows else 0))
            for x in range(cols + 1)] for y in range(rows + 1)]
    for y in range(rows):
        for x in range(cols):
            a, b, c, d = pts[y][x], pts[y][x + 1], pts[y + 1][x], pts[y + 1][x + 1]
            for tri in ((a, b, c), (b, d, c)) if rng.random() < 0.5 else ((a, b, d), (a, d, c)):
                cy = sum(p[1] for p in tri) / 3 / H
                base = lerp(TOP, BOTTOM, cy)
                shade = rng.uniform(-4, 6)
                blue = rng.uniform(0, 5)
                draw.polygon(tri, fill=tuple(max(0, min(255, round(v + shade + (blue if i == 2 else 0))))
                                             for i, v in enumerate(base)))
    # Soft blue glow where the logo stands.
    glow = Image.new('L', (W, H), 0)
    gd = ImageDraw.Draw(glow)
    cx, cy, r = int(W * 0.73), int(H * 0.62), int(H * 0.42)
    gd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(r // 2))
    img = Image.composite(Image.new('RGB', (W, H), (29, 111, 184)), img, glow)
    # The logo, slightly translucent so it sits in the scene.
    logo = Image.open(REPO / 'packaging/branding/kirin-logo.png').convert('RGBA')
    size = int(H * 0.46)
    logo = logo.resize((size, size), Image.LANCZOS)
    # Trim the cut-out's light fringe: shrink the mask a little and soften its edge.
    alpha = logo.getchannel('A').filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(1.5))
    alpha = alpha.point(lambda v: int(v * 0.92))
    logo.putalpha(alpha)
    img.paste(logo, (cx - size // 2, cy - size // 2), logo)
    out = REPO / 'packaging/branding/wallpaper'
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / 'kirin.png', optimize=True)
    img.save(out / 'kirin.jpg', quality=92, optimize=True)
    img.resize((960, 640), Image.LANCZOS).save(out / 'kirin-preview.png')
    print('wrote', out)


if __name__ == '__main__':
    main()
