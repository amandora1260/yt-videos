"""本編：スライド（＋字幕。render.SHOW_SUBTITLES で切り替え）に、キャラクターの口パク・動きを重ねる"""
import os, math, subprocess, numpy as np
from PIL import Image, ImageDraw
import render, chars
_A = os.path.join(os.path.dirname(__file__), "..", "assets")
_SPR = {}
def sprite(kind, level, h):
    key = (kind, level, h)
    if key not in _SPR:
        n = "toumo" if kind == "とうもろこし" else "yaki"
        im = Image.open(os.path.join(_A, f"{n}_{level}.png")).convert("RGBA")
        _SPR[key] = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
    return _SPR[key]
from render import F, wrap, W, H, WHITE, ACC, SPK_COL
FPS = 15; CH = 345; SIDE = 330          # キャラの高さ・字幕の左右の余白

def subtitle(im, speaker, text):
    im = im.copy(); d = ImageDraw.Draw(im); f = F("Medium", 46)
    lines = wrap(d, text, f, W - SIDE*2 - 40)[:3]
    h = 70*len(lines) + 60
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); od = ImageDraw.Draw(ov)
    od.rectangle([0, H-h-40, W, H], fill=(0, 0, 0, 175))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"); d = ImageDraw.Draw(im)
    nf = F("Bold", 36); col = SPK_COL.get(speaker, ACC); tw = d.textlength(speaker, font=nf)
    d.rounded_rectangle([W/2-tw/2-24, H-h-75, W/2+tw/2+24, H-h-20], radius=10, fill=col)
    d.text((W/2, H-h-47), speaker, font=nf, fill=(15, 15, 25), anchor="mm")
    for i, l in enumerate(lines): d.text((W/2, H-h+i*70), l, font=f, fill=WHITE, anchor="ma")
    return im

def build(b, audios, workdir, out_mp4):
    os.makedirs(workdir, exist_ok=True); fdir = os.path.join(workdir, "c"); os.makedirs(fdir, exist_ok=True)
    rate = audios[0][1]; gap = np.zeros(int(rate*0.5), np.int16)
    pieces, entries, timeline, t, n = [], [], [], 0.0, 0
    for s, au in zip(b["slides"], audios):
        pcm, r = au[0], au[1]; parts = au[2] if len(au) > 2 else None
        seg = np.concatenate([pcm, gap]); pieces.append(seg); total = len(seg)/rate
        base = render.render_slide(b, s)
        if parts is None or len(parts) != len(s["dialogue"]):   # 文字起こしで切れなかったときは「間」で推測
            import short as _sh
            parts = _sh.split_lines(pcm, r, s["dialogue"]) if len(s["dialogue"]) > 1 else [pcm]
        durs = [len(p_)/r for p_ in parts]; durs[-1] += len(gap)/rate
        for x, dur in zip(s["dialogue"], durs):
            n += 1; p = os.path.join(workdir, f"{n:03d}.png")
            (subtitle(base, x["speaker"], x["text"]) if render.show_subtitles(b) else base).save(p); entries.append((p, dur))
            timeline.append((t, t+dur, x["speaker"])); t += dur
    a = np.concatenate(pieces).astype(np.float32); a = a/max(1, np.abs(a).max())*0.85*32767
    import scipy.io.wavfile as wv; wav = os.path.join(workdir, "voice.wav"); wv.write(wav, rate, a.astype(np.int16))
    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        for p, dd in entries: f.write(f"file '{os.path.abspath(p)}'\nduration {dd:.3f}\n")
        f.write(f"file '{os.path.abspath(entries[-1][0])}'\n")
    # キャラのコマ（15fps）：話している方は口が音量に合わせて動き、体が弾む
    env = chars.envelope(a.astype(np.int16), rate, FPS); nfr = len(env)
    who = lambda tt: next((sp for t0, t1, sp in timeline if t0 <= tt < t1), None)
    for i in range(nfr):
        tt = i/FPS; sp = who(tt)
        canvas = Image.new("RGBA", (W, CH+20), (0, 0, 0, 0))
        for kind, side, ph in (("とうもろこし", "L", 0.0), ("焼きもろこし", "R", 1.3)):
            talk = (sp == kind); e = float(env[i]) if talk else 0.0
            level = 0 if e < 0.2 else 1 if e < 0.45 else 2 if e < 0.7 else 3      # 声の大きさで口を4段階に
            bounce = 10*abs(math.sin(tt*6+ph)) if talk and e > 0.2 else 3*math.sin(tt*1.5+ph)
            spr = sprite(kind, level, CH - 10)
            x0 = 20 if side == "L" else W - spr.width - 20
            canvas.alpha_composite(spr, (x0, int(12 - bounce)))
        canvas.save(os.path.join(fdir, f"{i:05d}.png"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
        "-framerate", str(FPS), "-i", os.path.join(fdir, "%05d.png"),
        "-filter_complex", f"[0:v]fps=30[bg];[bg][2:v]overlay=0:{H-CH-20}:shortest=0:eof_action=pass,format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    return t
