#!/usr/bin/env python3
"""
dotify.py - turn a photo into dot-matrix / binary-grid art as an SVG.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
except ImportError:
    sys.exit("Pillow is required:  python -m pip install Pillow")

THEMES = {
    "dark": ("#39d353", "#0e4429", None),
    "light": ("#216e39", "#aceebb", None),
}

ASCII_RAMP = "@%#*+=-:. "
BRAILLE_BASE = 0x2800
BRAILLE_BITS = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]


def square_crop(img, fx, fy):
    w, h = img.size
    side = min(w, h)
    left = min(max(fx * w - side / 2, 0), w - side)
    top = min(max(fy * h - side / 2, 0), h - side)
    return img.crop((round(left), round(top), round(left) + side, round(top) + side))


def load_grid(path, cols, contrast, brightness, gamma, cell_aspect, square=False,
              focus=(0.5, 0.5), equalize=False, detail=0.0):
    img = ImageOps.exif_transpose(Image.open(path))
    mask = None
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        if img.split()[3].getextrema()[0] < 250:
            mask = img.split()[3]
        flat = Image.new("RGBA", img.size, (0, 0, 0, 255))
        flat.alpha_composite(img)
        img = flat
    img = img.convert("RGB")
    if square:
        img = square_crop(img, *focus)
        if mask is not None:
            mask = square_crop(mask, *focus)
    gray = img.convert("L")
    if equalize:
        binmask = mask.point(lambda v: 255 if v > 127 else 0) if mask else None
        gray = ImageOps.equalize(gray, mask=binmask)
    if detail > 0:
        radius = max(2, round(min(img.size) / 52))
        gray = gray.filter(ImageFilter.UnsharpMask(radius=radius, percent=round(detail * 100), threshold=0))
    if contrast != 1.0:
        gray = ImageEnhance.Contrast(gray).enhance(contrast)
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if brightness != 1.0:
        gray = ImageEnhance.Brightness(gray).enhance(brightness)
        img = ImageEnhance.Brightness(img).enhance(brightness)
    w, h = img.size
    rows = max(1, round(cols * (h / w) * cell_aspect))
    small_g = gray.resize((cols, rows), Image.Resampling.LANCZOS)
    if mask is not None:
        small_m = mask.resize((cols, rows), Image.Resampling.LANCZOS)
        small_g = ImageChops.multiply(small_g, small_m)
    small_c = img.resize((cols, rows), Image.Resampling.LANCZOS)
    gp, cp = small_g.load(), small_c.load()
    rgb, lum = [], []
    for y in range(rows):
        rgb_row, lum_row = [], []
        for x in range(cols):
            rgb_row.append(cp[x, y])
            v = gp[x, y] / 255.0
            lum_row.append(min(1.0, max(0.0, v ** gamma)))
        rgb.append(rgb_row)
        lum.append(lum_row)
    return cols, rows, lum, rgb


def circle_falloff(x, y, cols, rows, feather=0.06):
    nx = (x + 0.5) / cols * 2 - 1
    ny = (y + 0.5) / rows * 2 - 1
    d = math.hypot(nx, ny)
    if d <= 1 - feather:
        return 1.0
    if d >= 1 + feather:
        return 0.0
    return (1 + feather - d) / (2 * feather)


def svg_header(w, h, rows, opts):
    css = []
    if opts.animate:
        css.append("@keyframes dp{0%,100%{opacity:.6}50%{opacity:1}}")
        css.append(f".d{{animation:dp {opts.duration}s ease-in-out infinite}}")
        css += [f".l{i}{{animation-delay:{i / opts.lanes * opts.duration:.2f}s}}" for i in range(opts.lanes)]
    if opts.reveal:
        step = opts.reveal_time / max(rows - 1, 1)
        css.append("@keyframes rv{from{opacity:0}to{opacity:1}}")
        css.append(f".rw{{animation:rv {opts.reveal_fade}s ease-out both}}")
        css += [f".r{y}{{animation-delay:{(rows-1-y if opts.reveal_dir=='up' else y)*step:.3f}s}}" for y in range(rows)]
    style = f"<style>{''.join(css)}</style>" if css else ""
    bgrect = f'<rect width="100%" height="100%" fill="{opts.bg}"/>' if opts.bg else ""
    pad = opts.pad
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w+2*pad} {h+2*pad}" '
            f'width="{w+2*pad}" height="{h+2*pad}" role="img" aria-label="dot-matrix portrait">'
            f'{style}{bgrect}<g transform="translate({pad},{pad})">')


def build_dots(cols, rows, lum, rgb, theme, opts):
    fg, dim, _ = THEMES[theme]
    cell = opts.cell
    max_r = cell * 0.5 * opts.dot_scale
    lanes = opts.lanes
    out = []
    for y in range(rows):
        row = []
        for x in range(cols):
            v = lum[y][x]
            if opts.invert: v = 1 - v
            if opts.circle: v *= circle_falloff(x, y, cols, rows)
            if v < opts.floor: continue
            r = max_r * (v ** 0.75)
            if r < 0.18: continue
            cx = x * cell + cell / 2
            cy = y * cell + cell / 2
            if opts.color:
                cr, cg, cb = rgb[y][x]
                fill = f"#{cr:02x}{cg:02x}{cb:02x}"
            else:
                fill = fg if v > 0.42 else dim
            cls = f' class="d l{x % lanes}"' if opts.animate else ""
            row.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.2f}" fill="{fill}"{cls}/>')
        if not row: continue
        if opts.reveal:
            out.append(f'<g class="rw r{y}">{""  .join(row)}</g>')
        else:
            out += row
    return "".join(out), cols * cell, rows * cell


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("image", type=Path)
    p.add_argument("-o", "--out", type=Path, default=Path("assets/portrait"))
    p.add_argument("--mode", choices=("dots", "binary", "ascii", "braille"), default="dots")
    p.add_argument("--cols", type=int, default=88)
    p.add_argument("--cell", type=float, default=10.0)
    p.add_argument("--dot-scale", type=float, default=0.92)
    p.add_argument("--gamma", type=float, default=0.65)
    p.add_argument("--brightness", type=float, default=1.35)
    p.add_argument("--contrast", type=float, default=1.25)
    p.add_argument("--equalize", action="store_true")
    p.add_argument("--detail", type=float, default=0.0)
    p.add_argument("--floor", type=float, default=0.06)
    p.add_argument("--threshold", type=float, default=0.45)
    p.add_argument("--cell-aspect", type=float, default=1.0)
    p.add_argument("--square", action="store_true")
    p.add_argument("--focus", default="0.5,0.5")
    p.add_argument("--invert", action="store_true")
    p.add_argument("--circle", action="store_true")
    p.add_argument("--color", action="store_true")
    p.add_argument("--animate", action="store_true")
    p.add_argument("--lanes", type=int, default=14)
    p.add_argument("--duration", type=float, default=4.0)
    p.add_argument("--reveal", action="store_true")
    p.add_argument("--reveal-time", type=float, default=2.5)
    p.add_argument("--reveal-fade", type=float, default=0.45)
    p.add_argument("--reveal-dir", choices=("down", "up"), default="down")
    p.add_argument("--pad", type=float, default=8.0)
    p.add_argument("--bg", default="")
    args = p.parse_args(argv)
    if not args.image.exists():
        sys.exit(f"no such image: {args.image}")
    try:
        fx, fy = (float(v) for v in args.focus.split(","))
    except ValueError:
        sys.exit(f"bad --focus: {args.focus}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cols, rows, lum, rgb = load_grid(args.image, args.cols, args.contrast, args.brightness, args.gamma,
                                     args.cell_aspect, args.square, (fx, fy), args.equalize, args.detail)
    builder = build_dots
    themes = ("dark",) if args.color else ("dark", "light")
    for theme in themes:
        body, w, h = builder(cols, rows, lum, rgb, theme, args)
        svg = svg_header(w, h, rows, args) + body + "</g></svg>"
        stem = args.out.name if args.color else f"{args.out.name}-{theme}"
        dest = args.out.with_name(f"{stem}.svg")
        dest.write_text(svg, encoding="utf-8")
        print(f"wrote {dest}  ({len(svg)//1024}KB, {cols}x{rows} cells)")

if __name__ == "__main__":
    main()