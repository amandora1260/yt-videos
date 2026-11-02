"""オリジナルキャラクター（とうもろこし／焼きもろこし）を描き、話している方の口を動かす"""
import math, numpy as np
from PIL import Image, ImageDraw

def _cob(d, cx, cy, w, h, base, kernel, line):
    # 実（だ円）と粒
    d.ellipse([cx-w/2, cy-h/2, cx+w/2, cy+h/2], fill=base, outline=line, width=5)
    rows, cols = 9, 5
    for r in range(rows):
        y = cy - h/2 + h*(r+0.7)/(rows+0.4)
        half = (w/2) * math.sqrt(max(0.0, 1 - ((y-cy)/(h/2))**2)) - 12
        for c in range(cols):
            x = cx - half + (2*half)*(c+0.5)/cols
            d.ellipse([x-11, y-9, x+11, y+9], fill=kernel)

def draw(kind, mouth=0.0, blink=False, bounce=0.0, size=300):
    S = 2  # 2倍で描いて縮小（なめらかに）
    W, H = size*S, int(size*1.15)*S
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    cx, cy = W/2, H*0.47 - bounce*S
    w, h = W*0.52, H*0.72
    if kind == "とうもろこし":
        base, kernel, line = (250, 204, 21), (253, 224, 71), (161, 98, 7)
    else:  # 焼きもろこし：こんがり色＋焼き目
        base, kernel, line = (217, 140, 40), (234, 170, 70), (120, 60, 10)
    # 皮（葉）
    leaf = (34, 160, 70)
    d.polygon([(cx-w*0.55, cy+h*0.05), (cx-w*0.15, cy+h*0.52), (cx-w*0.62, cy+h*0.58)], fill=leaf)
    d.polygon([(cx+w*0.55, cy+h*0.05), (cx+w*0.15, cy+h*0.52), (cx+w*0.62, cy+h*0.58)], fill=leaf)
    _cob(d, cx, cy, w, h, base, kernel, line)
    if kind == "焼きもろこし":
        for k in range(4):   # 焼き目
            y = cy - h*0.30 + k*h*0.18
            d.line([(cx-w*0.38, y), (cx+w*0.38, y+12)], fill=(90, 45, 10), width=10)
        d.polygon([(cx-30, cy-h/2+8), (cx-70, cy-h/2-30), (cx-70, cy-h/2+40)], fill=(225, 29, 72))   # リボン
        d.polygon([(cx+30, cy-h/2+8), (cx+70, cy-h/2-30), (cx+70, cy-h/2+40)], fill=(225, 29, 72))
        d.ellipse([cx-22, cy-h/2-10, cx+22, cy-h/2+30], fill=(190, 18, 60))
    else:
        d.chord([cx-w*0.42, cy-h/2-40, cx+w*0.42, cy-h/2+70], 180, 360, fill=(37, 99, 235))   # 帽子
        d.rectangle([cx-w*0.05, cy-h/2+12, cx+w*0.5, cy-h/2+30], fill=(30, 64, 175))
    # 顔の白いところ
    fy = cy - h*0.02
    d.ellipse([cx-w*0.40, fy-h*0.20, cx+w*0.40, fy+h*0.24], fill=(255, 247, 225))
    ex = w*0.17; ey = fy - h*0.06
    for sx in (-1, 1):
        x = cx + sx*ex
        if blink:
            d.line([(x-18, ey), (x+18, ey)], fill=(30, 30, 30), width=7)
        else:
            d.ellipse([x-17, ey-24, x+17, ey+24], fill=(30, 30, 30))
            d.ellipse([x-8, ey-16, x+3, ey-5], fill=(255, 255, 255))
        if kind == "焼きもろこし":   # まつげ・ほっぺ
            d.line([(x+sx*14, ey-22), (x+sx*30, ey-36)], fill=(30, 30, 30), width=5)
            d.ellipse([x+sx*10-22, ey+30, x+sx*10+22, ey+48], fill=(251, 113, 133))
    # 口（mouth=0〜1で開く）
    my = fy + h*0.12; mw = 34
    if mouth < 0.15:
        d.arc([cx-mw, my-22, cx+mw, my+14], 20, 160, fill=(80, 30, 20), width=7)
    else:
        mh = 10 + 36*mouth
        d.ellipse([cx-mw*0.9, my-mh/2, cx+mw*0.9, my+mh/2], fill=(110, 20, 30))
        d.ellipse([cx-mw*0.5, my, cx+mw*0.5, my+mh/2], fill=(244, 114, 182))
    return im.resize((size, int(size*1.15)), Image.LANCZOS)

def envelope(pcm, rate, fps):
    hop = rate // fps
    n = len(pcm) // hop
    a = np.abs(pcm[:n*hop].astype(np.float32)).reshape(n, hop).mean(axis=1)
    ref = np.percentile(a[a > 0], 90) if (a > 0).any() else 1
    return np.clip(a / ref, 0, 1)
