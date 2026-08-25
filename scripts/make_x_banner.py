"""
Compose the @BobFordTrades X profile banner (1500x500) from a leaderboard
screenshot.

X banner constraints designed for (verified 8/24/26):
  - Canvas 1500x500 (3:1), PNG, <5MB.
  - Circular avatar overlaps the bottom-left ~260px square -> keep it empty.
  - ~60px may be trimmed off top/bottom on some devices -> nothing critical
    in the outer 60px bands.
  - Only the central ~1200x400 box is reliably visible on all devices.

Layout:
  [empty dark bg 0-290 (avatar zone)] [leaderboard crop panel] [wordmark
  + tagline + URL, ending <= x1350]

Usage (defaults produce the launch banner):
  python scripts/make_x_banner.py
  python scripts/make_x_banner.py --tagline "Launch week." --out banner_v2.png
"""
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Crop fractions measured on the iOS 01_leaderboard.PNG (1206x2622):
# S&P-500 strip through the #3 (bronze) row.
CROP = dict(x0=0.0213, x1=0.9787, y0=0.1816, y1=0.4512)

W, H = 1500, 500
PANEL_H = 380                # fits inside the 60px top/bottom trim bands
PANEL_X, PANEL_Y = 290, (H - PANEL_H) // 2
TEXT_CENTER_X = 1155         # text block ends <= x1350 (safe-zone edge)
GREEN = (69, 230, 160)
GRAY = (156, 163, 175)
WHITE = (245, 247, 246)
BORDER = (42, 58, 53)


def load_font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(rf"C:\Windows\Fonts\{name}", size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=r"C:\Users\catal\Downloads\raw_screenshots\01_leaderboard.PNG")
    ap.add_argument("--out", default=r"C:\Users\catal\Downloads\x_banner_bobfordtrades.png")
    ap.add_argument("--tagline", default="Every trade timestamped.")
    ap.add_argument("--url", default="apestogether.ai")
    args = ap.parse_args()

    src = Image.open(args.src).convert("RGB")
    sw, sh = src.size

    # Background color sampled from the screenshot's own card margin.
    bg = src.getpixel((int(sw * 0.01), int(sh * 0.47)))
    banner = Image.new("RGB", (W, H), bg)

    # Leaderboard crop -> panel with rounded corners + subtle border.
    box = (int(sw * CROP["x0"]), int(sh * CROP["y0"]),
           int(sw * CROP["x1"]), int(sh * CROP["y1"]))
    crop = src.crop(box)
    panel_w = round(PANEL_H * crop.width / crop.height)
    panel = crop.resize((panel_w, PANEL_H), Image.LANCZOS)

    radius = 24
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, panel.width - 1, panel.height - 1], radius=radius, fill=255)
    banner.paste(panel, (PANEL_X, PANEL_Y), mask)
    ImageDraw.Draw(banner).rounded_rectangle(
        [PANEL_X, PANEL_Y, PANEL_X + panel.width - 1, PANEL_Y + PANEL_H - 1],
        radius=radius, outline=BORDER, width=2)

    # Text block (all inside the x<=1350 / y 60-440 safe zone).
    draw = ImageDraw.Draw(banner)
    f_name = load_font(["segoeuib.ttf", "arialbd.ttf"], 58)
    f_tag = load_font(["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"], 31)
    f_url = load_font(["segoeui.ttf", "arial.ttf"], 26)

    lines = [
        ("ApesTogether", f_name, WHITE, 175),
        (args.tagline, f_tag, GREEN, 262),
        (args.url, f_url, GRAY, 318),
    ]
    for text, font, color, y in lines:
        tw = draw.textlength(text, font=font)
        draw.text((TEXT_CENTER_X - tw / 2, y), text, font=font, fill=color)

    banner.save(args.out, "PNG")
    print(f"saved {args.out}  size={banner.size}  "
          f"panel_right_edge=x{PANEL_X + panel.width}")


if __name__ == "__main__":
    main()
