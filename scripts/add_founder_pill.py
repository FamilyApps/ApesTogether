"""
Composite the "Founding Trader" pill onto an existing app screenshot.

Replicates FoundingTraderPill (PortfolioDetailScreen.kt / PortfolioDetailView.swift)
pixel spec: gold #FFD700 at 15% fill + 40% 1dp border, fully-rounded corners,
10dp/6dp padding, 13dp medal icon, 4dp gap, "Founding Trader" 11sp semibold white.

Two modes (Pixel 8a screenshots are 1080x2400 @ 2.625 px/dp — the default
scale; iPhone @3x captures need --scale 3.0):

1. Plain overlay — draw the pill at a position that already has room:

    python scripts/add_founder_pill.py in.png out.png --y 690
    python scripts/add_founder_pill.py in.png out.png --x 42 --y 690

2. Insert mode — the hero card usually has NO free rows under the $ value, so
   stretch it: the scanline at --insert-y (a clean row inside the card, e.g.
   between the "Member for…" line and the value) is replicated into a band
   tall enough for the pill, and the same number of rows is deleted from
   uniform gaps further down (--trim y:count, repeatable) so the total height
   and any bottom bars stay put. Rows not covered by trims are cropped from
   the bottom.

    python scripts/add_founder_pill.py in.png out.png --insert-y 465 \
        --trim 1900:45 --trim 2130:45

The script prints the pill/band geometry so you can iterate on positions.
"""
import argparse
import math

from PIL import Image, ImageDraw, ImageFont

GOLD = (255, 215, 0)
TEXT_PRIMARY = (255, 255, 255)
LABEL = "Founding Trader"

# Windows font candidates closest to the app's semibold label, tried in order.
FONT_CANDIDATES = ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "segoeui.ttf", "arial.ttf")


def load_font(px: int) -> ImageFont.FreeTypeFont:
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def star_points(cx: float, cy: float, r: float) -> list:
    """5-point star (stand-in for the WorkspacePremium medal glyph)."""
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def pill_geometry(d: ImageDraw.ImageDraw, s: float):
    font = load_font(round(11 * s))
    bbox = d.textbbox((0, 0), LABEL, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    icon = round(13 * s)
    pad_h, pad_v, gap = round(10 * s), round(6 * s), round(4 * s)
    w = pad_h + icon + gap + text_w + pad_h
    h = pad_v + max(icon, text_h) + pad_v
    return font, bbox, text_h, icon, pad_h, gap, w, h


def draw_pill(d: ImageDraw.ImageDraw, x: int, y: int, s: float) -> tuple:
    font, bbox, text_h, icon, pad_h, gap, w, h = pill_geometry(d, s)
    # Pill: 20dp corner radius >= h/2, i.e. fully rounded ends.
    d.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=h / 2,
        fill=GOLD + (38,),        # 15% alpha
        outline=GOLD + (102,),    # 40% alpha
        width=max(1, round(s)),   # 1dp
    )
    # Medal icon (gold star), vertically centered.
    d.polygon(star_points(x + pad_h + icon / 2, y + h / 2, icon / 2), fill=GOLD + (255,))
    # Label, vertically centered (bbox top offset compensated).
    d.text((x + pad_h + icon + gap, y + (h - text_h) / 2 - bbox[1]), LABEL,
           font=font, fill=TEXT_PRIMARY + (255,))
    return w, h


def main() -> None:
    ap = argparse.ArgumentParser(description="Composite the Founding Trader pill onto a screenshot")
    ap.add_argument("input", help="source screenshot (PNG)")
    ap.add_argument("output", help="output path (PNG)")
    ap.add_argument("--y", type=int, default=None,
                    help="overlay mode: top edge of the pill, in pixels")
    ap.add_argument("--insert-y", type=int, default=None,
                    help="insert mode: replicate this scanline into a band holding the pill")
    ap.add_argument("--trim", action="append", default=[], metavar="Y:COUNT",
                    help="insert mode: delete COUNT rows starting at original row Y (repeatable)")
    ap.add_argument("--x", type=int, default=None,
                    help="left edge in pixels; omit to center horizontally (hero-card layout)")
    ap.add_argument("--margin", type=int, default=None,
                    help="insert mode: blank rows above/below the pill inside the band (default 8dp)")
    ap.add_argument("--scale", type=float, default=2.625,
                    help="pixels per dp (Pixel 8a = 2.625; iPhone @3x = 3.0)")
    args = ap.parse_args()

    if (args.y is None) == (args.insert_y is None):
        ap.error("pass exactly one of --y (overlay mode) or --insert-y (insert mode)")

    s = args.scale
    base = Image.open(args.input).convert("RGBA")
    W, H = base.size
    measurer = ImageDraw.Draw(base)
    *_, pill_w, pill_h = pill_geometry(measurer, s)

    if args.insert_y is not None:
        margin = args.margin if args.margin is not None else round(8 * s)
        band = pill_h + 2 * margin
        trims = []
        for t in args.trim:
            ty, _, count = t.partition(":")
            trims.append((int(ty), int(count)))
        trims.sort()
        if any(ty <= args.insert_y for ty, _ in trims):
            ap.error("--trim rows must lie below --insert-y")

        canvas = Image.new("RGBA", (W, H + band))
        canvas.paste(base.crop((0, 0, W, args.insert_y)), (0, 0))
        canvas.paste(base.crop((0, args.insert_y, W, args.insert_y + 1)).resize((W, band)),
                     (0, args.insert_y))
        cursor_src, cursor_dst = args.insert_y, args.insert_y + band
        for ty, count in trims:
            canvas.paste(base.crop((0, cursor_src, W, ty)), (0, cursor_dst))
            cursor_dst += ty - cursor_src
            cursor_src = ty + count
        canvas.paste(base.crop((0, cursor_src, W, H)), (0, cursor_dst))
        base = canvas.crop((0, 0, W, H))
        pill_y = args.insert_y + margin
        removed = sum(c for _, c in trims)
        note = f"band {band}px at y={args.insert_y}, trims reclaimed {removed}px, {band - removed}px cropped from bottom"
    else:
        pill_y = args.y
        note = "overlay mode"

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    x = args.x if args.x is not None else (W - pill_w) // 2
    draw_pill(d, x, pill_y, s)

    Image.alpha_composite(base, overlay).save(args.output)
    print(f"Pill {pill_w}x{pill_h}px at x={x}, y={pill_y} (scale {s}; {note}) -> {args.output}")


if __name__ == "__main__":
    main()
