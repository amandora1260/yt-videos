"""スライド画像＋字幕を作り、音声と合わせてMP4にする"""
import os, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
FD = "/usr/share/fonts/opentype/noto/"
def F(w, s): return ImageFont.truetype(FD + f"NotoSansCJK-{w}.ttc", s, index=0)  # index0＝日本語字形（JP）
BG=(14,27,48); PANEL=(24,42,72); WHITE=(240,244,250); GRAY=(150,165,190); ACC=(56,189,248)
UP=(52,211,153); DN=(248,113,113)
SPK_COL = {"焼きもろこし": (244,114,182), "とうもろこし": (250,204,21)}
NO_HEAD = "。、）」』％%！？!?ー"
# 字幕（画面下の話者名ラベル＋台詞の帯）を出すかどうか。kindごとの既定値で、原稿JSONに "show_subtitles": true/false を書けば個別に上書きできる。
# 音声をまとめて作って無音で区切っているため字幕と声が1行ずれることがあり、当面は本編・ショートとも出さない（戻すときは True に）
SHOW_SUBTITLES = {"main": False, "short": False}
def show_subtitles(b):
    v = b.get("show_subtitles")
    return SHOW_SUBTITLES.get(b.get("kind", "main"), True) if v is None else bool(v)

def wrap(d, text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=font) > maxw and ch not in NO_HEAD:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur: lines.append(cur)
    return lines

def _head(d, b, title):
    d.rectangle([0,0,W,8], fill=ACC)
    d.text((100,60), title, font=F("Bold",64), fill=WHITE)
    d.text((W-100,80), b["date_label"], font=F("Regular",34), fill=GRAY, anchor="ra")
    d.line([100,160,W-100,160], fill=PANEL, width=3)

def render_slide(b, s):
    im = Image.new("RGB", (W,H), BG); d = ImageDraw.Draw(im); t = s["type"]
    if t in ("title","end"):
        d.rectangle([0,0,W,8], fill=ACC)
        d.text((W/2,330), s["title"], font=F("Black",104 if t=="title" else 84), fill=WHITE, anchor="mm")
        if t == "title": d.text((W/2,470), b["date_label"], font=F("Bold",56), fill=ACC, anchor="mm")
        y = 560 if t == "title" else 470
        ls = [x for p in s.get("sub","").split("\n") for x in wrap(d,p,F("Regular",38),1500)]
        for i,l in enumerate(ls): d.text((W/2,y+i*60), l, font=F("Regular",38), fill=GRAY, anchor="mm")
        return im
    _head(d, b, s["title"])
    if t == "table":
        y = 220
        col2x = max([560] + [140 + int(d.textlength(r[0], font=F("Bold",48))) + 70 for r in s["rows"][:5]])
        for r in s["rows"][:5]:
            d.rounded_rectangle([100,y,W-100,y+100], radius=14, fill=PANEL)
            d.text((140,y+50), r[0], font=F("Bold",48), fill=WHITE, anchor="lm")
            if len(r) > 2 and r[2] == "":                      # 3列目が空の表（予定・決算）は2列目を左寄せ
                d.text((col2x,y+50), r[1], font=F("Regular",48), fill=WHITE, anchor="lm")
            else:
                d.text((1150,y+50), r[1], font=F("Regular",48), fill=WHITE, anchor="rm")
            v = r[2] if len(r) > 2 else ""
            col = UP if v.startswith("+") else DN if v.startswith("-") else ACC
            if len(r) > 3 and r[3] in ("good", "bad"):        # VIX上昇・金利低下など、符号と良し悪しが逆のもの
                col = UP if r[3] == "good" else DN
            mark = "▲ " if v.startswith("+") else "▼ " if v.startswith("-") else ""
            d.text((W-140,y+50), mark+v, font=F("Bold",48), fill=col, anchor="rm")
            y += 112
    elif t == "bullets":
        y = 240
        for i,it in enumerate(s["items"][:3]):
            d.ellipse([110,y+12,160,y+62], fill=ACC)
            d.text((135,y+37), str(i+1), font=F("Bold",34), fill=BG, anchor="mm")
            for j,l in enumerate(wrap(d,it,F("Bold",52),W-400)[:2]):
                d.text((200,y+j*70), l, font=F("Bold",52), fill=WHITE)
            y += 160
    return im

def add_subtitle(im, speaker, text):
    im = im.copy(); d = ImageDraw.Draw(im); f = F("Medium",46)
    lines = wrap(d, text, f, W-300)[:3]
    h = 70*len(lines) + 60
    ov = Image.new("RGBA",(W,H),(0,0,0,0)); od = ImageDraw.Draw(ov)
    od.rectangle([0,H-h-40,W,H], fill=(0,0,0,175))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"); d = ImageDraw.Draw(im)
    nf = F("Bold",36); col = SPK_COL.get(speaker, ACC)
    d.rounded_rectangle([100,H-h-75,100+d.textlength(speaker,font=nf)+48,H-h-20], radius=10, fill=col)
    d.text((124,H-h-47), speaker, font=nf, fill=(15,15,25), anchor="lm")
    for i,l in enumerate(lines): d.text((W/2,H-h+i*70), l, font=f, fill=WHITE, anchor="ma")
    return im

def build_video(b, audios, workdir, out_mp4):
    """audios: スライドごとの (pcm, rate)。字幕は発言の文字数に比例して時間を割り振る"""
    os.makedirs(workdir, exist_ok=True)
    rate = audios[0][1]; pieces = []; entries = []; n = 0
    gap = np.zeros(int(rate*0.5), np.int16)                     # スライドの切り替わりに0.5秒の間
    for s,(pcm,r) in zip(b["slides"], audios):
        if r != rate:                                           # 念のためレートをそろえる
            idx = np.linspace(0, len(pcm)-1, int(len(pcm)*rate/r)).astype(int); pcm = pcm[idx]
        seg = np.concatenate([pcm, gap]); pieces.append(seg)
        total = len(seg)/rate
        base = render_slide(b, s)
        chars = [max(len(t["text"]),1) for t in s["dialogue"]]
        for t,c in zip(s["dialogue"], chars):
            n += 1; p = os.path.join(workdir, f"{n:03d}.png")
            (add_subtitle(base, t["speaker"], t["text"]) if show_subtitles(b) else base).save(p)
            entries.append((p, total*c/sum(chars)))
    wav = os.path.join(workdir, "voice.wav")
    import scipy.io.wavfile as wv
    a = np.concatenate(pieces).astype(np.float32)
    peak = np.abs(a).max()
    if peak > 0: a = a/peak*0.85*32767                          # 音割れ防止
    wv.write(wav, rate, a.astype(np.int16))
    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        for p,dur in entries: f.write(f"file '{os.path.abspath(p)}'\nduration {dur:.3f}\n")
        f.write(f"file '{os.path.abspath(entries[-1][0])}'\n")
    subprocess.run(["ffmpeg","-y","-loglevel","error","-f","concat","-safe","0","-i",lst,"-i",wav,
                    "-vf","fps=30,format=yuv420p","-c:v","libx264","-preset","medium","-tune","stillimage","-crf","23",
                    "-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",out_mp4], check=True)
    return sum(e[1] for e in entries), os.path.join(workdir, "001.png")
