#!/usr/bin/env python3
"""Draws the package's icon (matterfall.ico): a cyan matter cube on dark blue. Our own drawing:
no art from the game ships with the port (the launcher shows the player's own game icon).

Usage: python make_icon.py <out.ico>
"""
import sys

from PIL import Image, ImageDraw


def draw(size):
    scale = 4  # drawn larger, then reduced: smooth edges
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    r = s // 6
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=r, fill=(10, 13, 22, 255))
    # An isometric cube: top, left and right faces.
    cx, cy, a = s / 2, s / 2, s * 0.30
    top = [(cx, cy - a), (cx + a * 0.87, cy - a / 2), (cx, cy), (cx - a * 0.87, cy - a / 2)]
    left = [(cx - a * 0.87, cy - a / 2), (cx, cy), (cx, cy + a), (cx - a * 0.87, cy + a / 2)]
    right = [(cx + a * 0.87, cy - a / 2), (cx, cy), (cx, cy + a), (cx + a * 0.87, cy + a / 2)]
    d.polygon(top, fill=(122, 230, 255, 255))
    d.polygon(left, fill=(54, 214, 255, 255))
    d.polygon(right, fill=(24, 120, 170, 255))
    d.line([(s * 0.18, s * 0.86), (s * 0.82, s * 0.86)], fill=(255, 63, 164, 255), width=max(1, s // 28))
    return image.resize((size, size), Image.LANCZOS)


def main():
    out = sys.argv[1]
    big = draw(256)
    big.save(out, sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Icon written: {out}")


if __name__ == "__main__":
    main()
