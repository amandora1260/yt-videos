"""本編のサムネイル（1280x720）を作る。型は STYLE で選ぶ（A〜D）。
原稿JSONに "thumb": {"big": "ダウ+3%", "line": "原油は-8%急落", "tag": "速報"} を書けば文言を上書きできる。
書いていなければ yt_title と表のスライドから自動で作る。"""
import math, os, re
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1280, 720
FD = "/usr/share/fonts/opentype/noto/"
def F(w, s): return ImageFont.truetype(FD + f"NotoSansCJK-{w}.ttc", s, index=0)
_A = os.path.join(os.path.dirname(__file__), "..", "assets")
STYLE = os.environ.get("THUMB_STYLE", "D")              # 毎日使う型（D：チャート背景型）
UP = (34, 197, 94); DN = (239, 68, 68); NEU = (250, 204, 21)
YEL = (255, 222, 0); BLK = (10, 10, 14); WHT = (255, 255, 255)

PCT = re.compile(r"(約)?([+\-−]?\d+(?:\.\d+)?)(%|％)")
DOWN_W = ("急落", "暴落", "下落", "安", "続落", "反落", "下げ", "急減")
ALIAS = {"SOX": ["半導体"], "WTI原油": ["原油"], "米10年債利回り": ["金利"]}
UP_W = ("急騰", "上昇", "反発", "高", "続伸", "上げ", "最高値", "急伸")

def _sign_from_words(s):
    for w in DOWN_W:
        if w in s: return -1
    for w in UP_W:
        if w in s: return 1
    return 0

def facts(b):
    """サムネに載せる要素：big（主役の数字）、line（2行目）、tag（帯の文字）、dir（+1/-1/0）、chips（指数）"""
    t = b.get("thumb") or {}
    core = b["yt_title"]
    core = re.sub(r"^【[^】]*】", "", core).split("｜")[0].strip()
    parts = [p for p in re.split(r"[、，,]", core) if p]
    chips = []
    for s in b.get("slides", []):
        if s.get("type") == "table" and "指数" in s.get("title", ""):
            for r in s["rows"][:3]:
                if len(r) > 2 and re.match(r"^[+\-]", r[2]): chips.append((r[0].replace("NY", "").replace("総合", ""), r[2]))
            break
    big, line, d = None, None, 0
    for i, p in enumerate(parts):
        m = PCT.search(p)
        if m:
            label = re.split(r"[でがはのをに]", re.sub(r"[でがはのをに]$", "", p[:m.start()]))[-1]
            num = m.group(2).replace("−", "-")
            sg = -1 if num.startswith("-") else 1 if num.startswith("+") else 0 if m.group(1) else _sign_from_words(p[m.end():])
            if sg and not num[0] in "+-": num = ("+" if sg > 0 else "-") + num
            big = f"{label}{num}%"
            d = sg
            others = [x for j, x in enumerate(parts) if j != i]
            line = others[0] if others else (p[m.end():] or "")
            break
    if big is None:                                     # 題名に%がない日は、題名の主語に合う表の数字を使う
        for s in b.get("slides", []):
            if s.get("type") != "table": continue
            for r in s["rows"]:
                key = re.sub(r"[（(].*", "", r[0]); alt = re.findall(r"[（(](.*?)[）)]", r[0]) + ALIAS.get(key, [])
                hit = [k for k in [key] + alt if k and k[:3] in parts[0]]
                v = re.sub(r"^約|前後$", "", r[2]) if len(r) > 2 else ""
                if re.match(r"^[+\-]\d", v) and hit:
                    big, d = f"{hit[0]}{v}", (1 if v[0] == "+" else -1); break
            if big: break
        if big is None and chips:
            k, v = max(chips, key=lambda c: abs(float(re.sub(r"[^\d.]", "", c[1]) or 0)))
            big, d = f"{k}{v}", (1 if v[0] == "+" else -1)
        big = big or parts[0]
        k0 = _split_big(big)[0][:3]
        rest = [x for x in parts if not (k0 and k0 in x)]
        line = rest[0] if rest else (parts[0] if parts[0] != big else "")
        if big and not d: d = _sign_from_words(parts[0])
    tag = "速報" if abs(_num(big)) >= 2 or any(w in core for w in ("急落", "暴落", "急騰", "予想超え")) else "今日の米国株"
    m = re.search(r"(\d+)月(\d+)日", b.get("date_label", ""))
    out = {"big": big, "line": line or "", "tag": tag, "dir": d, "chips": chips,
           "date": f"{m.group(1)}/{m.group(2)}" if m else ""}
    out.update({k: v for k, v in t.items() if v})
    return out

def _num(s):
    m = re.search(r"([+\-]?\d+(?:\.\d+)?)%", s or "")
    return float(m.group(1)) if m else 0.0

