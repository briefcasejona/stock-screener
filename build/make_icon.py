"""Draw the program's icon (app/icons/icon.png, .ico for Windows, .icns for the Mac). Run once; needs Pillow."""
import os

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'icons')
S = 1024


def draw():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    bg = Image.new('RGBA', (S, S))
    top, bottom = (24, 119, 220), (8, 74, 160)  # the program's blue, a little lighter at the top
    px = bg.load()
    for y in range(S):
        t = y / (S - 1)
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,)
        for x in range(S):
            px[x, y] = c
    mask = Image.new('L', (S, S), 0)
    m = 100  # the Mac's icon grid leaves a margin around the rounded square
    ImageDraw.Draw(mask).rounded_rectangle((m, m, S - m, S - m), radius=190, fill=255)
    img.paste(bg, (0, 0), mask)
    bars = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    b = ImageDraw.Draw(bars)
    base = 770
    for x0, h in ((245, 140), (405, 240), (565, 190)):
        b.rounded_rectangle((x0, base - h, x0 + 100, base), radius=16, fill=(255, 255, 255, 95))
    img = Image.alpha_composite(img, bars)
    d = ImageDraw.Draw(img)
    # a rising line over the bars, ending in a dot: "find what's growing"
    pts = [(255, 545), (455, 415), (615, 470), (775, 290)]
    d.line(pts, fill='white', width=44, joint='curve')
    for x, y in pts[:-1]:
        d.ellipse((x - 22, y - 22, x + 22, y + 22), fill='white')
    x, y = pts[-1]
    d.ellipse((x - 54, y - 54, x + 54, y + 54), fill='white')
    d.ellipse((x - 25, y - 25, x + 25, y + 25), fill=(24, 119, 220, 255))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    img = draw()
    img.save(os.path.join(OUT, 'icon.png'))
    img.save(os.path.join(OUT, 'icon.ico'), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(os.path.join(OUT, 'icon.icns'))
    print(os.listdir(OUT))


if __name__ == '__main__':
    main()
