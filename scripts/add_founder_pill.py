"""
Composite the "Founding Trader" pill onto an existing app screenshot.

Replicates FoundingTraderPill (PortfolioDetailScreen.kt / PortfolioDetailView.swift)
pixel spec: gold #FFD700 at 15% fill + 40% 1dp border, fully-rounded corners,
10dp/6dp padding, 13dp medal icon, 4dp gap, "Founding Trader" 11sp semibold white.

Usage (Pixel 8a screenshots are 1080x2400 @ 2.625 px/dp — the default scale):

    pip install pillow
    python scripts/add_founder_pill.py in.png out.png --y 690
    python scripts/add_founder_pill.py in.png out.png --x 42 --y 690 --scale 2.625

Placement guide:
  - Public-view hero card: omit --x (pill centers horizontally, matching the
    hero layout); --y is the pill's TOP edge, ~4dp (~10px) below the big
    portfolio-value text.
  - Owner view badges row: pass --x 42 (16dp left padding) with --y on the
    badges row line, above the chart card.
The script prints the rendered pill size so you can iterate on position.
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Composite the Founding Trader pill onto a screenshot")
    ap.add_argument("input", help="source screenshot (PNG)")
    ap.add_argument("output", help="output path (PNG)")
    ap.add_argument("--y", type=int, required=True, help="top edge of the pill, in pixels")
    ap.add_argument("--x", type=int, default=None,
                    help="left edge in pixels; omit to center horizontally (hero-card layout)")
    ap.add_argument("--scale", type=float, default=2.625,
                    help="pixels per dp (Pixel 8a = 2.625; iPhone @3x = 3.0)")
    args = ap.parse_args()

    s = args.scale
    base = Image.open(args.input).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    font = load_font(round(11 * s))
    bbox = d.textbbox((0, 0), LABEL, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    icon = round(13 * s)
    pad_h, pad_v, gap = round(10 * s), round(6 * s), round(4 * s)
    w = pad_h + icon + gap + text_w + pad_h
    h = pad_v + max(icon, text_h) + pad_v

    x = args.x if args.x is not None else (base.width - w) // 2
    y = args.y

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
    tx = x + pad_h + icon + gap
    ty = y + (h - text_h) / 2 - bbox[1]
    d.text((tx, ty), LABEL, font=font, fill=TEXT_PRIMARY + (255,))

    Image.alpha_composite(base, overlay).save(args.output)
    print(f"Pill rendered at x={x}, y={y}, size {w}x{h}px (scale {s}) -> {args.output}")


if __name__ == "__main__":
    main()