def _fit(d, text, weight, maxw, start, minsize=40):
    s = start
    while s > minsize and d.textlength(text, font=F(weight, s)) > maxw: s -= 4
    return F(weight, s)

def _txt(d, xy, text, font, fill, stroke=0, sfill=BLK, anchor="la"):
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=sfill, anchor=anchor)

def _shadow_text(im, xy, text, font, fill, stroke, sfill, anchor, off=10, blur=6):
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
    sd.text((xy[0]+off, xy[1]+off), text, font=font, fill=(0, 0, 0, 200), stroke_width=stroke, stroke_fill=(0, 0, 0, 200), anchor=anchor)
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(im).text(xy, text, font=font, fill=fill, stroke_width=stroke, stroke_fill=sfill, anchor=anchor)

def _char(kind, h, level=3):
    n = "toumo" if kind == "とうもろこし" else "yaki"
    im = Image.open(os.path.join(_A, f"{n}_{level}.png")).convert("RGBA")
    return im.resize((int(im.width*h/im.height), h), Image.LANCZOS)

def _col(d): return UP if d > 0 else DN if d < 0 else NEU

def _split_big(big):
    """「ダウ+3%」→（「ダウ」,「+3%」）"""
    m = re.search(r"(約)?[+\-]?\d+(?:\.\d+)?%$", big)
    a, b = (big[:m.start()], big[m.start():]) if m and m.start() > 0 else ("", big)
    return a, b.replace("-", "−")                       # 細いハイフンを太いマイナスに

# ---------- A：速報ニュース型 ----------
def style_a(f):
    im = Image.new("RGBA", (W, H), BLK); d = ImageDraw.Draw(im)
    for y in range(H):                                 # 黒→濃い赤のグラデーション
        k = y / H; d.line([(0, y), (W, y)], fill=(int(20+60*k), 8, int(12+6*k)))
    d.polygon([(0, 0), (420, 0), (360, 120), (0, 120)], fill=DN)
    _txt(d, (40, 60), f["tag"], F("Black", 76), WHT, anchor="lm")
    _txt(d, (W-40, 60), f["date"] + " 米国株", F("Black", 52), YEL, 3, BLK, "rm")
    label, num = _split_big(f["big"])
    fnum = _fit(d, num, "Black", 900 if label else 1180, 300)
    y0 = 330
    if label:
        fl = _fit(d, label, "Black", 330, 150)
        _shadow_text(im, (60, y0), label, fl, WHT, 8, BLK, "lm")
        x = 70 + d.textlength(label, font=fl)
    else:
        x = 60
    _shadow_text(im, (x, y0), num, fnum, YEL if f["dir"] >= 0 else (255, 90, 90), 14, BLK, "lm")
    if f["line"]:
        fl2 = _fit(d, f["line"], "Black", 860, 104)
        d.rectangle([0, 520, W, 660], fill=YEL)
        _txt(d, (50, 590), f["line"], fl2, BLK, anchor="lm")
    c = _char("焼きもろこし", 330); im.alpha_composite(c, (W-c.width-10, H-c.height+20))
    return im

# ---------- B：巨大数字型 ----------
def style_b(f):
    col = _col(f["dir"]); dark = tuple(int(v*0.35) for v in col)
    im = Image.new("RGBA", (W, H)); d = ImageDraw.Draw(im)
    for x in range(W):
        k = x / W; d.line([(x, 0), (x, H)], fill=tuple(int(dark[i]*(1-k)+col[i]*0.75*k) for i in range(3)))
    label, num = _split_big(f["big"])
    ax, ay = 1080, 300                                  # 大きな矢印
    if f["dir"] != 0:
        s = -1 if f["dir"] > 0 else 1
        pts = [(ax, ay+s*200), (ax-150, ay+s*20), (ax-65, ay+s*20), (ax-65, ay-s*190), (ax+65, ay-s*190), (ax+65, ay+s*20), (ax+150, ay+s*20)]
        d.polygon(pts, fill=(255, 255, 255, 235), outline=BLK, width=8)
    if label: _txt(d, (60, 90), label, _fit(d, label, "Black", 700, 120), WHT, 8, BLK, "lm")
    _shadow_text(im, (40, 330), num, _fit(d, num, "Black", 900, 330), WHT, 14, BLK, "lm", off=14)
    d.rectangle([0, 560, W, H], fill=BLK)
    txt = f["line"] or f["tag"]
    _txt(d, (40, 640), txt, _fit(d, txt, "Black", 980, 96), YEL, anchor="lm")
    _txt(d, (W-30, 640), f["date"], F("Black", 64), WHT, anchor="rm")
    return im

