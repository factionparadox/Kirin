#!/usr/bin/env python3
"""Render the images Kirin puts into openKylin's graphical installer
(packaging/branding/installer/), sized to fit the space of the images they replace.

* background.jpg: the installer's full-screen background (3840x2160), Kirin's
  low-poly field without the logo, so the installer's panels sit on a quiet area.
* logo.png, logo@2x.png: replace the KYLIN logo on the language page (200x80 and
  400x159, white on transparent like the original).
Needs Pillow and the Inter font (fonts-inter).
    python3 scripts/dev/make-installer-branding.py
"""
import importlib.util
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / 'packaging/branding/installer'
FONT = '/usr/share/fonts/opentype/inter/Inter-SemiBold.otf'
# Space each image has in the installer (bytes), from scripts/build/qtres.py list.
LIMITS = {'background.jpg': 2291287, 'logo.png': 7334, 'logo@2x.png': 16767}


def wallpaper():
    spec = importlib.util.spec_from_file_location('wall', REPO / 'scripts/dev/make-wallpaper.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def small_png(img: Image.Image, limit: int) -> bytes:
    for colours in (256, 128, 64, 32):
        q = img.quantize(colors=colours, method=Image.Quantize.FASTOCTREE)
        buf = io.BytesIO(); q.save(buf, 'PNG', optimize=True)
        if buf.tell() <= limit:
            return buf.getvalue()
    raise SystemExit(f'cannot fit a {img.size} PNG into {limit} bytes')


def logo(w: int, h: int) -> Image.Image:
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    mark = Image.open(REPO / 'packaging/branding/kirin-logo.png').convert('RGBA')
    bbox = mark.getchannel('A').point(lambda v: 255 if v > 40 else 0).getbbox()
    mark = mark.crop(bbox)
    mh = int(h * 0.92)
    mark = mark.resize((round(mark.width * mh / mark.height), mh), Image.LANCZOS)
    # White, like the logo it replaces, which sits on a coloured page.
    white = Image.new('RGBA', mark.size, (255, 255, 255, 255))
    white.putalpha(mark.getchannel('A').filter(ImageFilter.MinFilter(3)))
    img.alpha_composite(white, (0, (h - mh) // 2))
    draw = ImageDraw.Draw(img)
    x = mark.width + int(h * 0.12)
    size = int(h * 0.5)
    while size > 6:
        font = ImageFont.truetype(FONT, size)
        l, t, r, b = draw.textbbox((0, 0), 'Kirin', font=font)
        sub = ImageFont.truetype(FONT, int(size * 0.42))
        sl, st, sr, sb = draw.textbbox((0, 0), 'LINUX', font=sub)
        if x + max(r - l, sr - sl) <= w and (b - t) + (sb - st) + h * 0.08 <= h * 0.9:
            break
        size -= 1
    top = (h - ((b - t) + (sb - st) + int(h * 0.08))) // 2
    draw.text((x - l, top - t), 'Kirin', font=font, fill='white')
    draw.text((x - sl + 2, top + (b - t) + int(h * 0.08) - st), 'LINUX', font=sub, fill=(255, 255, 255, 220))
    return img


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bg = wallpaper().render(3840, 2160, logo_mark=False, glow_at=(0.5, 0.55))
    for q in (92, 88, 84, 80):
        buf = io.BytesIO(); bg.save(buf, 'JPEG', quality=q, optimize=True)
        if buf.tell() <= LIMITS['background.jpg']:
            (OUT / 'background.jpg').write_bytes(buf.getvalue()); break
    else:
        raise SystemExit('background does not fit')
    (OUT / 'logo.png').write_bytes(small_png(logo(200, 80), LIMITS['logo.png']))
    (OUT / 'logo@2x.png').write_bytes(small_png(logo(400, 159), LIMITS['logo@2x.png']))
    for name, limit in LIMITS.items():
        print(f'{name}: {(OUT / name).stat().st_size} of {limit} bytes')


if __name__ == '__main__':
    main()