# ---------- C：キャラ驚き型 ----------
def style_c(f):
    im = Image.new("RGBA", (W, H), (255, 214, 0)); d = ImageDraw.Draw(im)
    cx, cy = W/2, H*0.45
    for i in range(36):                                 # 集中線
        a0 = i*2*math.pi/36; a1 = a0 + math.pi/36
        d.polygon([(cx, cy), (cx+1600*math.cos(a0), cy+1600*math.sin(a0)), (cx+1600*math.cos(a1), cy+1600*math.sin(a1))],
                  fill=(255, 168, 0) if i % 2 else (255, 230, 60))
    l = _char("とうもろこし", 420); r = _char("焼きもろこし", 420)
    im.alpha_composite(l, (-30, H-l.height+40)); im.alpha_composite(r, (W-r.width+30, H-r.height+40))
    d.rounded_rectangle([250, 40, W-250, 420], radius=40, fill=WHT, outline=BLK, width=10)
    d.polygon([(560, 412), (640, 412), (520, 500)], fill=WHT, outline=None)
    d.line([(560, 418), (520, 500), (640, 418)], fill=BLK, width=10)
    label, num = _split_big(f["big"])
    if label: _txt(d, (W/2, 120), label, _fit(d, label, "Black", 700, 100), BLK, anchor="mm")
    _txt(d, (W/2, 280 if label else 230), num, _fit(d, num, "Black", 720, 230), _col(f["dir"]) if f["dir"] else DN, 8, BLK, "mm")
    if f["line"]:
        fl = _fit(d, f["line"], "Black", 700, 80)
        tw = d.textlength(f["line"], font=fl)
        d.rounded_rectangle([W/2-tw/2-30, 540, W/2+tw/2+30, 660], radius=20, fill=BLK)
        _txt(d, (W/2, 600), f["line"], fl, YEL, anchor="mm")
    _txt(d, (30, 30), f["date"], F("Black", 56), WHT, 6, BLK)
    return im

# ---------- D：チャート背景型 ----------
def style_d(f):
    im = Image.new("RGBA", (W, H), (8, 14, 30)); d = ImageDraw.Draw(im)
    for x in range(0, W, 80): d.line([(x, 0), (x, H)], fill=(20, 32, 58), width=2)
    for y in range(0, H, 80): d.line([(0, y), (W, y)], fill=(20, 32, 58), width=2)
    col = _col(f["dir"]); s = f["dir"] or 1
    import random; rnd = random.Random(7); pts = []; v = 0.15 if s > 0 else 0.9
    for i in range(41):                                 # 値動きの線（上げの日は右肩上がり）
        v += s*0.02 + rnd.uniform(-0.035, 0.035); v = min(max(v, 0.1), 0.9)
        pts.append((i*W/40, H*(0.95 - 0.8*v)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(glow)
    gd.line(pts, fill=col + (255,), width=26); im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))
    area = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ad = ImageDraw.Draw(area)
    ad.polygon(pts + [(W, H), (0, H)], fill=col + (60,)); im.alpha_composite(area)
    d.line(pts, fill=col, width=10)
    dim = Image.new("RGBA", (W, H), (0, 0, 0, 90)); im.alpha_composite(dim); d = ImageDraw.Draw(im)
    d.rounded_rectangle([30, 30, 330, 110], radius=16, fill=YEL)
    _txt(d, (180, 70), f["date"] + " 米国株", F("Black", 46), BLK, anchor="mm")
    label, num = _split_big(f["big"])
    if label: _txt(d, (50, 200), label, _fit(d, label, "Black", 900, 120), WHT, 8, BLK, "lm")
    _shadow_text(im, (40, 360), num, _fit(d, num, "Black", 1100, 260), col, 12, WHT, "lm")
    d = ImageDraw.Draw(im)
    if f["line"]: _txt(d, (50, 520), f["line"], _fit(d, f["line"], "Black", 1180, 90), WHT, 8, BLK, "lm")
    x = 40
    for k, v in f["chips"][:3]:
        t = f"{k} {v}"; fc = F("Bold", 40); tw = d.textlength(t, font=fc)
        d.rounded_rectangle([x, 610, x+tw+40, 680], radius=14, fill=(15, 23, 42), outline=UP if v[0] == "+" else DN, width=4)
        _txt(d, (x+20, 645), t, fc, UP if v[0] == "+" else DN, anchor="lm"); x += tw + 60
    return im

STYLES = {"A": style_a, "B": style_b, "C": style_c, "D": style_d}

def make(b, out_png, style=None):
    im = STYLES[(style or b.get("thumb_style") or STYLE).upper()](facts(b))
    im.convert("RGB").save(out_png, quality=92)
    return out_png

if __name__ == "__main__":
    import json, sys
    b = json.load(open(sys.argv[1], encoding="utf-8")); out = sys.argv[2]
    for k in (sys.argv[3] if len(sys.argv) > 3 else "ABCD"):
        make(b, out.replace(".png", f"_{k}.png"), k); print(facts(b))
